"""
Planner 节点：制定执行计划
基于 LangGraph 官方教程实现

这个文件定义了 AIOps Plan-Execute-Replan 工作流里的第一个节点：planner。
planner 的职责不是直接执行工具，也不是直接生成最终报告，
而是根据用户任务、知识库经验、可用工具列表，生成一组“接下来应该怎么排查/执行”的步骤。

最终输出会写回 LangGraph 状态中的 plan 字段，例如：
{
    "plan": [
        "使用 get_current_time 获取当前诊断时间",
        "使用告警查询工具查询当前活跃告警",
        "使用日志查询工具分析异常服务最近日志",
        "综合告警、指标和日志生成诊断报告"
    ]
}
"""

from textwrap import dedent
from typing import Dict, Any, List
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from loguru import logger

from app.core.llm_factory import llm_factory
from app.tools import get_current_time, retrieve_knowledge
from app.agent.mcp_client import get_mcp_client_with_retry
from .state import PlanExecuteState
from .utils import format_tools_description


class Plan(BaseModel):
    """计划的输出格式

    这是给大模型的“结构化输出约束”。
    planner 不是让模型随便输出一段自然语言，而是要求模型输出一个符合 Plan 结构的对象：

    Plan(
        steps=[
            "步骤1：...",
            "步骤2：..."
        ]
    )

    后面 llm.with_structured_output(Plan) 会强制模型尽量按照这个 schema 返回。
    """
    steps: List[str] = Field(
        description="完成任务所需的不同步骤。这些步骤应该按顺序执行，每一步都建立在前一步的基础上。"
    )


# Planner 提示词
# 这个提示词告诉模型：
# 1. 你现在是规划者，不是执行者
# 2. 你可以参考可用工具列表，但不要真正调用工具
# 3. 如果知识库里有经验文档，要参考经验文档来制定步骤
# 4. 输出应该是清晰、可执行、有顺序的计划
planner_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            dedent("""
                作为一个专家级别的规划者，你需要将复杂的任务分解为可执行的步骤。

                可用工具列表（用于制定计划时参考）：

                {tools_description}

                注意：你的职责是制定计划，实际的工具调用由 Executor 负责执行。

                {experience_context}

                对于给定的任务，请创建一个简单的、逐步的计划来完成它。计划应该：
                - 将任务分解为逻辑上独立的步骤
                - 每个步骤应该明确使用哪些工具(如果需要工具的话)来获取信息, 最好能同时提供工具执行所需要的参数
                - 步骤之间应该有清晰的依赖关系
                - 步骤描述要具体、可操作
                - **如果有相关经验文档，请参考其中的方法和步骤制定计划**

                示例输入："分析当前系统的性能问题"
                示例输出（假设有对应工具）：
                步骤1: 使用 get_metrics 工具收集系统的 CPU 和内存使用情况
                步骤2: 使用 query_logs 工具检查最近的错误日志
                步骤3: 使用 query_database 工具分析慢查询日志
                步骤4: 综合以上信息生成性能分析报告
            """).strip(),
        ),
        ("placeholder", "{messages}"),
    ]
)


