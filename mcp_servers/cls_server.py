"""腾讯云 CLS (Cloud Log Service) MCP Server

提供日志查询、检索和分析功能，包括：
- 日志主题查询（按服务名/主题名）
- 日志搜索（按 topic_id / 服务名）
- 日志模式分析（错误频率、异常聚类）
- 慢 SQL 查询
- 系统事件查询（OOM / restart / crash）
- 日志级别统计

所有日志数据来自 mock_data.py，与告警场景形成证据链。
"""

import functools
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.mock_data import (
    MOCK_LOG_TOPICS,
    MOCK_SLOW_SQLS,
    MOCK_SYSTEM_EVENTS,
    get_logs_by_service,
    get_service_by_name,
    get_slow_sqls_by_service,
    get_system_events_by_service,
    minutes_ago,
    now,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CLS_MCP_Server")

mcp = FastMCP("CLS")


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


def _parse_time(time_str: str | None, default_offset_hours: int = 0) -> datetime:
    """解析时间字符串或返回默认时间"""
    if time_str:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return now() + timedelta(hours=default_offset_hours)


# ============================================================
# 基础工具
# ============================================================


@mcp.tool()
@log_tool_call
def get_current_timestamp() -> int:
    """获取当前时间戳（毫秒）。

    用于 search_log 的 start_time / end_time 参数。
    计算 N 分钟前时间戳：current - (N * 60 * 1000)。

    Returns:
        当前毫秒时间戳，例如: 1708012345000
    """
    return int(now().timestamp() * 1000)


@mcp.tool()
@log_tool_call
def get_region_code_by_name(region_name: str) -> dict[str, Any]:
    """根据地区名称获取地区代码。

    Args:
        region_name: 地区名称（北京/上海/广州）

    Returns:
        地区代码及可用性信息。
    """
    region_mapping = {
        "北京": {"region_code": "ap-beijing", "region_name": "北京", "available": True},
        "上海": {"region_code": "ap-shanghai", "region_name": "上海", "available": True},
        "广州": {"region_code": "ap-guangzhou", "region_name": "广州", "available": True},
    }
    return region_mapping.get(
        region_name,
        {
            "region_code": None,
            "region_name": region_name,
            "available": False,
            "error": f"未找到地区: {region_name}",
        },
    )


@mcp.tool()
@log_tool_call
def get_topic_info_by_name(topic_name: str, region_code: str | None = None) -> dict[str, Any]:
    """根据主题名称搜索日志主题信息。

    Args:
        topic_name: 主题名称
        region_code: 地区代码（可选）

    Returns:
        主题ID、名称、所属地区、日志类型。
    """
    for topic in MOCK_LOG_TOPICS:
        if topic["topic_name"] == topic_name:
            if region_code is None or topic["region_code"] in (region_code, "all"):
                return topic
    return {
        "topic_id": None,
        "topic_name": topic_name,
        "error": f"未找到主题: {topic_name}",
    }


@mcp.tool()
@log_tool_call
def search_topic_by_service_name(
    service_name: str, region_code: str | None = None, fuzzy: bool = True
) -> dict[str, Any]:
    """根据服务名称搜索相关的日志主题。

    Args:
        service_name: 服务名称（如 "payment-service"）
        region_code: 地区代码（可选）
        fuzzy: 是否模糊搜索（默认 True）

    Returns:
        匹配的日志主题列表。
    """
    matched = []
    for topic in MOCK_LOG_TOPICS:
        svc = topic.get("service_name")
        if svc is None:
            continue
        if region_code and topic["region_code"] not in (region_code, "all"):
            continue
        if fuzzy:
            if service_name.lower() in svc.lower() or svc.lower() in service_name.lower():
                matched.append(topic)
        else:
            if svc == service_name:
                matched.append(topic)

    return {
        "total": len(matched),
        "topics": matched,
        "query": {"service_name": service_name, "region_code": region_code, "fuzzy": fuzzy},
        "message": f"找到 {len(matched)} 个匹配的日志主题"
        if matched
        else f"未找到服务 '{service_name}' 的日志主题",
    }


@mcp.tool()
@log_tool_call
def search_log(
    topic_id: str, start_time: int, end_time: int, query: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """基于 topic_id 搜索日志。

    Args:
        topic_id: 主题ID（如 "topic-001"）
        start_time: 开始时间戳（毫秒）
        end_time: 结束时间戳（毫秒）
        query: 查询语句（可选，如 "level:ERROR"）
        limit: 返回条数限制（默认100）

    Returns:
        日志列表，每条包含 timestamp、level、message。
        根据 topic_id 返回与告警场景相关的日志内容。
    """
    # 查找 topic 对应的服务
    topic = None
    for t in MOCK_LOG_TOPICS:
        if t["topic_id"] == topic_id:
            topic = t
            break

    if not topic:
        return {
            "topic_id": topic_id,
            "total": 0,
            "logs": [],
            "error": f"主题不存在: {topic_id}",
        }

    # 系统级主题
    if topic["topic_name"] == "system-metrics":
        return {
            "topic_id": topic_id,
            "total": 3,
            "logs": [
                {
                    "timestamp": minutes_ago(28),
                    "level": "WARN",
                    "message": "payment-service CPU 使用率 95.2%，超过阈值 80%",
                },
                {
                    "timestamp": minutes_ago(42),
                    "level": "WARN",
                    "message": "data-sync-service 内存使用率 88.4%，超过阈值 85%",
                },
                {
                    "timestamp": minutes_ago(55),
                    "level": "WARN",
                    "message": "api-gateway 磁盘使用率 87.3%",
                },
            ],
            "took_ms": 45,
        }

    if topic["topic_name"] == "system-events":
        return {
            "topic_id": topic_id,
            "total": len(MOCK_SYSTEM_EVENTS),
            "logs": [
                {
                    "timestamp": e["timestamp"],
                    "level": e["severity"].upper(),
                    "message": e["message"],
                }
                for e in MOCK_SYSTEM_EVENTS
            ],
            "took_ms": 50,
        }

    if topic["topic_name"] == "database-slow-query":
        return {
            "topic_id": topic_id,
            "total": len(MOCK_SLOW_SQLS),
            "logs": [
                {
                    "timestamp": s["timestamp"],
                    "level": "WARN",
                    "message": f"慢SQL: {s['query'][:80]}... 耗时 {s['execution_time_ms']}ms",
                }
                for s in MOCK_SLOW_SQLS
            ],
            "took_ms": 40,
        }

    # 服务级主题：返回该服务的 mock 日志
    svc_name = topic.get("service_name")
    if svc_name:
        logs = get_logs_by_service(svc_name)
        # 按 query 过滤
        if query:
            ql = query.lower()
            logs = [
                log for log in logs if ql in log["message"].lower() or ql in log["level"].lower()
            ]
        logs = logs[:limit]
        return {
            "topic_id": topic_id,
            "topic_name": topic["topic_name"],
            "service_name": svc_name,
            "start_time": start_time,
            "end_time": end_time,
            "query": query,
            "total": len(logs),
            "logs": logs,
            "took_ms": 50,
            "message": f"成功查询 {len(logs)} 条日志",
        }

    return {"topic_id": topic_id, "total": 0, "logs": [], "message": "无日志数据"}


# ============================================================
# 高级日志分析工具（新增）
# ============================================================


@mcp.tool()
@log_tool_call
def search_service_logs(
    service_name: str,
    log_level: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """按服务名称搜索日志，支持日志级别和关键词筛选。

    Args:
        service_name: 服务名称（如 "payment-service"）
        log_level: 日志级别筛选（INFO/WARN/ERROR/FATAL，可选）
        keyword: 关键词筛选（可选，如 "timeout"）
        limit: 返回条数限制（默认50）

    Returns:
        日志列表，包含 timestamp、level、message、instance。
        数据与该服务的告警场景一致。

    使用示例:
        # 查询 payment-service 的所有 ERROR 日志
        search_service_logs(service_name="payment-service", log_level="ERROR")

        # 查询 data-sync-service 包含 "OOM" 的日志
        search_service_logs(service_name="data-sync-service", keyword="OOM")
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name, "logs": []}

    logs = get_logs_by_service(service_name)

    # 级别筛选
    if log_level:
        log_level_upper = log_level.upper()
        logs = [log for log in logs if log["level"].upper() == log_level_upper]

    # 关键词筛选
    if keyword:
        kw = keyword.lower()
        logs = [log for log in logs if kw in log["message"].lower()]

    logs = logs[:limit]

    return {
        "service_name": service_name,
        "log_level": log_level,
        "keyword": keyword,
        "total": len(logs),
        "logs": logs,
        "message": f"查询到 {len(logs)} 条日志",
    }


@mcp.tool()
@log_tool_call
def analyze_log_pattern(
    service_name: str,
    time_range_minutes: int = 60,
) -> dict[str, Any]:
    """分析服务日志模式，返回错误频率和异常模式聚类。

    Args:
        service_name: 服务名称（如 "payment-service"）
        time_range_minutes: 分析时间范围（分钟，默认60）

    Returns:
        日志级别分布、错误频率 Top N、异常模式聚类。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    logs = get_logs_by_service(service_name)

    # 级别分布统计
    level_counts: dict[str, int] = {}
    for log in logs:
        level_counts[log["level"]] = level_counts.get(log["level"], 0) + 1

    # 错误日志模式聚类（按消息关键词）
    error_patterns: dict[str, int] = {}
    for log in logs:
        if log["level"] in ("ERROR", "FATAL"):
            # 提取关键模式
            msg = log["message"]
            if "timeout" in msg.lower() or "超时" in msg:
                pattern = "超时/Timeout"
            elif "OOM" in msg or "OutOfMemory" in msg:
                pattern = "内存溢出/OOM"
            elif "Connection" in msg or "连接" in msg:
                pattern = "连接异常"
            elif "CPU" in msg:
                pattern = "CPU 告警"
            elif "disk" in msg.lower() or "磁盘" in msg or "space" in msg.lower():
                pattern = "磁盘空间不足"
            elif "GC" in msg:
                pattern = "GC 异常"
            elif "crash" in msg.lower() or "启动" in msg:
                pattern = "崩溃/启动失败"
            else:
                pattern = "其他错误"
            error_patterns[pattern] = error_patterns.get(pattern, 0) + 1

    # 错误频率排序
    top_errors = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)

    return {
        "service_name": service_name,
        "time_range_minutes": time_range_minutes,
        "total_logs": len(logs),
        "level_distribution": level_counts,
        "error_patterns": [{"pattern": p, "count": c} for p, c in top_errors],
        "top_error_pattern": top_errors[0][0] if top_errors else None,
        "analysis_summary": _build_analysis_summary(service_name, level_counts, error_patterns),
    }


def _build_analysis_summary(service_name: str, level_counts: dict, error_patterns: dict) -> str:
    """构建分析摘要"""
    error_count = level_counts.get("ERROR", 0) + level_counts.get("FATAL", 0)
    if error_count == 0:
        return f"{service_name} 近期无错误日志，日志模式正常"

    top_pattern = max(error_patterns, key=error_patterns.get) if error_patterns else "未知"
    return f"{service_name} 近期发现 {error_count} 条错误日志，主要异常模式: {top_pattern}"


@mcp.tool()
@log_tool_call
def query_slow_sql(
    service_name: str,
    threshold_ms: int = 1000,
    limit: int = 20,
) -> dict[str, Any]:
    """查询数据库慢 SQL 记录。

    Args:
        service_name: 服务名称（如 "order-service"）
        threshold_ms: 慢查询阈值（毫秒，默认1000）
        limit: 返回条数限制（默认20）

    Returns:
        慢 SQL 列表，包含 SQL 文本、执行时间、扫描行数、优化建议。
        order-service 会返回多条慢查询记录。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    sqls = get_slow_sqls_by_service(service_name)
    # 按阈值过滤
    sqls = [s for s in sqls if s["execution_time_ms"] >= threshold_ms]
    # 按执行时间降序
    sqls = sorted(sqls, key=lambda x: x["execution_time_ms"], reverse=True)
    sqls = sqls[:limit]

    return {
        "service_name": service_name,
        "threshold_ms": threshold_ms,
        "total": len(sqls),
        "slow_sqls": sqls,
        "summary": {
            "max_execution_time_ms": sqls[0]["execution_time_ms"] if sqls else 0,
            "avg_execution_time_ms": round(sum(s["execution_time_ms"] for s in sqls) / len(sqls), 0)
            if sqls
            else 0,
            "total_scan_rows": sum(s["scan_rows"] for s in sqls),
        },
    }


@mcp.tool()
@log_tool_call
def search_system_events(
    service_name: str,
    event_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """查询系统事件日志（OOM kill、服务重启、crash、磁盘满等）。

    Args:
        service_name: 服务名称（如 "data-sync-service"）
        event_type: 事件类型筛选（oom_kill/full_gc/crash/restart/disk_full_warning/thread_pool_exhausted/high_cpu/slow_query，可选）
        limit: 返回条数限制（默认50）

    Returns:
        系统事件列表，包含事件类型、严重级别、时间戳、详情。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    events = get_system_events_by_service(service_name)

    if event_type:
        events = [e for e in events if e["event_type"] == event_type]

    events = events[:limit]

    return {
        "service_name": service_name,
        "event_type_filter": event_type,
        "total": len(events),
        "events": events,
        "summary": {
            "critical_count": sum(1 for e in events if e["severity"] == "critical"),
            "warning_count": sum(1 for e in events if e["severity"] == "warning"),
        },
    }


@mcp.tool()
@log_tool_call
def get_log_statistics(
    service_name: str,
    time_range_minutes: int = 60,
) -> dict[str, Any]:
    """获取服务日志级别分布统计。

    Args:
        service_name: 服务名称（如 "payment-service"）
        time_range_minutes: 统计时间范围（分钟，默认60）

    Returns:
        各级别日志数量、错误率、日志趋势。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    logs = get_logs_by_service(service_name)

    level_stats: dict[str, int] = {}
    for log in logs:
        level_stats[log["level"]] = level_stats.get(log["level"], 0) + 1

    total = len(logs)
    error_count = level_stats.get("ERROR", 0) + level_stats.get("FATAL", 0)
    error_rate = round(error_count / total * 100, 1) if total > 0 else 0

    # 按实例统计
    instance_stats: dict[str, int] = {}
    for log in logs:
        inst = log.get("instance", "unknown")
        instance_stats[inst] = instance_stats.get(inst, 0) + 1

    return {
        "service_name": service_name,
        "time_range_minutes": time_range_minutes,
        "total_logs": total,
        "level_distribution": level_stats,
        "error_rate_percent": error_rate,
        "instance_distribution": instance_stats,
        "trend": "increasing" if error_rate > 30 else "stable",
        "alert": error_rate > 30,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8003)
