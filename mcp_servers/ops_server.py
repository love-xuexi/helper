"""运维操作 MCP Server

提供部署管理、运维操作、历史工单查询和 Runbook 检索功能。

工具列表：
- list_recent_deployments   — 列出近期部署记录
- get_deployment_detail     — 获取部署详情
- rollback_deployment       — 回滚部署（mock 操作）
- restart_service           — 重启服务实例（mock 操作）
- scale_service             — 扩缩容服务实例（mock 操作）
- search_historical_tickets — 搜索历史工单
- get_runbook               — 获取运维手册/SOP
"""

import functools
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.mock_data import (
    MOCK_DEPLOYMENTS,
    MOCK_HISTORICAL_TICKETS,
    MOCK_RUNBOOKS,
    fmt,
    get_deployments_by_service,
    get_service_by_name,
    get_tickets_by_service,
    now,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Ops_MCP_Server")

mcp = FastMCP("Ops")


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


# ============================================================
# 部署管理工具
# ============================================================


@mcp.tool()
@log_tool_call
def list_recent_deployments(
    service_name: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """列出近期的部署记录。

    Args:
        service_name: 服务名称筛选（可选，如 "notification-service"）
        limit: 返回条数限制（默认10）

    Returns:
        部署记录列表，包含部署ID、服务、版本、状态、部署时间、变更内容。
        notification-service 会有一条 failed 状态的部署记录。

    使用示例:
        # 查看所有近期部署
        list_recent_deployments()

        # 查看 notification-service 的部署
        list_recent_deployments(service_name="notification-service")
    """
    deployments = MOCK_DEPLOYMENTS.copy()

    if service_name:
        deployments = get_deployments_by_service(service_name)

    deployments = deployments[:limit]

    return {
        "total": len(deployments),
        "deployments": deployments,
        "query_time": fmt(now()),
    }


@mcp.tool()
@log_tool_call
def get_deployment_detail(deployment_id: str) -> dict[str, Any]:
    """获取指定部署的详细信息。

    Args:
        deployment_id: 部署ID（如 "DEP-2026-0089"）

    Returns:
        部署完整详情：版本、镜像、环境、状态、变更内容、错误信息、回滚可用性。
    """
    for dep in MOCK_DEPLOYMENTS:
        if dep["deployment_id"] == deployment_id:
            return dep
    return {"error": f"未找到部署记录: {deployment_id}", "deployment_id": deployment_id}


@mcp.tool()
@log_tool_call
def rollback_deployment(
    service_name: str,
    version: str | None = None,
) -> dict[str, Any]:
    """回滚服务部署到指定版本（mock 操作）。

    这是一个 mock 操作，不会真正执行回滚，仅返回模拟结果。

    Args:
        service_name: 服务名称（如 "notification-service"）
        version: 目标回滚版本（可选，默认回滚到上一个稳定版本）

    Returns:
        回滚操作结果，包含目标版本、状态、预计完成时间。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {
            "error": f"未找到服务: {service_name}",
            "service_name": service_name,
            "rolled_back": False,
        }

    # 查找最近的部署记录
    deps = get_deployments_by_service(service_name)
    if not deps:
        return {
            "error": f"服务 {service_name} 无部署记录",
            "service_name": service_name,
            "rolled_back": False,
        }

    latest_dep = deps[0]
    target_version = version or latest_dep.get("previous_version", "unknown")

    return {
        "service_name": service_name,
        "action": "rollback",
        "from_version": latest_dep["version"],
        "to_version": target_version,
        "status": "initiated",
        "initiated_at": fmt(now()),
        "estimated_completion_minutes": 5,
        "instances_to_update": svc["instances"],
        "message": f"已发起 {service_name} 从 {latest_dep['version']} 回滚到 {target_version} 的操作",
        "rolled_back": True,
    }


# ============================================================
# 运维操作工具
# ============================================================


@mcp.tool()
@log_tool_call
def restart_service(
    service_name: str,
    instance_id: str | None = None,
) -> dict[str, Any]:
    """重启服务实例（mock 操作）。

    这是一个 mock 操作，不会真正重启服务，仅返回模拟结果。

    Args:
        service_name: 服务名称（如 "notification-service"）
        instance_id: 指定实例ID（可选，未指定则重启所有实例）

    Returns:
        重启操作结果，包含目标实例、状态、预计完成时间。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {
            "error": f"未找到服务: {service_name}",
            "service_name": service_name,
            "restarted": False,
        }

    if instance_id:
        return {
            "service_name": service_name,
            "action": "restart",
            "target_instance": instance_id,
            "scope": "single_instance",
            "status": "initiated",
            "initiated_at": fmt(now()),
            "estimated_completion_seconds": 30,
            "message": f"已发起重启实例 {instance_id} 的操作",
            "restarted": True,
        }
    else:
        return {
            "service_name": service_name,
            "action": "restart",
            "target_instance": "all",
            "scope": "all_instances",
            "status": "initiated",
            "initiated_at": fmt(now()),
            "estimated_completion_seconds": 60,
            "total_instances": svc["instances"],
            "message": f"已发起重启 {service_name} 全部 {svc['instances']} 个实例的操作",
            "restarted": True,
        }


@mcp.tool()
@log_tool_call
def scale_service(
    service_name: str,
    target_instances: int,
) -> dict[str, Any]:
    """扩缩容服务实例数量（mock 操作）。

    这是一个 mock 操作，不会真正执行扩缩容，仅返回模拟结果。

    Args:
        service_name: 服务名称（如 "payment-service"）
        target_instances: 目标实例数量

    Returns:
        扩缩容操作结果，包含原实例数、目标实例数、操作类型（扩容/缩容）。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {
            "error": f"未找到服务: {service_name}",
            "service_name": service_name,
            "scaled": False,
        }

    current = svc["instances"]
    action_type = "scale_out" if target_instances > current else "scale_in"

    return {
        "service_name": service_name,
        "action": action_type,
        "current_instances": current,
        "target_instances": target_instances,
        "delta": abs(target_instances - current),
        "status": "initiated",
        "initiated_at": fmt(now()),
        "estimated_completion_seconds": 120,
        "message": f"已发起 {service_name} {'扩容' if action_type == 'scale_out' else '缩容'}：{current} → {target_instances} 实例",
        "scaled": True,
    }


# ============================================================
# 历史工单工具
# ============================================================


@mcp.tool()
@log_tool_call
def search_historical_tickets(
    service_name: str | None = None,
    issue_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """搜索历史运维工单，查找类似的过往故障和处理经验。

    Args:
        service_name: 服务名称筛选（可选，如 "payment-service"）
        issue_type: 问题类型筛选（可选，如 "cpu_high"/"memory_high"/"disk_high"/"service_unavailable"/"slow_response"）
        limit: 返回条数限制（默认20）

    Returns:
        历史工单列表，包含工单ID、标题、根因、解决方案、处理时长。

    使用示例:
        # 查找所有历史工单
        search_historical_tickets()

        # 查找 payment-service 的 CPU 相关工单
        search_historical_tickets(service_name="payment-service", issue_type="cpu_high")
    """
    tickets = MOCK_HISTORICAL_TICKETS.copy()

    if service_name:
        tickets = get_tickets_by_service(service_name)

    if issue_type:
        tickets = [t for t in tickets if t["issue_type"] == issue_type]

    tickets = tickets[:limit]

    return {
        "total": len(tickets),
        "tickets": tickets,
    }


# ============================================================
# Runbook 工具
# ============================================================


@mcp.tool()
@log_tool_call
def get_runbook(issue_type: str) -> dict[str, Any]:
    """根据问题类型获取运维手册（Runbook / SOP）。

    Args:
        issue_type: 问题类型，可选值：
            - "cpu_high": CPU 使用率过高
            - "memory_high": 内存使用率过高
            - "disk_high": 磁盘使用率过高
            - "service_unavailable": 服务不可用
            - "slow_response": 响应时间过长

    Returns:
        运维手册内容：排查步骤、常见原因、参考文档路径。

    使用示例:
        # 获取 CPU 高的排查手册
        get_runbook(issue_type="cpu_high")
    """
    runbook = MOCK_RUNBOOKS.get(issue_type)
    if not runbook:
        valid_types = list(MOCK_RUNBOOKS.keys())
        return {
            "error": f"未找到问题类型 '{issue_type}' 的运维手册",
            "issue_type": issue_type,
            "valid_types": valid_types,
        }

    return runbook


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8106)
