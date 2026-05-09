"""
Replanner 节点：重新规划或生成最终响应
基于 LangGraph 官方教程实现

这个文件定义了 AIOps Plan-Execute-Replan 工作流里的第三个节点：replanner。
executor 每执行完一个步骤后，都会进入 replanner。
replanner 会根据当前剩余计划 plan 和已执行结果 past_steps 判断下一步该怎么做：

1. continue：当前剩余计划合理，不修改状态，继续让 executor 执行下一个步骤
2. replan：当前计划不合理，返回新的 plan 替换剩余计划
3. respond：信息已经足够，生成最终 response，流程准备结束

最终返回值可能有三种：
- {}：不修改状态，继续执行原计划
- {"plan": ["新的步骤1", "新的步骤2"]}：替换剩余计划
- {"response": "最终 Markdown 报告"}：写入最终响应，LangGraph 后续结束
"""

from textwrap import dedent
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen
from pydantic import BaseModel, Field
from loguru import logger

from app.config import config
from app.tools import get_current_time, retrieve_knowledge
from app.agent.mcp_client import get_mcp_client_with_retry
from .state import PlanExecuteState
from .utils import format_tools_description


class Response(BaseModel):
    """最终响应的格式

    这是生成最终报告时的大模型结构化输出约束。
    也就是说，大模型最后应该输出：
    Response(response="Markdown 格式最终报告")
    """
    response: str = Field(description="对用户的最终响应")


class Act(BaseModel):
    """重新规划的输出格式

    这是 replanner 决策阶段的大模型结构化输出约束。
    大模型不能随便输出自然语言，而是要输出类似：

    Act(action="continue", new_steps=[])
    Act(action="replan", new_steps=["补充查询日志", "重新分析根因"])
    Act(action="respond", new_steps=[])

    其中 action 决定 replanner 接下来返回什么状态增量。
    """
    action: str = Field(
        description="""下一步的行动，必须是以下三种之一：
        - 'continue': 当前计划合理，继续执行下一个步骤
        - 'replan': 当前计划需要调整，提供新的步骤列表
        - 'respond': 计划已完成且信息充足，生成最终响应"""
    )
    # action 为 'replan' 时，新的步骤列表（会替换当前剩余计划）
    # action 为 continue/respond 时，通常为空列表。
    new_steps: List[str] = Field(
        default_factory=list,
        description="新的步骤列表（如果 action 是 'replan'，这些步骤会替换剩余计划）"
    )


# Replanner 提示词
# 这个提示词用于“决策阶段”：判断当前是继续执行、调整计划，还是生成最终响应。
# 重点约束：
# - 优先 respond，不要为了追求完美无限执行
# - continue 只在剩余步骤确实必要时使用
# - replan 谨慎使用，避免计划越改越长导致死循环
replanner_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent("""
                作为一个重新规划专家，你需要根据已执行的步骤决定下一步行动。

                可用工具列表（用于制定计划时参考）：

                {tools_description}

                注意：你的职责是制定或调整计划，实际的工具调用由 Executor 负责执行。

                你有三个选择（按优先级排序）：

                **1. 'respond' - 信息充足，立即生成最终响应** 【最高优先级】
                   - 使用场景：当前信息已经足够回答用户问题
                   - 决策标准：
                     * 已执行步骤 >= 3 且获取了关键信息
                     * 或者已执行步骤 >= 5（无论结果如何）
                     * 或者当前信息完全满足任务需求
                   - ⚠️ 不要等到"完美"才响应，"足够好"就应该立即 respond

                **2. 'continue' - 当前计划合理，继续执行** 【次优先级】
                   - 使用场景：剩余计划合理且必要
                   - 决策标准：剩余步骤确实能提供关键信息
                   - ⚠️ 如果剩余步骤不是"必需"的，应选择 respond

                **3. 'replan' - 当前计划有严重问题** 【最低优先级，谨慎使用】
                   - 使用场景：原计划明显错误或遗漏关键步骤
                   - ⚠️ **严格限制**：
                     * 新步骤数量必须 <= 当前剩余步骤数
                     * 优先简化计划，不要添加不必要的步骤
                     * 总步骤数已执行 >= 5 次时，禁止 replan，只能 respond

                评估标准：
                - 当前信息是否已经足够解决用户问题？【最关键】
                - 已执行步骤是否成功获取了核心信息？
                - 剩余步骤是否真的"必需"？
                - 已执行步骤数是否过多（>= 5）？如果是，立即 respond

                **决策优先级口诀：** 
                "优先结束 > 保持不变 > 调整计划"
                "信息足够就响应，不要追求完美"
            """).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)

# 最终响应生成提示词
# 这个提示词用于“报告生成阶段”。
# 当 replanner 判断信息足够时，会把 past_steps 中所有执行结果交给模型，
# 让模型生成最终 Markdown 响应。
response_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent("""
                根据原始任务和已执行步骤的结果，生成一个全面的最终响应。

                响应要求：
                - 清晰、结构化
                - 基于实际数据，不要编造
                - 如果某些步骤失败，要诚实说明
                - 使用 Markdown 格式
            """).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)


