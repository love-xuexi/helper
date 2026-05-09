"""
Executor 节点：执行单个步骤
基于 LangGraph 官方教程实现

这个文件定义了 AIOps Plan-Execute-Replan 工作流里的第二个节点：executor。
planner 节点负责生成 plan 列表，executor 节点每次只取 plan 里的第一个步骤来执行。

执行完成后，它会返回一个状态增量：
{
    "plan": ["剩余步骤1", "剩余步骤2"],
    "past_steps": [("刚执行的步骤", "执行结果")]
}

LangGraph 会把这个返回值合并回全局状态，之后 replanner 会根据 past_steps 判断是否继续执行。
"""

from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_qwq import ChatQwen
from langgraph.prebuilt import ToolNode
from loguru import logger

from app.config import config
from app.tools import get_current_time, retrieve_knowledge
from app.agent.mcp_client import get_mcp_client_with_retry
from .state import PlanExecuteState


async def executor(state: PlanExecuteState) -> Dict[str, Any]:
    """
    执行节点：执行计划中的下一个步骤
    
    使用 LangGraph 的 ToolNode 自动处理工具调用

    输入 state 示例：
    {
        "input": "诊断当前系统是否存在告警",
        "plan": [
            "使用告警查询工具查询当前活跃告警",
            "使用日志查询工具分析异常服务日志",
            "生成诊断报告"
        ],
        "past_steps": [],
        "response": ""
    }

    输出示例：
    {
        "plan": [
            "使用日志查询工具分析异常服务日志",
            "生成诊断报告"
        ],
        "past_steps": [
            (
                "使用告警查询工具查询当前活跃告警",
                "查询结果：当前存在 CPUHigh 告警，影响 payment-service"
            )
        ]
    }
    """
    logger.info("=== Executor：执行步骤 ===")

    plan = state.get("plan", [])

    # 如果计划为空，不执行
    # 这种情况通常表示 planner 没有生成步骤，或者所有步骤已经执行完。
    if not plan:
        logger.info("计划为空，跳过执行")
        return {}

    # 取出第一个步骤
    # executor 一次只执行一个步骤，不会一次性执行完整 plan。
    # 执行完后会通过 return {"plan": plan[1:]} 把已执行步骤从 plan 中移除。
    task = plan[0]
    logger.info(f"当前任务: {task}")

    try:
        # 获取本地工具
        # 这些工具可以被 LLM 调用：
        # get_current_time：获取当前时间
        # retrieve_knowledge：检索知识库经验/文档
        local_tools = [
            get_current_time,
            retrieve_knowledge
        ]

        # 获取 MCP 工具
        # MCP 工具来自外部 MCP Server，例如告警查询、日志查询、指标查询等。
        # get_mcp_client_with_retry() 会创建/复用带重试能力的 MCP Client。
        mcp_client = await get_mcp_client_with_retry()
        mcp_tools = await mcp_client.get_tools()
        logger.info(f"可用工具数量: 本地 {len(local_tools)} + MCP {len(mcp_tools)}")

        # 合并所有工具
        # all_tools 会同时提供给 LLM 和 ToolNode：
        # - LLM 用它来决定要调用哪个工具
        # - ToolNode 用它来真正执行工具调用
        all_tools = local_tools + mcp_tools

        # 创建 LLM（绑定工具）
        # bind_tools(all_tools) 后，模型就可以在回复里生成 tool_calls。
        # 注意：模型此时只是“决定调用工具”，真正执行工具的是下面的 ToolNode。
        llm = ChatQwen(
            model=config.rag_model,
            api_key=config.dashscope_api_key,
            temperature=0
        )
        llm_with_tools = llm.bind_tools(all_tools)

        # 创建工具节点（自动执行工具调用）
        # ToolNode 接收包含 tool_calls 的 AIMessage，
        # 然后根据 tool name 找到对应工具并执行，最后返回 ToolMessage。
        tool_node = ToolNode(all_tools)

        # 构建消息（只包含当前步骤，避免原始任务干扰）
        # 这里有意只让模型关注当前 task，而不是整个原始任务。
        # 这样 executor 每次只完成一个明确步骤，便于后续 replanner 评估。
        messages = [
            SystemMessage(content="""你是一个能力强大的助手，负责执行具体的任务步骤。

你可以使用各种工具来完成任务。对于每个步骤：
1. 理解步骤的目标
2. 选择合适的工具，如果已经指定了工具，则使用指定的工具
3. 调用工具获取信息
4. 返回执行结果

注意：
- 如果工具调用失败，请说明失败原因
- 不要编造数据，只返回实际获取的信息
- 执行结果要清晰、准确
- 专注于当前步骤，不要考虑其他任务"""),
            HumanMessage(content=f"请执行以下任务: {task}")
        ]

        # 第一步：LLM 决定是否调用工具
        # 返回的 llm_response 可能有两种情况：
        # 1. 带 tool_calls：表示模型认为需要调用工具
        # 2. 不带 tool_calls：表示模型直接给出了执行结果
        llm_response = await llm_with_tools.ainvoke(messages)
        logger.info(f"LLM 响应类型: {type(llm_response)}")

        # 第二步：如果有工具调用，执行工具
        if hasattr(llm_response, "tool_calls") and llm_response.tool_calls:
            logger.info(f"检测到 {len(llm_response.tool_calls)} 个工具调用")
            
            # 使用 ToolNode 自动执行工具
            # 先把 AIMessage 追加到 messages 中，因为 ToolNode 需要从最后的 AIMessage 里读取 tool_calls。
            messages.append(llm_response)
            # tool_messages 示例：
            # {
            #     "messages": [
            #         ToolMessage(content="查询结果：发现 CPUHigh 告警", tool_call_id="...")
            #     ]
            # }
            tool_messages = await tool_node.ainvoke({"messages": messages})
            
            # 第三步：将工具结果返回给 LLM 生成最终答案
            # 工具执行结果本身通常比较原始。
            # 这里再让 LLM 基于工具结果整理成当前步骤的自然语言执行结果。
            messages.extend(tool_messages["messages"])
            final_response = await llm_with_tools.ainvoke(messages)
            result = final_response.content if hasattr(final_response, 'content') else str(final_response)
        else:
            # 没有工具调用，直接使用 LLM 的输出
            # 例如某些步骤只是“总结已有信息”，不一定需要工具。
            logger.info("LLM 未调用工具，直接返回结果")
            result = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)

        logger.info(f"步骤执行完成，结果长度: {len(result)}")

        # 返回更新：移除已执行的步骤，添加执行历史
        # 这里返回的是 LangGraph 状态增量，不是直接返回给用户的最终报告。
        # plan[1:] 表示剩余待执行步骤。
        # past_steps 记录本次执行的步骤和结果，后续 replanner 会基于它判断是否继续。
        return {
            "plan": plan[1:],  # 移除第一个步骤
            "past_steps": [(task, result)],  # 使用 operator.add 追加
        }

    except Exception as e:
        logger.error(f"执行步骤失败: {e}", exc_info=True)
        # 即使当前步骤执行失败，也把失败信息写入 past_steps，并移除当前步骤。
        # 这样 replanner 可以看到失败原因，决定是否补充新步骤或生成带失败说明的报告。
        return {
            "plan": plan[1:],
            "past_steps": [(task, f"执行失败: {str(e)}")],
        }
