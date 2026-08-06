"""多 Agent 协作框架

Supervisor-Worker 模式，基于 LangGraph 实现。

图结构：
    START → supervisor → [researcher|analyst|executor|writer|FINISH]
                                ↓ (Worker 执行完)
                           supervisor → ... → FINISH → END

Supervisor 是路由中心，根据任务和已有结果决定下一步派给哪个 Worker。
Worker 执行完自动回到 Supervisor，形成循环。
当 Supervisor 决定 FINISH 时，生成最终报告并结束。

与 app/agent/aiops/（单 Agent Plan-Execute-Replan）完全独立，互不影响。
"""

from typing import Any

from langgraph.graph import END, StateGraph
from loguru import logger

from app.agent.multi_agent.state import MultiAgentState
from app.agent.multi_agent.supervisor import supervisor
from app.agent.multi_agent.workers import get_worker_nodes

# 节点名称常量
NODE_SUPERVISOR = "supervisor"
NODE_RESEARCHER = "researcher"
NODE_ANALYST = "analyst"
NODE_EXECUTOR = "executor"
NODE_WRITER = "writer"


def build_multi_agent_graph(checkpointer: Any = None):
    """构建多 Agent 协作图

    Args:
        checkpointer: LangGraph checkpointer（与单 Agent 共用 session 持久化）

    Returns:
        编译后的 LangGraph 图
    """
    logger.info("构建多 Agent 协作图...")

    workflow = StateGraph(MultiAgentState)

    # 添加 Supervisor 节点
    workflow.add_node(NODE_SUPERVISOR, supervisor)

    # 添加 Worker 节点
    worker_nodes = get_worker_nodes()
    for name, node_fn in worker_nodes.items():
        workflow.add_node(name, node_fn)

    # 设置入口点
    workflow.set_entry_point(NODE_SUPERVISOR)

    # Supervisor 的条件边：根据 next 字段路由
    def route_from_supervisor(state: MultiAgentState) -> str:
        """根据 Supervisor 的决策路由到对应 Worker 或 FINISH"""
        next_node = state.get("next", "FINISH")

        if next_node in (NODE_RESEARCHER, NODE_ANALYST, NODE_EXECUTOR, NODE_WRITER):
            return next_node

        # FINISH 或无效值 → END
        return END

    workflow.add_conditional_edges(
        NODE_SUPERVISOR,
        route_from_supervisor,
        {
            NODE_RESEARCHER: NODE_RESEARCHER,
            NODE_ANALYST: NODE_ANALYST,
            NODE_EXECUTOR: NODE_EXECUTOR,
            NODE_WRITER: NODE_WRITER,
            END: END,
        },
    )

    # 所有 Worker 执行完后回到 Supervisor
    for worker_name in [NODE_RESEARCHER, NODE_ANALYST, NODE_EXECUTOR, NODE_WRITER]:
        workflow.add_edge(worker_name, NODE_SUPERVISOR)

    # 编译
    compiled = workflow.compile(checkpointer=checkpointer)
    logger.info("多 Agent 协作图构建完成")
    return compiled


__all__ = [
    "build_multi_agent_graph",
    "supervisor",
    "get_worker_nodes",
    "MultiAgentState",
]