async def replanner(state: PlanExecuteState) -> Dict[str, Any]:
    """
    重新规划节点：决定是继续、调整计划还是生成最终响应

    三种决策：
    1. continue - 继续执行当前计划
    2. replan - 调整计划（替换剩余步骤）
    3. respond - 生成最终响应

    输入 state 示例：
    {
        "input": "诊断当前系统是否存在告警",
        "plan": ["查询日志", "生成报告"],
        "past_steps": [
            ("查询当前活跃告警", "发现 CPUHigh 告警")
        ],
        "response": ""
    }

    输出可能是：
    1. continue:
       {}

    2. replan:
       {"plan": ["补充查询 CPU 指标", "查询最近错误日志"]}

    3. respond:
       {"response": "# 告警分析报告\\n..."}
    """
    logger.info("=== Replanner：重新规划 ===")

    input_text = state.get("input", "")
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])

    logger.info(f"剩余计划步骤: {len(plan)}")
    logger.info(f"已执行步骤: {len(past_steps)}")

    # ⚠️ 强制限制：如果已执行步骤过多，直接生成响应
    # 这是防止 Agent 无限循环的重要保护。
    # 如果 planner/replanner 一直追加步骤，最多执行 MAX_STEPS 次后强制生成报告。
    MAX_STEPS = 8
    if len(past_steps) >= MAX_STEPS:
        logger.warning(f"已执行 {len(past_steps)} 个步骤，超过最大限制 {MAX_STEPS}，强制生成最终响应")
        llm = ChatQwen(
            model=config.rag_model,
            api_key=config.dashscope_api_key,
            temperature=0
        )
        return await _generate_response(state, llm)

    # 获取可用工具列表
    # replanner 本身不执行工具，但需要知道有哪些工具可用，
    # 这样在 replan 时可以生成合理的新步骤。
    try:
        # 获取本地工具
        local_tools = [
            get_current_time,
            retrieve_knowledge
        ]

        # 获取 MCP 工具
        # 例如远程告警查询、日志查询、指标查询工具。
        mcp_client = await get_mcp_client_with_retry()
        mcp_tools = await mcp_client.get_tools()

        # 合并所有工具
        all_tools = local_tools + mcp_tools
        logger.info(f"可用工具数量: 本地 {len(local_tools)} + MCP {len(mcp_tools)}")

        # 格式化工具描述
        # tools_description 会被放进 replanner_prompt，让模型知道还能规划哪些工具步骤。
        tools_description = format_tools_description(all_tools)
    except Exception as e:
        logger.warning(f"获取工具列表失败: {e}")
        tools_description = "无法获取工具列表"

    # 创建 LLM
    # temperature=0 让决策更稳定，减少一会儿 continue、一会儿 replan 的随机性。
    llm = ChatQwen(
        model=config.rag_model,
        api_key=config.dashscope_api_key,
        temperature=0
    )

    # 格式化已执行的步骤
    # past_steps 是 executor 累积的执行历史：
    # [
    #     ("查询告警", "发现 CPUHigh 告警..."),
    #     ("查询日志", "发现 timeout 日志...")
    # ]
    # 这里把它转成文本，供 replanner 判断信息是否足够。
    steps_summary = "\n".join([
        f"步骤: {step}\n结果: {result[:300]}..."
        for step, result in past_steps
    ])

    # 如果还有剩余计划，进行决策
    # 有剩余 plan 时，replanner 要判断：继续执行、替换计划、还是提前生成最终响应。
    if plan:
        logger.info("还有剩余计划，评估下一步行动")

        # 结构化决策链：
        # prompt -> Qwen -> Act(action=..., new_steps=...)
        replanner_chain = replanner_prompt | llm.with_structured_output(Act)

        try:
            # 传给 replanner 的核心上下文：
            # 1. 原始任务是什么
            # 2. 已经执行了哪些步骤，结果是什么
            # 3. 当前还剩哪些步骤
            # 4. 已执行步数提示，用于引导模型不要无限执行
            messages = [
                ("user", f"原始任务: {input_text}"),
                ("user", f"已执行的步骤:\n{steps_summary}"),
                ("user", f"剩余计划: {', '.join(plan)}"),
                ("user", f"⚠️ 重要提示：已执行 {len(past_steps)} 个步骤，请优先考虑是否信息已足够生成响应（respond）")
            ]

            # 调用模型进行结构化决策，返回 Act 或 dict。
            act = await replanner_chain.ainvoke({
                "messages": messages,
                "tools_description": tools_description
            })

            # 处理返回结果
            # 正常情况下 act 是 Act 对象；
            # 为了兼容部分实现，也允许 dict。
            if isinstance(act, Act):
                action = act.action
                new_steps = act.new_steps
            else:
                # 如果返回的是字典
                action = act.get("action", "continue")  # type: ignore
                new_steps = act.get("new_steps", [])  # type: ignore

            logger.info(f"Replanner 决策: {action}")

            if action == "respond":
                logger.info("决定生成最终响应")
                # 返回 {"response": "..."}，后续 aiops_service 会把它作为最终报告事件发出去。
                return await _generate_response(state, llm)

            elif action == "replan":
                # ⚠️ 强制限制：新步骤数不能超过当前剩余步骤数
                # 避免模型不断扩展计划，导致执行链路越来越长。
                if len(new_steps) > len(plan):
                    logger.warning(
                        f"新步骤数 {len(new_steps)} > 剩余步骤数 {len(plan)}，"
                        f"强制截断为 {len(plan)} 个步骤"
                    )
                    new_steps = new_steps[:len(plan)]
                
                # ⚠️ 二次检查：如果已执行步骤 >= 5，禁止 replan
                # 已经执行较多步骤时，优先收敛输出报告，而不是继续改计划。
                if len(past_steps) >= 5:
                    logger.warning(f"已执行 {len(past_steps)} 个步骤，禁止重新规划，强制生成响应")
                    return await _generate_response(state, llm)
                
                logger.info(f"决定调整计划，新步骤数量: {len(new_steps)}")
                if new_steps:
                    # 替换剩余计划
                    # 返回 {"plan": new_steps} 后，LangGraph 会用新计划覆盖当前剩余 plan。
                    return {"plan": new_steps}
                else:
                    logger.warning("replan 但未提供新步骤，继续执行原计划")
                    return {}

            else:  # action == "continue"
                logger.info("决定继续执行当前计划")
                # 返回空 dict 表示不修改状态。
                # aiops_service 的条件边看到 state 里仍有 plan，会继续进入 executor。
                return {}  # 不修改状态，继续执行

        except Exception as e:
            logger.error(f"重新规划失败: {e}, 继续执行剩余计划")
            # 决策失败时不终止流程，默认继续执行原剩余计划。
            return {}

    else:
        # 没有剩余计划，生成最终响应
        # plan 已经为空时，说明 executor 已把所有步骤执行完。
        # 这时必须生成 response，否则流程没有最终答案。
        logger.info("计划已执行完毕，生成最终响应")
        return await _generate_response(state, llm)


