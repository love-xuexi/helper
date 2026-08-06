"""告警管理 MCP Server

提供告警查询、详情、历史、规则配置和确认操作。

工具列表：
- list_active_alerts      — 列出当前活跃告警
- get_alert_detail        — 获取告警详情
- query_alert_history     — 查询历史告警
- get_alert_rules         — 获取告警规则配置
- acknowledge_alert       — 确认告警（mock 操作）
- get_alert_summary       — 告警概览统计

所有数据来自 mock_data.py，对应 5 个运维场景的活跃告警。
"""

import functools
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.mock_data import (
    MOCK_ALERT_HISTORY,
    MOCK_ALERT_RULES,
    MOCK_ALERTS,
    MOCK_SERVICES,
    fmt,
    get_alert_by_id,
    get_alerts_by_service,
    now,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Alert_MCP_Server")

mcp = FastMCP("Alert")


def log_tool_call(func):
    """装饰器：记录工具调用日志"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        method_name = func.__name__
        logger.info(f"调用方法: {method_name}")
        if kwargs:
            try:
                params_str = json.dumps(kwargs, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                params_str = str(kwargs)
            logger.info(f"参数: {params_str}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"方法 {method_name} 执行成功")
            return result
        except Exception as e:
            logger.error(f"方法 {method_name} 执行失败: {e}")
            raise

    return wrapper


# 已确认告警的内存存储（模拟状态变更）
_acknowledged_alerts: set[str] = set()


@mcp.tool()
@log_tool_call
def list_active_alerts(
    severity: str | None = None,
    service_name: str | None = None,
) -> dict[str, Any]:
    """列出当前所有活跃告警，支持按级别和服务名筛选。

    Args:
        severity: 告警级别筛选（critical/warning/urgent，可选）
            - critical: 严重（如 CPU/内存超限）
            - warning: 警告（如磁盘/响应时间超限）
            - urgent: 紧急（如服务不可用）
        service_name: 服务名称筛选（可选，如 "payment-service"）

    Returns:
        活跃告警列表，每条包含告警ID、名称、级别、目标服务、触发时间、当前值、阈值。

    使用示例:
        # 列出所有活跃告警
        list_active_alerts()

        # 只查看严重告警
        list_active_alerts(severity="critical")

        # 查看 payment-service 的告警
        list_active_alerts(service_name="payment-service")
    """
    alerts = MOCK_ALERTS.copy()

    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]

    if service_name:
        alerts = [a for a in alerts if a["service_name"] == service_name]

    # 标记确认状态
    for alert in alerts:
        alert["acknowledged"] = alert["alert_id"] in _acknowledged_alerts

    severity_counts = {"critical": 0, "warning": 0, "urgent": 0}
    for a in alerts:
        sev = a["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "total": len(alerts),
        "severity_summary": severity_counts,
        "alerts": alerts,
        "query_time": fmt(now()),
    }


@mcp.tool()
@log_tool_call
def get_alert_detail(alert_id: str) -> dict[str, Any]:
    """获取指定告警的详细信息。

    Args:
        alert_id: 告警ID（如 "ALT-2026-001"）

    Returns:
        告警完整详情：名称、级别、服务、触发时间、当前值、阈值、描述、关联告警。
    """
    alert = get_alert_by_id(alert_id)
    if not alert:
        return {"error": f"未找到告警: {alert_id}", "alert_id": alert_id}

    # 补充服务信息
    from mcp_servers.mock_data import get_service_by_name

    svc = get_service_by_name(alert["service_name"])
    alert_detail = alert.copy()
    alert_detail["service_info"] = svc
    alert_detail["acknowledged"] = alert_id in _acknowledged_alerts

    # 补充关联告警详情
    related = []
    for rel_name in alert.get("related_alerts", []):
        for a in MOCK_ALERTS:
            if a["alert_name"] == rel_name and a["alert_id"] != alert_id:
                related.append(
                    {
                        "alert_id": a["alert_id"],
                        "alert_name": a["alert_name"],
                        "service_name": a["service_name"],
                        "severity": a["severity"],
                    }
                )
    alert_detail["related_alert_details"] = related

    return alert_detail


@mcp.tool()
@log_tool_call
def query_alert_history(
    service_name: str | None = None,
    days: int = 90,
    limit: int = 20,
) -> dict[str, Any]:
    """查询历史告警记录（已恢复的告警）。

    Args:
        service_name: 服务名称筛选（可选）
        days: 查询天数范围（默认90天）
        limit: 返回条数限制（默认20）

    Returns:
        历史告警列表，包含告警名称、服务、级别、触发时间、恢复时间、持续时间、峰值。
    """
    history = MOCK_ALERT_HISTORY.copy()

    if service_name:
        history = [h for h in history if h["service_name"] == service_name]

    history = history[:limit]

    return {
        "total": len(history),
        "days_range": days,
        "history": history,
    }


@mcp.tool()
@log_tool_call
def get_alert_rules(service_name: str | None = None) -> dict[str, Any]:
    """获取告警规则配置。

    Args:
        service_name: 服务名称筛选（可选，未指定时返回全部规则）

    Returns:
        告警规则列表，包含指标、条件、阈值、持续时间、级别。
    """
    rules = MOCK_ALERT_RULES.copy()

    # 如果指定了服务名，只返回该服务相关的规则
    if service_name:
        # 获取该服务对应的活跃告警名称
        service_alert_names = {a["alert_name"] for a in get_alerts_by_service(service_name)}
        rules = [r for r in rules if r["rule_name"] in service_alert_names]

    return {
        "total": len(rules),
        "rules": rules,
    }


@mcp.tool()
@log_tool_call
def acknowledge_alert(alert_id: str, comment: str = "") -> dict[str, Any]:
    """确认（ACK）一条告警，表示已知晓并正在处理。

    这是一个 mock 操作，不会真正修改告警状态，仅记录确认信息。

    Args:
        alert_id: 告警ID（如 "ALT-2026-001"）
        comment: 确认备注（可选，如 "已通知运维团队处理"）

    Returns:
        确认结果，包含告警ID、确认时间、备注。
    """
    alert = get_alert_by_id(alert_id)
    if not alert:
        return {"error": f"未找到告警: {alert_id}", "alert_id": alert_id, "acknowledged": False}

    _acknowledged_alerts.add(alert_id)

    return {
        "alert_id": alert_id,
        "alert_name": alert["alert_name"],
        "service_name": alert["service_name"],
        "acknowledged": True,
        "acknowledged_at": fmt(now()),
        "comment": comment or "已确认",
        "message": f"告警 {alert_id} ({alert['alert_name']}) 已确认",
    }


@mcp.tool()
@log_tool_call
def get_alert_summary() -> dict[str, Any]:
    """获取当前告警概览统计（按级别、按服务汇总）。

    Returns:
        告警总数、按级别统计、按服务统计、最严重告警、受影响服务列表。
    """
    total = len(MOCK_ALERTS)
    by_severity: dict[str, int] = {}
    by_service: dict[str, int] = {}

    for alert in MOCK_ALERTS:
        sev = alert["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1

        svc = alert["service_name"]
        by_service[svc] = by_service.get(svc, 0) + 1

    # 最严重的告警（urgent > critical > warning）
    severity_order = {"urgent": 0, "critical": 1, "warning": 2}
    most_severe = min(MOCK_ALERTS, key=lambda a: severity_order.get(a["severity"], 99))

    # 受影响的服务列表
    affected_services = []
    for svc_name in by_service:
        svc_info = next((s for s in MOCK_SERVICES if s["service_name"] == svc_name), None)
        if svc_info:
            affected_services.append(
                {
                    "service_name": svc_name,
                    "display_name": svc_info["display_name"],
                    "alert_count": by_service[svc_name],
                    "health": svc_info["health"],
                }
            )

    unack_count = total - len(_acknowledged_alerts)

    return {
        "total_alerts": total,
        "unacknowledged": unack_count,
        "acknowledged": len(_acknowledged_alerts),
        "by_severity": by_severity,
        "by_service": by_service,
        "most_severe_alert": {
            "alert_id": most_severe["alert_id"],
            "alert_name": most_severe["alert_name"],
            "service_name": most_severe["service_name"],
            "severity": most_severe["severity"],
            "message": most_severe["message"],
        },
        "affected_services": affected_services,
        "summary_time": fmt(now()),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8005)
