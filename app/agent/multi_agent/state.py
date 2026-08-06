"""多 Agent 协作状态定义

Supervisor-Worker 模式的状态结构。
与现有 app/agent/aiops/state.py 中的 PlanExecuteState 完全独立，互不影响。
"""

import operator
from typing import Annotated, TypedDict


class WorkerResult(TypedDict):
    """单个 Worker 的执行结果"""

    worker: str  # "researcher" / "analyst" / "executor" / "writer"
    subtask: str  # Supervisor 分配的子任务描述
    result: str  # Worker 返回的结果摘要


class SupervisorDecision(TypedDict):
    """Supervisor 的路由决策"""

    next_worker: str  # "researcher" / "analyst" / "executor" / "writer" / "FINISH"
    subtask: str  # 分配给下一个 Worker 的子任务
    reasoning: str  # 为什么选择这个 Worker


class MultiAgentState(TypedDict):
    """多 Agent 协作图的全局状态"""

    # 原始用户任务
    task: str

    # 各 Worker 完成的结果列表（operator.add 追加式更新）
    worker_results: Annotated[list[WorkerResult], operator.add]

    # Supervisor 当前分配的子任务（供 Worker 读取）
    current_subtask: str

    # 最终综合报告
    final_report: str

    # 路由目标（供条件边判断）
    next: str