async def _generate_response(state: PlanExecuteState, llm: ChatQwen) -> Dict[str, Any]:
    """生成最终响应

    这个函数把原始任务 input 和执行历史 past_steps 交给大模型，
    让模型生成最终 Markdown 报告。

    最终返回：
    {
        "response": "# 告警分析报告\\n..."
    }

    这个 response 会被 aiops_service.execute(...) 作为最终响应取出，
    并通过 report/complete 事件返回给前端。
    """
    logger.info("生成最终响应...")

    input_text = state.get("input", "")
    past_steps = state.get("past_steps", [])

    # 格式化执行历史
    # 把 past_steps 转成 Markdown 片段，让模型能清楚看到每一步的证据。
    execution_history = "\n\n".join([
        f"### 步骤: {step}\n**结果:**\n{result}"
        for step, result in past_steps
    ])

    # response_prompt | llm.with_structured_output(Response)
    # 表示要求模型输出 Response(response="...") 结构。
    response_gen = response_prompt | llm.with_structured_output(Response)

    try:
        # 这里传入的是最终报告生成所需的全部上下文：
        # 原始任务 + 所有执行步骤和结果。
        messages = [
            ("user", f"原始任务: {input_text}"),
            ("user", f"执行历史:\n{execution_history}"),
            ("user", "请基于以上信息生成全面的最终响应")
        ]

        # 调用大模型生成结构化最终响应。
        response_obj = await response_gen.ainvoke({"messages": messages})

        # 处理返回结果
        if isinstance(response_obj, Response):
            final_response = response_obj.response
        else:
            # 如果返回的是字典
            final_response = response_obj.get("response", "")  # type: ignore

        logger.info(f"最终响应生成完成，长度: {len(final_response)}")

        # 返回 LangGraph 状态增量：写入 response 字段。
        return {"response": final_response}

    except Exception as e:
        logger.error(f"生成响应失败: {e}")
        # 生成简单的后备响应
        # 如果最终报告生成失败，也要返回一个可读的兜底 Markdown，
        # 避免整个诊断流程没有最终输出。
        fallback_response = f"""# 任务执行结果

## 原始任务
{input_text}

## 执行的步骤
{_format_simple_steps(past_steps)}

## 说明
由于系统异常，无法生成完整响应。以上是已收集的信息。
"""
        return {"response": fallback_response}


def _format_simple_steps(past_steps: list) -> str:
    """格式化步骤列表（简单版）

    这是最终报告生成失败时的兜底格式化函数。
    它只展示每个步骤和结果预览，不再调用大模型。
    """
    if not past_steps:
        return "无"

    formatted = []
    for i, (step, result) in enumerate(past_steps, 1):
        result_preview = result[:200] + "..." if len(result) > 200 else result
        formatted.append(f"{i}. **{step}**\n   {result_preview}\n")

    return "\n".join(formatted)