async def planner(state: PlanExecuteState) -> Dict[str, Any]:
    """
    规划节点：根据用户输入生成执行计划

    流程：
    1. 先查询内部文档，获取相关经验和最佳实践
    2. 基于经验文档和可用工具制定执行计划

    输入 state 示例：
    {
        "input": "诊断当前系统是否存在告警",
        "plan": [],
        "past_steps": [],
        "response": ""
    }

    输出示例：
    {
        "plan": [
            "使用告警查询工具查询当前活跃告警",
            "针对活跃告警查询相关服务日志",
            "分析监控指标和日志证据",
            "生成 Markdown 告警诊断报告"
        ]
    }

    这个返回值会被 LangGraph 合并回全局状态，供 executor 节点继续使用。
    """
    logger.info("=== Planner：制定执行计划 ===")

    input_text = state.get("input", "")
    logger.info(f"用户输入: {input_text}")

    try:
        # 步骤1: 查询内部文档获取相关经验
        # 这里先走一次 RAG 检索，不是为了回答用户，而是为了给 planner 提供“历史经验”。
        # 例如知识库里可能有“CPU 告警排查 SOP”、“接口超时排查流程”等文档。
        logger.info("查询内部文档，寻找相关经验...")
        experience_docs = ""
        try:
            # retrieve_knowledge 使用 response_format="content_and_artifact"
            # ainvoke() 只返回 content（字符串），不是元组
            # 返回示例：
            # "CPU 告警排查经验：先查 CPU 指标，再查线程数，再查错误日志..."
            context_str = await retrieve_knowledge.ainvoke({"query": input_text})
            if context_str and context_str.strip():
                experience_docs = context_str
                logger.info(f"找到相关经验文档，长度: {len(experience_docs)}")
            else:
                logger.info("未找到相关经验文档")
        except Exception as e:
            logger.warning(f"查询内部文档失败: {e}")

        # 步骤2: 获取可用工具列表
        # 获取本地工具
        # 本地工具是项目里直接定义的 LangChain Tool。
        # get_current_time：获取当前时间
        # retrieve_knowledge：查询本项目知识库
        local_tools = [
            get_current_time,
            retrieve_knowledge
        ]

        # 获取 MCP 工具
        # MCP 工具来自外部 MCP Server。
        # get_mcp_client_with_retry() 会返回带重试拦截器的 MCP Client；
        # get_tools() 会把远程 MCP Server 暴露的工具转换成 LangChain 可用的工具对象。
        mcp_client = await get_mcp_client_with_retry()
        mcp_tools = await mcp_client.get_tools()

        # 合并所有工具
        # planner 只会“看”这些工具的名称和描述来制定计划。
        # 真正调用工具的是 executor 节点，不是 planner 节点。
        all_tools = local_tools + mcp_tools
        logger.info(f"可用工具数量: 本地 {len(local_tools)} + MCP {len(mcp_tools)}")

        # 格式化工具描述
        # tools_description 会被插入到 planner_prompt 的 {tools_description} 位置。
        # 这样模型知道当前有哪些工具可用，以及每个工具大概能做什么。
        tools_description = format_tools_description(all_tools)

        # 步骤3: 格式化经验文档上下文
        # 如果知识库检索到了相关经验，就把经验作为额外上下文塞进 prompt。
        # 这样生成出来的计划会更像“基于已有 SOP 的排查步骤”，而不是模型凭空规划。
        if experience_docs:
            experience_context = dedent(f"""
                ## 相关经验文档

                以下是从知识库中检索到的相关经验和最佳实践，请参考这些经验制定执行计划：

                {experience_docs}

                ---
            """).strip()
        else:
            experience_context = ""

        # 步骤4: 创建 LLM 并生成计划
        # temperature=0 表示尽量稳定输出，减少同样输入每次生成不同计划的概率。
        llm = llm_factory.create_chat_model(
            temperature=0,
            streaming=False,
        )

        # planner_prompt | llm.with_structured_output(Plan)
        # 表示先把 prompt 渲染成消息，再调用 Qwen，并要求输出符合 Plan schema。
        planner_chain = planner_prompt | llm.with_structured_output(Plan)

        # 调用 LLM 生成计划
        # 传入三类信息：
        # 1. messages：用户原始任务
        # 2. tools_description：当前可用工具清单
        # 3. experience_context：知识库检索到的历史经验
        plan_result = await planner_chain.ainvoke({
            "messages": [("user", input_text)],
            "tools_description": tools_description,
            "experience_context": experience_context
        })

        # 提取步骤列表
        # 正常情况下 plan_result 是 Plan 对象；
        # 为了兼容某些实现返回 dict，这里也做了字典兜底。
        if isinstance(plan_result, Plan):
            plan_steps = plan_result.steps
        else:
            # 如果返回的是字典，提取 steps 字段
            plan_steps = plan_result.get("steps", [])  # type: ignore

        logger.info(f"计划已生成，共 {len(plan_steps)} 个步骤")
        for i, step in enumerate(plan_steps, 1):
            logger.info(f"  步骤{i}: {step}")

        # LangGraph 节点函数返回的是“状态增量”。
        # 这里返回 {"plan": plan_steps} 后，LangGraph 会把 plan 字段更新到全局状态里。
        return {"plan": plan_steps}

    except Exception as e:
        logger.error(f"生成计划失败: {e}", exc_info=True)
        # 返回一个默认计划
        # 如果知识库、MCP 工具或 LLM 调用失败，仍然返回一个最基础的兜底计划，
        # 避免整个 Plan-Execute-Replan 流程在 planner 阶段直接中断。
        return {
            "plan": [
                "收集相关信息",
                "分析数据",
                "生成报告"
            ]
        }
