"""
通用 Plan-Execute-Replan 服务
基于 LangGraph 官方教程实现

这个文件是 AIOps Agent 的“总调度器”。
planner.py、executor.py、replanner.py 分别只是一个节点；
这里负责把这三个节点组装成一个 LangGraph 状态机：

planner -> executor -> replanner -> executor -> replanner -> ... -> END

整个图共用同一个 PlanExecuteState 状态，状态大概长这样：
{
    "input": "用户输入的诊断任务",
    "plan": ["待执行步骤1", "待执行步骤2"],
    "past_steps": [("已执行步骤", "执行结果")],
    "response": "最终 Markdown 报告"
}

execute(...) 最终不是一次性返回字符串，而是持续 yield 事件给 API 层，
适合被 FastAPI SSE 接口包装成流式响应。
"""

from typing import AsyncGenerator, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from app.agent.aiops import PlanExecuteState, planner, executor, replanner


# 节点名称常量
# 这些字符串既是 LangGraph 的节点名，也是解析 self.graph.astream(...) 输出事件时的 key。
NODE_PLANNER = "planner"
NODE_EXECUTOR = "executor"
NODE_REPLANNER = "replanner"


class AIOpsService:
    """通用 Plan-Execute-Replan 服务

    这个类负责：
    1. 构建 LangGraph 工作流
    2. 启动任务执行
    3. 把每个节点的状态更新格式化成前端可读事件
    4. 提供 diagnose() 兼容旧诊断接口
    """

    def __init__(self):
        """初始化服务

        MemorySaver 是 LangGraph 的内存 checkpoint。
        它会根据 thread_id 保存一次图执行中的状态，后面可以通过 get_state 取最终状态。
        """
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()
        logger.info("Plan-Execute-Replan Service 初始化完成")

    def _build_graph(self):
        """构建 Plan-Execute-Replan 工作流

        图结构：
        1. planner：根据 input 生成 plan
        2. executor：取 plan[0] 执行，把结果追加到 past_steps，并移除已执行步骤
        3. replanner：根据 past_steps 和剩余 plan 判断继续、重规划或生成 response

        条件循环：
        - replanner 后如果 state["response"] 有值：END
        - replanner 后如果 state["plan"] 还有步骤：回到 executor
        """
        logger.info("构建工作流图...")

        # 创建状态图
        # PlanExecuteState 定义了图中所有节点共同读写的字段。
        workflow = StateGraph(PlanExecuteState)

        # 添加节点
        workflow.add_node(NODE_PLANNER, planner)      # 制定计划
        workflow.add_node(NODE_EXECUTOR, executor)  # 执行步骤
        workflow.add_node(NODE_REPLANNER, replanner)  # 重新规划

        # 设置入口点
        workflow.set_entry_point(NODE_PLANNER)

        # 定义边
        workflow.add_edge(NODE_PLANNER, NODE_EXECUTOR)     # planner -> executor
        workflow.add_edge(NODE_EXECUTOR, NODE_REPLANNER)   # executor -> replanner

        # replanner 的条件边
        def should_continue(state: PlanExecuteState) -> str:
            """判断是否继续执行

            这个函数只在 replanner 节点执行完之后调用。
            它根据最新状态决定下一条边走向：
            - 返回 END：整个图结束
            - 返回 NODE_EXECUTOR：继续执行下一个计划步骤
            """
            # 如果已经生成了最终响应，结束
            if state.get("response"):
                logger.info("已生成最终响应，结束流程")
                return END

            # 如果还有计划步骤，继续执行
            plan = state.get("plan", [])
            if plan:
                logger.info(f"继续执行，剩余 {len(plan)} 个步骤")
                return NODE_EXECUTOR

            # 计划为空但没有响应，返回 replanner 生成响应
            # 正常情况下 replanner.py 在 plan 为空时会生成 response。
            # 如果走到这里仍然没有 response，就结束，避免异常循环。
            logger.info("计划执行完毕，生成最终响应")
            return END

        workflow.add_conditional_edges(
            NODE_REPLANNER,
            should_continue,
            {
                NODE_EXECUTOR: NODE_EXECUTOR,
                END: END
            }
        )

        # 编译工作流
        # 编译后才能调用 astream/ainvoke 等方法执行图。
        # checkpointer 让同一个 session_id/thread_id 可以保存执行状态。
        compiled_graph = workflow.compile(checkpointer=self.checkpointer)

        logger.info("工作流图构建完成")
        return compiled_graph

    async def execute(
        self,
        user_input: str,
        session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行 Plan-Execute-Replan 流程

        Args:
            user_input: 用户的任务描述
            session_id: 会话ID

        Yields:
            Dict[str, Any]: 流式事件

        执行结果不是最终字符串，而是一连串事件，例如：
        {"type": "plan", "stage": "plan_created", "plan": ["查询告警", "查询日志"]}
        {"type": "step_complete", "stage": "step_executed", "current_step": "查询告警"}
        {"type": "status", "stage": "replanner", "remaining_steps": 1}
        {"type": "report", "stage": "final_report", "report": "# 告警分析报告\\n..."}
        {"type": "complete", "stage": "complete", "response": "# 告警分析报告\\n..."}
        """
        logger.info(f"[会话 {session_id}] 开始执行任务: {user_input}")

        try:
            # 初始化状态
            # 这是传入 LangGraph 的初始状态。
            # 后续 planner 会填充 plan，executor 会填充 past_steps，replanner 会填充 response。
            initial_state: PlanExecuteState = {
                "input": user_input,
                "plan": [],
                "past_steps": [],
                "response": ""
            }

            # 流式执行工作流
            # thread_id 用于区分不同会话的 checkpoint。
            # 这里使用 session_id 作为 thread_id。
            config_dict = {
                "configurable": {
                    "thread_id": session_id
                }
            }

            async for event in self.graph.astream(
                input=initial_state,
                config=config_dict,
                stream_mode="updates"
            ):
                # 解析事件
                # stream_mode="updates" 表示每次只返回某个节点对状态的增量更新。
                # 示例：
                # {"planner": {"plan": ["步骤1", "步骤2"]}}
                # {"executor": {"plan": ["步骤2"], "past_steps": [("步骤1", "结果1")]}}
                # {"replanner": {"response": "# 最终报告"}}
                for node_name, node_output in event.items():
                    logger.info(f"节点 '{node_name}' 输出事件")

                    # 根据节点类型生成不同的事件
                    if node_name == NODE_PLANNER:
                        yield self._format_planner_event(node_output)

                    elif node_name == NODE_EXECUTOR:
                        yield self._format_executor_event(node_output)

                    elif node_name == NODE_REPLANNER:
                        yield self._format_replanner_event(node_output)

            # 获取最终状态
            # 图执行完以后，从 checkpointer 中读取最终 state，拿到完整 response。
            final_state = self.graph.get_state(config_dict)
            final_response = ""

            # 安全地获取响应（处理 values 可能为 None 的情况）
            if final_state and final_state.values:
                final_response = final_state.values.get("response", "")

            # 发送完成事件
            # complete 是 execute(...) 的最后一个事件，用于告诉前端整个任务已经结束。
            yield {
                "type": "complete",
                "stage": "complete",
                "message": "任务执行完成",
                "response": final_response
            }

            logger.info(f"[会话 {session_id}] 任务执行完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] 任务执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "stage": "error",
                "message": f"任务执行出错: {str(e)}"
            }

    async def diagnose(
        self,
        session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        AIOps 诊断接口（兼容旧接口）

        Args:
            session_id: 会话ID

        Yields:
            Dict[str, Any]: 诊断过程的流式事件

        diagnose() 是 execute() 的特化版本。
        它内部写死了一个“诊断当前系统告警并生成报告”的任务描述，
        然后复用 execute(...) 的完整 Plan-Execute-Replan 流程。

        和 execute(...) 的区别：
        - execute(...) 的 complete 事件返回 response 字段
        - diagnose(...) 为了兼容旧接口，把 response 包装成 diagnosis.report
        """
        # 使用固定的 AIOps 任务描述
        from textwrap import dedent
        aiops_task = dedent("""诊断当前系统是否存在告警，如果存在告警请详细分析告警原因并生成诊断报告，诊断报告输出格式要求：
                ```
                # 告警分析报告

                ---

                ## 📋 活跃告警清单

                | 告警名称 | 级别 | 目标服务 | 首次触发时间 | 最新触发时间 | 状态 |
                |---------|------|----------|-------------|-------------|------|
                | [告警1名称] | [级别] | [服务名] | [时间] | [时间] | 活跃 |
                | [告警2名称] | [级别] | [服务名] | [时间] | [时间] | 活跃 |

                ---

                ## 🔍 告警根因分析1 - [告警名称]

                ### 告警详情
                - **告警级别**: [级别]
                - **受影响服务**: [服务名]
                - **持续时间**: [X分钟]

                ### 症状描述
                [根据监控指标描述症状]

                ### 日志证据
                [引用查询到的关键日志]

                ### 根因结论
                [基于证据得出的根本原因]

                ---

                ## 🛠️ 处理方案执行1 - [告警名称]

                ### 已执行的排查步骤
                1. [步骤1]
                2. [步骤2]

                ### 处理建议
                [给出具体的处理建议]

                ### 预期效果
                [说明预期的效果]

                ---

                ## 🔍 告警根因分析2 - [告警名称]
                [如果有第2个告警，重复上述格式]

                ---

                ## 📊 结论

                ### 整体评估
                [总结所有告警的整体情况]

                ### 关键发现
                - [发现1]
                - [发现2]

                ### 后续建议
                1. [建议1]
                2. [建议2]

                ### 风险评估
                [评估当前风险等级和影响范围]
                ```

                **重要提醒**：
                - 最终输出必须是纯 Markdown 文本，不要包含 JSON 结构
                - 所有内容必须基于工具查询的真实数据，严禁编造
                - 如果某个步骤失败，在结论中如实说明，不要跳过""")

        async for event in self.execute(aiops_task, session_id):
            # 转换事件格式以兼容旧的 API
            if event.get("type") == "complete":
                # 将 response 包装为 diagnosis 格式
                # execute complete:
                # {"type": "complete", "response": "..."}
                #
                # diagnose complete:
                # {"type": "complete", "diagnosis": {"status": "completed", "report": "..."}}
                yield {
                    "type": "complete",
                    "stage": "diagnosis_complete",
                    "message": "诊断流程完成",
                    "diagnosis": {
                        "status": "completed",
                        "report": event.get("response", "")
                    }
                }
            else:
                yield event

    def _format_planner_event(self, state: Dict | None) -> Dict:
        """格式化 Planner 节点事件

        planner.py 返回的状态增量通常是：
        {"plan": ["查询告警", "查询日志", "生成报告"]}

        这里把它转换成前端事件：
        {
            "type": "plan",
            "stage": "plan_created",
            "message": "执行计划已制定，共 3 个步骤",
            "plan": [...]
        }
        """
        if not state:
            return {
                "type": "status",
                "stage": "planner",
                "message": "规划节点执行中"
            }

        plan = state.get("plan", [])

        return {
            "type": "plan",
            "stage": "plan_created",
            "message": f"执行计划已制定，共 {len(plan)} 个步骤",
            "plan": plan
        }

    def _format_executor_event(self, state: Dict | None) -> Dict:
        """格式化 Executor 节点事件

        executor.py 每次只执行一个步骤，返回的状态增量通常是：
        {
            "plan": ["剩余步骤"],
            "past_steps": [("刚执行的步骤", "执行结果")]
        }

        这里不会把完整执行结果直接返回给前端，只告诉前端“哪个步骤执行完了”和“还剩几步”。
        完整结果会留在 past_steps 中，后续由 replanner 汇总成最终报告。
        """
        if not state:
            return {
                "type": "status",
                "stage": "executor",
                "message": "执行节点运行中"
            }

        plan = state.get("plan", [])
        past_steps = state.get("past_steps", [])

        if past_steps:
            last_step, _ = past_steps[-1]
            return {
                "type": "step_complete",
                "stage": "step_executed",
                "message": f"步骤执行完成 ({len(past_steps)}/{len(past_steps) + len(plan)})",
                "current_step": last_step,
                "remaining_steps": len(plan)
            }
        else:
            return {
                "type": "status",
                "stage": "executor",
                "message": "开始执行步骤"
            }

    def _format_replanner_event(self, state: Dict | None) -> Dict:
        """格式化 Replanner 节点事件

        replanner.py 的返回可能有三种：
        1. {}：继续执行原计划
        2. {"plan": [...]}：替换剩余计划
        3. {"response": "..."}：生成最终报告

        如果有 response，这里返回 report 事件；
        如果没有 response，就返回 status 事件，告诉前端还要继续执行。
        """
        if not state:
            return {
                "type": "status",
                "stage": "replanner",
                "message": "评估节点运行中"
            }

        response = state.get("response", "")
        plan = state.get("plan", [])

        if response:
            # 已生成最终响应
            return {
                "type": "report",
                "stage": "final_report",
                "message": "最终报告已生成",
                "report": response
            }
        else:
            # 重新规划
            return {
                "type": "status",
                "stage": "replanner",
                "message": f"评估完成，{'继续执行剩余步骤' if plan else '准备生成最终响应'}",
                "remaining_steps": len(plan)
            }


# 全局单例
# API 层可以直接 import aiops_service 使用，避免每个请求都重新构建 LangGraph。
aiops_service = AIOpsService()
