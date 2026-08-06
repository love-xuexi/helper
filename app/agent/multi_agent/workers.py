"""Worker 节点实现

每个 Worker 是一个 LangGraph 节点函数：
1. 从 state 读取 Supervisor 分配的 current_subtask
2. 获取该 Worker 的工具子集
3. LLM 决定调用哪些工具 → ToolNode 执行
4. 将工具结果交给 LLM 生成结果摘要
5. 返回 {worker_results: [WorkerResult(...)]]}

与 app/agent/aiops/executor.py 的设计理念相似，但：
- 每个 Worker 有独立的 system prompt
- 每个 Worker 只绑定自己的工具子集
- Worker 不做计划，直接执行子任务
"""

import functools
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from loguru import logger

from app.agent.mcp_client import get_mcp_client_with_retry
from app.agent.multi_agent.prompts import WORKER_PROFILES
from app.agent.multi_agent.state import MultiAgentState, WorkerResult
from app.agent.multi_agent.tool_registry import filter_tools_for_worker
from app.core.llm_factory import llm_factory
from app.tools import get_current_time, retrieve_knowledge


async def _get_all_tools() -> list:
    """获取全部可用工具（本地 + MCP），供各 Worker 筛选"""
    local_tools = [get_current_time, retrieve_knowledge]
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools = await mcp_client.get_tools()
    return local_tools + mcp_tools


def make_worker_node(worker_name: str):
    """创建一个 Worker 节点函数

    Args:
        worker_name: Worker 角色名（researcher/analyst/executor/writer）

    Returns:
        async worker_node(state) -> dict
    """
    profile = WORKER_PROFILES[worker_name]
    prompt = profile["prompt"]
    emoji = profile["emoji"]
    display_name = profile["name"]

    @functools.wraps(make_worker_node)
    async def worker_node(state: MultiAgentState) -> dict[str, Any]:
        """Worker 节点：执行 Supervisor 分配的子任务"""
        subtask = state.get("current_subtask", "")
        logger.info(f"=== {emoji} {display_name}（{worker_name}）执行子任务 ===")
        logger.info(f"子任务: {subtask}")

        if not subtask:
            logger.warning(f"{worker_name} 收到空子任务，跳过")
            return {
                "worker_results": [
                    WorkerResult(worker=worker_name, subtask=subtask, result="未收到子任务")
                ]
            }

        try:
            # 1. 获取工具并筛选
            all_tools = await _get_all_tools()
            worker_tools = filter_tools_for_worker(worker_name, all_tools)
            logger.info(f"{worker_name} 可用工具: {len(worker_tools)} 个")

            if not worker_tools:
                # 没有工具的 Worker（如 Writer 可能无工具时）直接生成文本
                llm = llm_factory.create_chat_model(temperature=0.3, streaming=False)
                messages = [
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"子任务: {subtask}\n\n请基于已有信息完成任务。"),
                ]
                response = await llm.ainvoke(messages)
                result = response.content if hasattr(response, "content") else str(response)
            else:
                # 2. LLM 绑定工具
                llm = llm_factory.create_chat_model(
                    temperature=0,
                    streaming=False,
                )
                llm_with_tools = llm.bind_tools(worker_tools)
                tool_node = ToolNode(worker_tools)

                # 3. LLM 决定调用哪些工具
                messages = [
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"请执行以下子任务: {subtask}"),
                ]
                llm_response = await llm_with_tools.ainvoke(messages)

                # 4. 如果有工具调用，执行工具
                if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
                    logger.info(
                        f"{worker_name} 调用了 {len(llm_response.tool_calls)} 个工具: "
                        f"{[tc['name'] for tc in llm_response.tool_calls]}"
                    )
                    messages.append(llm_response)
                    tool_messages = await tool_node.ainvoke({"messages": messages})
                    messages.extend(tool_messages["messages"])

                    # 5. 将工具结果交给 LLM 生成摘要
                    final_response = await llm_with_tools.ainvoke(messages)
                    result = (
                        final_response.content
                        if hasattr(final_response, "content")
                        else str(final_response)
                    )
                else:
                    # 没有工具调用，直接使用 LLM 输出
                    logger.info(f"{worker_name} 未调用工具，直接返回结果")
                    result = (
                        llm_response.content
                        if hasattr(llm_response, "content")
                        else str(llm_response)
                    )

            logger.info(f"{worker_name} 执行完成，结果长度: {len(result)}")

            return {
                "worker_results": [WorkerResult(worker=worker_name, subtask=subtask, result=result)]
            }

        except Exception as e:
            logger.error(f"{worker_name} 执行失败: {e}", exc_info=True)
            return {
                "worker_results": [
                    WorkerResult(worker=worker_name, subtask=subtask, result=f"执行失败: {str(e)}")
                ]
            }

    return worker_node


# 预创建 4 个 Worker 节点
researcher = None  # 延迟初始化
analyst = None
executor = None
writer = None


def get_worker_nodes():
    """初始化并返回 4 个 Worker 节点

    make_worker_node 是同步函数（只是返回 async 闭包），
    工具获取发生在每次 worker_node 被调用时。
    """
    global researcher, analyst, executor, writer

    if researcher is None:
        researcher = make_worker_node("researcher")
        analyst = make_worker_node("analyst")
        executor = make_worker_node("executor")
        writer = make_worker_node("writer")

    return {
        "researcher": researcher,
        "analyst": analyst,
        "executor": executor,
        "writer": writer,
    }
