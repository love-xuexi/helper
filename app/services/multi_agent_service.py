"""多 Agent 协作服务

多 Agent 版本的 aiops_service。负责：
1. 构建多 Agent LangGraph 图
2. 启动任务执行
3. 将图节点输出格式化为前端可读的 SSE 事件
4. 持久化执行结果（复用 session_persistence）

与 app/services/aiops_service.py 完全独立，互不影响。
前端通过 POST /api/aiops?multi_agent=true 路由到本服务。
"""

from collections.abc import AsyncGenerator
from typing import Any

from langgraph.graph import END
from loguru import logger

from app.agent.multi_agent import build_multi_agent_graph
from app.agent.multi_agent.prompts import WORKER_PROFILES
from app.core.session_persistence import session_persistence_manager

# 节点名称（与 __init__.py 保持一致）
_NODE_SUPERVISOR = "supervisor"
_NODE_WORKERS = {"researcher", "analyst", "executor", "writer"}


class MultiAgentService:
    """多 Agent 协作服务（Supervisor-Worker 模式）"""

    def __init__(self):
        """初始化服务"""
        self.checkpointer = session_persistence_manager.checkpointer
        self.graph = build_multi_agent_graph(checkpointer=self.checkpointer)
        logger.info("多 Agent 协作服务初始化完成")

    def configure_checkpointer(self, checkpointer: Any) -> None:
        """重新配置 checkpointer 并重建图"""
        self.checkpointer = checkpointer
        self.graph = build_multi_agent_graph(checkpointer=checkpointer)

    async def execute(
        self, user_input: str, session_id: str = "default"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行多 Agent 协作任务

        Args:
            user_input: 用户的任务描述
            session_id: 会话ID

        Yields:
            流式事件，事件类型：
            - {"type": "start", "task": "..."}  任务开始
            - {"type": "supervisor_route", "next_worker": "...", "subtask": "...", "reasoning": "..."}
            - {"type": "worker_start", "worker": "...", "subtask": "..."}
            - {"type": "worker_complete", "worker": "...", "result": "..."}
            - {"type": "report", "report": "..."}  最终报告
            - {"type": "complete", "response": "..."}  任务完成
            - {"type": "error", "message": "..."}  错误
        """
        logger.info(f"[多Agent 会话 {session_id}] 开始执行任务: {user_input}")

        try:
            # 发送开始事件
            yield {"type": "start", "stage": "multi_agent_start", "task": user_input}

            # 初始化状态
            initial_state = {
                "task": user_input,
                "worker_results": [],
                "current_subtask": "",
                "final_report": "",
                "next": "",
            }

            config_dict = {"configurable": {"thread_id": session_id}}

            # 流式执行图
            async for event in self.graph.astream(
                input=initial_state, config=config_dict, stream_mode="updates"
            ):
                for node_name, node_output in event.items():
                    logger.info(f"[多Agent] 节点 '{node_name}' 输出事件")

                    if node_name == _NODE_SUPERVISOR:
                        yield self._format_supervisor_event(node_output)
                    elif node_name in _NODE_WORKERS:
                        yield self._format_worker_event(node_name, node_output)

            # 获取最终状态
            final_state = self.graph.get_state(config_dict)
            final_report = ""
            worker_results: list = []

            if final_state and final_state.values:
                final_report = final_state.values.get("final_report", "")
                worker_results = final_state.values.get("worker_results", [])

            # 持久化：存为 multi_agent 格式，前端按 type==='multi_agent' 还原执行流程
            try:
                routes = []
                for wr in worker_results:
                    worker = wr.get("worker", "")
                    profile = WORKER_PROFILES.get(worker, {})
                    routes.append(
                        {
                            "worker": worker,
                            "workerName": profile.get("name", worker),
                            "workerEmoji": profile.get("emoji", "🤖"),
                            "subtask": wr.get("subtask", ""),
                            "result": wr.get("result", ""),
                        }
                    )
                session_persistence_manager.upsert_multi_agent_session(
                    session_id=session_id,
                    task=user_input,
                    routes=routes,
                    report=final_report,
                )
                logger.info(
                    f"[多Agent 会话 {session_id}] 任务已持久化（{len(routes)} 轮 Worker 调用）"
                )
            except Exception as persist_err:
                logger.error(f"[多Agent 会话 {session_id}] 持久化失败: {persist_err}")

            # 发送报告事件
            if final_report:
                yield {
                    "type": "report",
                    "stage": "final_report",
                    "message": "最终报告已生成",
                    "report": final_report,
                }

            # 发送完成事件
            yield {
                "type": "complete",
                "stage": "complete",
                "message": "多 Agent 任务执行完成",
                "response": final_report,
            }

            logger.info(f"[多Agent 会话 {session_id}] 任务执行完成")

        except Exception as e:
            logger.error(f"[多Agent 会话 {session_id}] 任务执行失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "stage": "error",
                "message": f"多 Agent 任务执行出错: {str(e)}",
            }

    def _format_supervisor_event(self, state: dict | None) -> dict:
        """格式化 Supervisor 节点事件

        Supervisor 的输出可能是：
        - {"next": "researcher", "current_subtask": "..."}  路由到 Worker
        - {"next": "FINISH", "final_report": "..."}  结束
        """
        if not state:
            return {"type": "status", "stage": "supervisor", "message": "调度中…"}

        next_worker = state.get("next", "")
        subtask = state.get("current_subtask", "")
        final_report = state.get("final_report", "")

        if next_worker == END or next_worker == "FINISH" or final_report:
            # Supervisor 决定结束
            return {
                "type": "supervisor_finish",
                "stage": "supervisor_finish",
                "message": "信息已充分，准备生成最终报告",
                "final_report_preview": final_report[:200] + "..."
                if len(final_report) > 200
                else final_report,
            }
        elif next_worker in _NODE_WORKERS:
            # 路由到 Worker
            profile = WORKER_PROFILES.get(next_worker, {})
            return {
                "type": "supervisor_route",
                "stage": "supervisor_route",
                "next_worker": next_worker,
                "worker_name": profile.get("name", next_worker),
                "worker_emoji": profile.get("emoji", "🤖"),
                "subtask": subtask,
                "message": f"派给 {profile.get('emoji', '')} {profile.get('name', next_worker)}: {subtask[:60]}...",
            }
        else:
            return {
                "type": "status",
                "stage": "supervisor",
                "message": f"Supervisor 决策中（next={next_worker}）",
            }

    def _format_worker_event(self, worker_name: str, state: dict | None) -> dict:
        """格式化 Worker 节点事件

        Worker 的输出是：
        {"worker_results": [WorkerResult(worker, subtask, result)]}
        """
        if not state:
            return {"type": "status", "stage": worker_name, "message": f"{worker_name} 执行中"}

        worker_results = state.get("worker_results", [])
        if not worker_results:
            return {"type": "status", "stage": worker_name, "message": f"{worker_name} 执行中"}

        last_result = worker_results[-1]
        profile = WORKER_PROFILES.get(worker_name, {})
        result = last_result.get("result", "")
        result_preview = result[:500] + "..." if len(result) > 500 else result

        return {
            "type": "worker_complete",
            "stage": "worker_complete",
            "worker": worker_name,
            "worker_name": profile.get("name", worker_name),
            "worker_emoji": profile.get("emoji", "🤖"),
            "subtask": last_result.get("subtask", ""),
            "result": result,
            "result_preview": result_preview,
            "message": f"{profile.get('emoji', '')} {profile.get('name', worker_name)} 完成",
        }


# 全局单例
multi_agent_service = MultiAgentService()
