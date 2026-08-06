"""Supervisor 节点实现

Supervisor 是多 Agent 协作的调度中心：
1. 接收原始任务 + 已有 Worker 结果
2. 用 LLM 决定下一步派给哪个 Worker（或 FINISH）
3. 如果 FINISH，生成最终综合报告

Supervisor 不直接调用工具，只做路由决策和最终综合。
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger
from pydantic import BaseModel, Field

from app.agent.multi_agent.prompts import SUPERVISOR_PROMPT
from app.agent.multi_agent.tool_registry import format_worker_descriptions
from app.core.llm_factory import llm_factory


class SupervisorDecision(BaseModel):
    """Supervisor 的路由决策结构"""

    next_worker: str = Field(
        description=(
            "下一个调用的 Worker 名称，必须是以下之一："
            "'researcher', 'analyst', 'executor', 'writer', 'FINISH'"
        )
    )
    subtask: str = Field(
        description="分配给该 Worker 的子任务描述（清晰、具体）。当 next_worker='FINISH' 时可为空。"
    )
    reasoning: str = Field(description="做出这个决策的简短原因")


# Supervisor 决策提示词模板
supervisor_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUPERVISOR_PROMPT),
        (
            "human",
            """## 团队成员

{worker_desc}

## 用户任务

{task}

## 已完成的 Worker 结果

{worker_results_text}

## 请决策

请决定下一步派给哪个 Worker（或 FINISH 结束并生成报告）。""",
        ),
    ]
)


async def supervisor(state: dict[str, Any]) -> dict[str, Any]:
    """Supervisor 节点：分析任务和已有结果，决定下一步路由

    输入 state:
    {
        "task": "用户任务",
        "worker_results": [WorkerResult(...), ...],
    }

    输出（状态增量）:
    - 如果 next_worker != "FINISH":
      {"next": "researcher", "current_subtask": "查询 payment-service 告警"}
    - 如果 next_worker == "FINISH":
      {"next": "FINISH", "final_report": "# 最终报告\\n..."}
    """
    logger.info("=== 🧠 Supervisor 决策 ===")

    task = state.get("task", "")
    worker_results = state.get("worker_results", [])

    logger.info(f"用户任务: {task}")
    logger.info(f"已完成 Worker 调用: {len(worker_results)} 次")

    # 格式化已有结果
    worker_results_text = _format_worker_results(worker_results)

    # 格式化 Worker 角色描述
    worker_desc = format_worker_descriptions()

    # 强制终止：最多 6 轮 Worker 调用
    if len(worker_results) >= 6:
        logger.warning(f"已执行 {len(worker_results)} 轮，强制结束并生成报告")
        return await _generate_final_report(state)

    # 创建 LLM 并生成结构化决策
    llm = llm_factory.create_chat_model(temperature=0, streaming=False)
    decision_chain = supervisor_prompt | llm.with_structured_output(SupervisorDecision)

    try:
        decision: SupervisorDecision = await decision_chain.ainvoke(
            {
                "task": task,
                "worker_results_text": worker_results_text,
                "worker_desc": worker_desc,
            }
        )

        next_worker = decision.next_worker
        subtask = decision.subtask

        logger.info(f"Supervisor 决策: next={next_worker}, subtask={subtask[:80]}...")
        logger.info(f"决策原因: {decision.reasoning}")

        if next_worker == "FINISH":
            # 结束，生成最终报告
            return await _generate_final_report(state)
        else:
            # 路由到 Worker
            return {"next": next_worker, "current_subtask": subtask}

    except Exception as e:
        logger.error(f"Supervisor 决策失败: {e}", exc_info=True)
        # 决策失败时，如果有结果就生成报告，否则直接结束
        if worker_results:
            return await _generate_final_report(state)
        return {"next": "FINISH", "final_report": f"任务执行异常: {str(e)}"}


def _format_worker_results(worker_results: list) -> str:
    """格式化 Worker 执行结果为文本摘要"""
    if not worker_results:
        return ""

    lines = []
    for i, wr in enumerate(worker_results, 1):
        worker = wr.get("worker", "unknown")
        subtask = wr.get("subtask", "")
        result = wr.get("result", "")
        # 截断过长结果
        result_preview = result[:500] + "..." if len(result) > 500 else result
        lines.append(
            f"### 第 {i} 轮 — {worker}\n**子任务**: {subtask}\n**结果**:\n{result_preview}"
        )

    return "\n\n".join(lines)


async def _generate_final_report(state: dict[str, Any]) -> dict[str, str]:
    """生成最终综合报告

    将所有 Worker 的结果交给 LLM，生成一份结构化的 Markdown 报告。
    如果已经有 Writer 执行过，直接用 Writer 的结果作为最终报告。
    """
    logger.info("生成最终综合报告...")

    task = state.get("task", "")
    worker_results = state.get("worker_results", [])

    # 检查是否 Writer 已经生成过报告
    for wr in reversed(worker_results):
        if wr.get("worker") == "writer" and wr.get("result"):
            logger.info("Writer 已生成报告，直接使用")
            return {"next": "FINISH", "final_report": wr["result"]}

    # 没有 Writer 报告，Supervisor 自己综合
    worker_results_text = _format_worker_results(worker_results)

    llm = llm_factory.create_chat_model(temperature=0.3, streaming=False)

    messages = [
        SystemMessage(
            content=(
                "你是报告撰写专家。请根据以下 Worker 执行结果，"
                "为用户的原始任务生成一份结构化的 Markdown 报告。\n\n"
                "要求：\n"
                "- 基于实际数据，不要编造\n"
                "- 使用 Markdown 格式（标题、列表、表格）\n"
                "- 包含：问题概述、证据展示、根因分析、处理建议\n"
            )
        ),
        HumanMessage(
            content=(
                f"## 原始任务\n{task}\n\n## 执行结果\n{worker_results_text}\n\n请生成最终报告。"
            )
        ),
    ]

    try:
        response = await llm.ainvoke(messages)
        final_report = response.content if hasattr(response, "content") else str(response)
        logger.info(f"最终报告生成完成，长度: {len(final_report)}")
        return {"next": "FINISH", "final_report": final_report}
    except Exception as e:
        logger.error(f"生成报告失败: {e}")
        fallback = (
            f"# 任务执行结果\n\n"
            f"## 原始任务\n{task}\n\n"
            f"## 执行的步骤\n{_format_worker_results(worker_results)}\n\n"
            f"## 说明\n由于系统异常，无法生成完整报告。以上是已收集的信息。\n"
        )
        return {"next": "FINISH", "final_report": fallback}
