"""工具按 Worker 角色分组注册表

将 4 个 MCP Server 的 41 个工具按角色分配给 4 个 Worker。
每个 Worker 只看到自己相关的工具，减少 LLM 上下文噪声，提高工具调用准确率。

工具名称对应 MCP Server 中 @mcp.tool() 注册的函数名。
"""

from typing import Any

from langchain_core.tools import BaseTool

# ============================================================
# 各 Worker 的工具名称清单
# ============================================================

WORKER_TOOL_NAMES: dict[str, list[str]] = {
    "researcher": [
        # Alert 工具
        "list_active_alerts",
        "get_alert_detail",
        "get_alert_summary",
        "query_alert_history",
        # Monitor 服务管理工具
        "list_all_services",
        "get_service_info",
        "query_service_health",
        "get_service_instances",
        "get_service_topology",
        # CLS 日志工具
        "search_service_logs",
        "search_log",
        "search_system_events",
        "get_log_statistics",
        # DuckDuckGo 联网搜索工具
        "web_search",
        "web_search_suggest",
        # 本地工具
        "get_current_time",
    ],
    "analyst": [
        # Monitor 指标工具
        "query_cpu_metrics",
        "query_memory_metrics",
        "query_disk_metrics",
        "query_network_metrics",
        "query_process_list",
        "query_gc_metrics",
        "query_response_time_metrics",
        "query_error_rate_metrics",
        "query_qps_metrics",
        "query_database_metrics",
        "query_cache_metrics",
        # CLS 分析工具
        "analyze_log_pattern",
        "query_slow_sql",
        # Alert 规则
        "get_alert_rules",
    ],
    "executor": [
        # Ops 操作工具
        "rollback_deployment",
        "restart_service",
        "scale_service",
        "get_runbook",
        # Alert 确认
        "acknowledge_alert",
    ],
    "writer": [
        # Ops 参考
        "get_runbook",
        # 本地知识检索
        "retrieve_knowledge",
    ],
}

# Supervisor 不直接调用工具
SUPERVISOR_TOOLS: list[str] = []


def get_worker_tool_names(worker_name: str) -> list[str]:
    """获取指定 Worker 的工具名称列表"""
    return WORKER_TOOL_NAMES.get(worker_name, [])


def filter_tools_for_worker(worker_name: str, all_tools: list[BaseTool]) -> list[Any]:
    """从全部工具列表中筛选属于该 Worker 的工具子集

    Args:
        worker_name: Worker 角色名（researcher/analyst/executor/writer）
        all_tools: 全部可用工具列表（本地 + MCP）

    Returns:
        该 Worker 的工具子集
    """
    wanted_names = set(get_worker_tool_names(worker_name))
    return [t for t in all_tools if t.name in wanted_names]


def format_worker_descriptions() -> str:
    """生成各 Worker 能力描述文本（供 Supervisor prompt 使用）"""
    from app.agent.multi_agent.prompts import WORKER_PROFILES

    lines = []
    for name, profile in WORKER_PROFILES.items():
        tool_count = len(WORKER_TOOL_NAMES.get(name, []))
        lines.append(
            f"- {name}（{profile['emoji']} {profile['name']}）: "
            f"{profile['description']}，可用 {tool_count} 个工具"
        )
    return "\n".join(lines)
