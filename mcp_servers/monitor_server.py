"""智能运维监控 MCP Server

提供丰富的运维监控数据查询工具，覆盖以下场景：
- 监控指标查询（CPU、内存、磁盘、网络、GC、响应时间、错误率、QPS）
- 进程信息查询
- 服务管理（服务列表、详情、健康检查、实例列表、拓扑）
- 数据库与缓存指标

所有数据来自 mock_data.py，确保与告警、日志、工单形成连贯证据链。
"""

import functools
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_servers.mock_data import (
    MOCK_SERVICES,
    fmt,
    generate_metric_series,
    get_service_by_name,
    hours_ago,
    minutes_ago,
    now,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Monitor_MCP_Server")

mcp = FastMCP("Monitor")


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


def _interval_minutes(interval: str) -> int:
    """将 '1m'/'5m'/'1h' 转换为分钟数"""
    if interval.endswith("m"):
        return int(interval[:-1])
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    return 1


# ============================================================
# 核心指标查询工具
# ============================================================


@mcp.tool()
@log_tool_call
def query_cpu_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务的 CPU 使用率监控数据。

    Args:
        service_name: 服务名称（如 "payment-service"）
        start_time: 开始时间 "YYYY-MM-DD HH:MM:SS"（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔 "1m"/"5m"/"1h"（默认1m）

    Returns:
        CPU 使用率时间序列 + 统计信息 + 告警状态。
        payment-service 会返回持续高 CPU（95%）数据。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = generate_metric_series(service_name, "cpu", start_dt, end_dt, iv)

    if not data_points:
        return {"service_name": service_name, "data_points": [], "statistics": {}}

    values = [d["value"] for d in data_points]
    avg_val = round(sum(values) / len(values), 2)
    max_val = max(values)
    spike = max_val > 80.0

    return {
        "service_name": service_name,
        "metric_name": "cpu_usage_percent",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg": avg_val,
            "max": max_val,
            "min": min(values),
            "p95": round(sorted(values)[int(len(values) * 0.95)], 2)
            if len(values) > 1
            else max_val,
            "spike_detected": spike,
        },
        "alert_info": {
            "triggered": spike,
            "threshold": 80.0,
            "message": "CPU 使用率持续超过 80% 阈值" if spike else "CPU 使用率正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_memory_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务的内存使用率监控数据。

    Args:
        service_name: 服务名称（如 "data-sync-service"）
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        内存使用率时间序列 + 统计信息。
        data-sync-service 会返回持续高内存（88%）数据。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = generate_metric_series(service_name, "memory", start_dt, end_dt, iv)
    total_gb = 8.0

    for dp in data_points:
        dp["used_gb"] = round(dp["value"] / 100 * total_gb, 2)
        dp["total_gb"] = total_gb

    if not data_points:
        return {"service_name": service_name, "data_points": [], "statistics": {}}

    values = [d["value"] for d in data_points]
    avg_val = round(sum(values) / len(values), 2)
    max_val = max(values)
    pressure = max_val > 70.0

    return {
        "service_name": service_name,
        "metric_name": "memory_usage_percent",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg": avg_val,
            "max": max_val,
            "min": min(values),
            "p95": round(sorted(values)[int(len(values) * 0.95)], 2)
            if len(values) > 1
            else max_val,
            "memory_pressure": pressure,
        },
        "alert_info": {
            "triggered": pressure,
            "threshold": 70.0,
            "message": "内存使用率超过 70%，存在内存压力" if pressure else "内存使用率正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_disk_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务的磁盘使用率监控数据。

    Args:
        service_name: 服务名称（如 "api-gateway"）
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        磁盘使用率时间序列 + 分区详情。
        api-gateway 会返回磁盘使用率 87% 的数据。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = generate_metric_series(service_name, "disk", start_dt, end_dt, iv)

    # 分区详情
    partitions = [
        {"mount_point": "/", "total_gb": 50, "used_gb": 18, "usage_percent": 36.0},
        {"mount_point": "/var/log", "total_gb": 20, "used_gb": 17.4, "usage_percent": 87.3},
        {"mount_point": "/data", "total_gb": 100, "used_gb": 42, "usage_percent": 42.0},
    ]

    if not data_points:
        return {"service_name": service_name, "data_points": [], "statistics": {}}

    values = [d["value"] for d in data_points]
    max_val = max(values)

    return {
        "service_name": service_name,
        "metric_name": "disk_usage_percent",
        "interval": interval,
        "data_points": data_points,
        "partitions": partitions,
        "statistics": {
            "avg": round(sum(values) / len(values), 2),
            "max": max_val,
            "min": min(values),
        },
        "alert_info": {
            "triggered": max_val > 80,
            "threshold": 80.0,
            "message": "磁盘使用率超过 80% 阈值" if max_val > 80 else "磁盘使用率正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_network_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务的网络流量和丢包率。

    Args:
        service_name: 服务名称
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        网络入站/出站流量(MB/s)、丢包率、TCP 重传率。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = []
    current = start_dt
    while current <= end_dt:
        in_mb = round(15 + (current.second % 10), 2)
        out_mb = round(22 + (current.second % 8), 2)
        data_points.append(
            {
                "timestamp": current.strftime("%H:%M"),
                "inbound_mbps": in_mb,
                "outbound_mbps": out_mb,
                "packet_loss_percent": round(0.1 + (current.second % 5) * 0.05, 2),
                "tcp_retransmit_rate": round(0.5 + (current.second % 3) * 0.2, 2),
            }
        )
        current += timedelta(minutes=iv)

    return {
        "service_name": service_name,
        "metric_name": "network_traffic",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg_inbound_mbps": round(
                sum(d["inbound_mbps"] for d in data_points) / len(data_points), 2
            ),
            "avg_outbound_mbps": round(
                sum(d["outbound_mbps"] for d in data_points) / len(data_points), 2
            ),
            "max_packet_loss": max(d["packet_loss_percent"] for d in data_points),
        },
    }


@mcp.tool()
@log_tool_call
def query_process_list(
    service_name: str,
    sort_by: str = "cpu",
    limit: int = 10,
) -> dict[str, Any]:
    """查询服务所在主机的进程列表（按 CPU 或内存排序）。

    Args:
        service_name: 服务名称（如 "payment-service"）
        sort_by: 排序字段 "cpu" 或 "memory"（默认 cpu）
        limit: 返回进程数量（默认10）

    Returns:
        进程列表，包含 PID、进程名、CPU%、内存%、命令行。
        payment-service 会返回 CPU 98.7% 的 java 进程。
    """
    # 根据服务名返回不同的进程列表
    if service_name == "payment-service":
        processes = [
            {
                "pid": 12345,
                "name": "java",
                "cpu_percent": 98.7,
                "memory_percent": 42.3,
                "command": "java -jar payment-service.jar --server.port=8080",
            },
            {
                "pid": 12346,
                "name": "java",
                "cpu_percent": 85.3,
                "memory_percent": 38.1,
                "command": "java -jar payment-service.jar --server.port=8081",
            },
            {
                "pid": 12347,
                "name": "java",
                "cpu_percent": 72.1,
                "memory_percent": 35.5,
                "command": "java -jar payment-service.jar --server.port=8082",
            },
            {
                "pid": 890,
                "name": "nginx",
                "cpu_percent": 5.2,
                "memory_percent": 1.8,
                "command": "nginx: worker process",
            },
            {
                "pid": 567,
                "name": "filebeat",
                "cpu_percent": 3.1,
                "memory_percent": 2.0,
                "command": "/usr/share/filebeat/bin/filebeat",
            },
        ]
    elif service_name == "data-sync-service":
        processes = [
            {
                "pid": 23456,
                "name": "java",
                "cpu_percent": 65.2,
                "memory_percent": 88.4,
                "command": "java -Xmx4g -jar data-sync.jar",
            },
            {
                "pid": 23457,
                "name": "java",
                "cpu_percent": 52.8,
                "memory_percent": 82.1,
                "command": "java -Xmx4g -jar data-sync.jar",
            },
            {
                "pid": 891,
                "name": "node_exporter",
                "cpu_percent": 2.1,
                "memory_percent": 0.9,
                "command": "/usr/local/bin/node_exporter",
            },
        ]
    else:
        processes = [
            {
                "pid": 1001,
                "name": "main",
                "cpu_percent": 25.3,
                "memory_percent": 30.2,
                "command": f"{service_name} --port=8080",
            },
            {
                "pid": 1002,
                "name": "sidecar",
                "cpu_percent": 5.1,
                "memory_percent": 2.0,
                "command": "envoy proxy",
            },
            {
                "pid": 890,
                "name": "nginx",
                "cpu_percent": 3.2,
                "memory_percent": 1.5,
                "command": "nginx: worker process",
            },
        ]

    sorted_procs = sorted(processes, key=lambda p: p[f"{sort_by}_percent"], reverse=True)[:limit]

    return {
        "service_name": service_name,
        "sort_by": sort_by,
        "total": len(sorted_procs),
        "processes": sorted_procs,
        "top_consumer": sorted_procs[0] if sorted_procs else None,
    }


@mcp.tool()
@log_tool_call
def query_gc_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询 JVM GC（垃圾回收）统计指标。

    Args:
        service_name: 服务名称（如 "data-sync-service"）
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        Young GC / Full GC 次数、耗时、堆内存使用。
        data-sync-service 会返回 Full GC 频繁的数据。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = []
    current = start_dt
    young_gc_count = 0
    full_gc_count = 0
    while current <= end_dt:
        young_gc = 2 + (current.second % 4)
        full_gc = 0
        if service_name == "data-sync-service":
            full_gc = 1 + (current.second % 3)
        young_gc_count += young_gc
        full_gc_count += full_gc
        data_points.append(
            {
                "timestamp": current.strftime("%H:%M"),
                "young_gc_count": young_gc,
                "young_gc_time_ms": young_gc * 120,
                "full_gc_count": full_gc,
                "full_gc_time_ms": full_gc * 3200,
                "heap_used_gb": round(3.2 + (current.second % 10) * 0.3, 2),
                "heap_total_gb": 4.0,
                "heap_usage_percent": round((3.2 + (current.second % 10) * 0.3) / 4.0 * 100, 1),
            }
        )
        current += timedelta(minutes=iv)

    return {
        "service_name": service_name,
        "metric_name": "jvm_gc",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "total_young_gc": young_gc_count,
            "total_full_gc": full_gc_count,
            "avg_full_gc_time_ms": round(
                sum(d["full_gc_time_ms"] for d in data_points) / max(len(data_points), 1), 0
            ),
            "max_heap_usage_percent": max(d["heap_usage_percent"] for d in data_points)
            if data_points
            else 0,
        },
        "alert_info": {
            "frequent_full_gc": full_gc_count > 10,
            "message": "Full GC 频繁，疑似内存泄漏" if full_gc_count > 10 else "GC 正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_response_time_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务响应时间指标（P50/P90/P99/P999）。

    Args:
        service_name: 服务名称（如 "order-service"）
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        多分位响应时间趋势。order-service 会返回 P99 4520ms 的数据。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = generate_metric_series(service_name, "response_time", start_dt, end_dt, iv)

    # 补充分位数据
    for dp in data_points:
        p99 = dp["value"]
        dp["p50_ms"] = round(p99 * 0.15, 0)
        dp["p90_ms"] = round(p99 * 0.45, 0)
        dp["p99_ms"] = p99
        dp["p999_ms"] = round(p99 * 1.3, 0)

    if not data_points:
        return {"service_name": service_name, "data_points": [], "statistics": {}}

    p99_values = [d["p99_ms"] for d in data_points]
    max_p99 = max(p99_values)

    return {
        "service_name": service_name,
        "metric_name": "response_time",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg_p50": round(sum(d["p50_ms"] for d in data_points) / len(data_points), 0),
            "avg_p99": round(sum(p99_values) / len(p99_values), 0),
            "max_p99": max_p99,
        },
        "alert_info": {
            "triggered": max_p99 > 3000,
            "threshold": 3000.0,
            "message": f"P99 响应时间 {max_p99}ms，超过阈值 3000ms"
            if max_p99 > 3000
            else "响应时间正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_error_rate_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务错误率和 HTTP 状态码分布。

    Args:
        service_name: 服务名称（如 "notification-service"）
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        错误率趋势 + HTTP 状态码分布。notification-service 会返回 62% 错误率。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = generate_metric_series(service_name, "error_rate", start_dt, end_dt, iv)

    # HTTP 状态码分布
    if service_name == "notification-service":
        status_codes = {"200": 380, "500": 580, "503": 40, "timeout": 120}
    else:
        status_codes = {"200": 950, "404": 20, "500": 15, "503": 5, "timeout": 10}

    if not data_points:
        return {"service_name": service_name, "data_points": [], "statistics": {}}

    values = [d["value"] for d in data_points]
    max_err = max(values)

    return {
        "service_name": service_name,
        "metric_name": "error_rate_percent",
        "interval": interval,
        "data_points": data_points,
        "http_status_distribution": status_codes,
        "statistics": {
            "avg_error_rate": round(sum(values) / len(values), 2),
            "max_error_rate": max_err,
        },
        "alert_info": {
            "triggered": max_err > 50,
            "threshold": 50.0,
            "message": f"错误率 {max_err}%，超过阈值 50%" if max_err > 50 else "错误率正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_qps_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
) -> dict[str, Any]:
    """查询服务 QPS（每秒请求数）趋势。

    Args:
        service_name: 服务名称
        start_time: 开始时间（默认1小时前）
        end_time: 结束时间（默认当前时间）
        interval: 聚合间隔

    Returns:
        QPS 时间序列 + 峰值/均值统计。
    """
    start_dt = _parse_time(start_time, -1)
    end_dt = _parse_time(end_time, 0)
    iv = _interval_minutes(interval)

    data_points = []
    current = start_dt
    while current <= end_dt:
        qps = 800 + (current.minute * 15) + (current.second % 200)
        data_points.append(
            {
                "timestamp": current.strftime("%H:%M"),
                "qps": qps,
                "tps": round(qps * 0.7, 0),
            }
        )
        current += timedelta(minutes=iv)

    qps_values = [d["qps"] for d in data_points]
    return {
        "service_name": service_name,
        "metric_name": "qps",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg_qps": round(sum(qps_values) / len(qps_values), 0),
            "max_qps": max(qps_values),
            "min_qps": min(qps_values),
        },
    }


@mcp.tool()
@log_tool_call
def query_database_metrics(service_name: str) -> dict[str, Any]:
    """查询服务关联的数据库指标（连接池、慢查询数）。

    Args:
        service_name: 服务名称（如 "order-service"）

    Returns:
        数据库连接池使用率、活跃连接数、慢查询数、锁等待。
        order-service 会返回连接池满载的数据。
    """
    if service_name == "order-service":
        return {
            "service_name": service_name,
            "database": "order_db",
            "db_type": "MySQL 8.0",
            "connection_pool": {
                "max_connections": 50,
                "active_connections": 48,
                "idle_connections": 2,
                "usage_percent": 96.0,
                "waiting_threads": 12,
            },
            "slow_queries": {
                "count_last_hour": 4,
                "avg_time_ms": 2100,
                "max_time_ms": 3420,
            },
            "lock_waits": {"count": 3, "avg_wait_ms": 850},
            "alert_info": {
                "pool_exhausted": True,
                "message": "数据库连接池使用率 96%，接近满载",
            },
        }
    elif service_name == "payment-service":
        return {
            "service_name": service_name,
            "database": "payment_db",
            "db_type": "MySQL 8.0",
            "connection_pool": {
                "max_connections": 30,
                "active_connections": 28,
                "idle_connections": 2,
                "usage_percent": 93.3,
                "waiting_threads": 5,
            },
            "slow_queries": {"count_last_hour": 1, "avg_time_ms": 1560, "max_time_ms": 1560},
            "lock_waits": {"count": 0, "avg_wait_ms": 0},
            "alert_info": {"pool_exhausted": True, "message": "数据库连接池使用率 93%"},
        }
    else:
        return {
            "service_name": service_name,
            "database": f"{service_name}_db",
            "db_type": "MySQL 8.0",
            "connection_pool": {
                "max_connections": 50,
                "active_connections": 15,
                "idle_connections": 35,
                "usage_percent": 30.0,
                "waiting_threads": 0,
            },
            "slow_queries": {"count_last_hour": 0, "avg_time_ms": 0, "max_time_ms": 0},
            "lock_waits": {"count": 0, "avg_wait_ms": 0},
            "alert_info": {"pool_exhausted": False, "message": "数据库连接池正常"},
        }


@mcp.tool()
@log_tool_call
def query_cache_metrics(service_name: str) -> dict[str, Any]:
    """查询服务缓存指标（命中率、内存占用、Key 数量）。

    Args:
        service_name: 服务名称（如 "order-service"）

    Returns:
        Redis 缓存命中率、内存使用、Key 数量、过期策略。
        order-service 会返回缓存命中率下降的数据（45% vs 正常 85%）。
    """
    if service_name == "order-service":
        return {
            "service_name": service_name,
            "cache_type": "Redis 7.0",
            "hit_rate_percent": 45.0,
            "memory_used_mb": 1840,
            "memory_max_mb": 2048,
            "memory_usage_percent": 89.8,
            "total_keys": 1850000,
            "expired_keys_last_hour": 420000,
            "evicted_keys_last_hour": 15000,
            "avg_latency_ms": 3.2,
            "alert_info": {
                "low_hit_rate": True,
                "message": "缓存命中率 45%（正常 85%），疑似缓存雪崩",
            },
        }
    else:
        return {
            "service_name": service_name,
            "cache_type": "Redis 7.0",
            "hit_rate_percent": 87.5,
            "memory_used_mb": 680,
            "memory_max_mb": 2048,
            "memory_usage_percent": 33.2,
            "total_keys": 320000,
            "expired_keys_last_hour": 15000,
            "evicted_keys_last_hour": 0,
            "avg_latency_ms": 1.1,
            "alert_info": {"low_hit_rate": False, "message": "缓存运行正常"},
        }


# ============================================================
# 服务管理工具
# ============================================================


@mcp.tool()
@log_tool_call
def list_all_services() -> dict[str, Any]:
    """列出所有已注册的服务及其状态摘要。

    Returns:
        服务总数 + 每个服务的名称、状态、健康度、实例数、活跃告警数。
    """
    from mcp_servers.mock_data import MOCK_ALERTS

    services = []
    for svc in MOCK_SERVICES:
        alert_count = sum(1 for a in MOCK_ALERTS if a["service_name"] == svc["service_name"])
        services.append(
            {
                "service_name": svc["service_name"],
                "display_name": svc["display_name"],
                "status": svc["status"],
                "health": svc["health"],
                "version": svc["version"],
                "instances": svc["instances"],
                "healthy_instances": svc["healthy_instances"],
                "region": svc["region_name"],
                "active_alerts": alert_count,
            }
        )

    healthy = sum(1 for s in services if s["status"] == "healthy")
    warning = sum(1 for s in services if s["status"] == "warning")
    critical = sum(1 for s in services if s["status"] == "critical")

    return {
        "total_services": len(services),
        "summary": {
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
        },
        "services": services,
    }


@mcp.tool()
@log_tool_call
def get_service_info(service_name: str) -> dict[str, Any]:
    """获取服务的详细元数据。

    Args:
        service_name: 服务名称（如 "payment-service"）

    Returns:
        服务完整信息：版本、实例数、负责人、依赖、技术栈。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}
    return svc


@mcp.tool()
@log_tool_call
def query_service_health(service_name: str) -> dict[str, Any]:
    """查询服务健康检查状态。

    Args:
        service_name: 服务名称（如 "notification-service"）

    Returns:
        健康检查结果：状态、响应时间、失败原因。
        notification-service 会返回 unhealthy。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    if svc["health"] == "unhealthy":
        return {
            "service_name": service_name,
            "health_status": "unhealthy",
            "healthy_instances": 0,
            "total_instances": svc["instances"],
            "health_check_url": f"http://{service_name}:8080/health",
            "last_check_time": fmt(now()),
            "failure_reason": "连接被拒绝: Connection refused",
            "consecutive_failures": 15,
            "alert_triggered": True,
        }
    elif svc["health"] == "degraded":
        return {
            "service_name": service_name,
            "health_status": "degraded",
            "healthy_instances": svc["healthy_instances"],
            "total_instances": svc["instances"],
            "health_check_url": f"http://{service_name}:8080/health",
            "last_check_time": fmt(now()),
            "response_time_ms": 1500,
            "failure_reason": None,
            "alert_triggered": True,
        }
    else:
        return {
            "service_name": service_name,
            "health_status": "healthy",
            "healthy_instances": svc["healthy_instances"],
            "total_instances": svc["instances"],
            "health_check_url": f"http://{service_name}:8080/health",
            "last_check_time": fmt(now()),
            "response_time_ms": 45,
            "failure_reason": None,
            "alert_triggered": False,
        }


@mcp.tool()
@log_tool_call
def get_service_instances(service_name: str) -> dict[str, Any]:
    """获取服务的所有实例列表。

    Args:
        service_name: 服务名称（如 "payment-service"）

    Returns:
        实例列表，每个实例包含 IP、端口、状态、CPU/内存使用率。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    # 根据服务状态生成实例数据
    if svc["health"] == "unhealthy":
        instances = [
            {
                "instance_id": f"{service_name}-1",
                "ip": f"10.0.1.{10 + i}",
                "port": 8080,
                "status": "crash_loop",
                "cpu_percent": 0,
                "memory_percent": 0,
                "restart_count": 6,
                "last_started": minutes_ago(3),
            }
            for i in range(svc["instances"])
        ]
    elif svc["health"] == "degraded" and service_name == "payment-service":
        instances = [
            {
                "instance_id": "payment-1",
                "ip": "10.0.1.11",
                "port": 8080,
                "status": "running",
                "cpu_percent": 98.7,
                "memory_percent": 42.3,
                "restart_count": 0,
                "last_started": hours_ago(5),
            },
            {
                "instance_id": "payment-2",
                "ip": "10.0.1.12",
                "port": 8080,
                "status": "running",
                "cpu_percent": 85.3,
                "memory_percent": 38.1,
                "restart_count": 0,
                "last_started": hours_ago(5),
            },
            {
                "instance_id": "payment-3",
                "ip": "10.0.1.13",
                "port": 8080,
                "status": "running",
                "cpu_percent": 72.1,
                "memory_percent": 35.5,
                "restart_count": 0,
                "last_started": hours_ago(5),
            },
            {
                "instance_id": "payment-4",
                "ip": "10.0.1.14",
                "port": 8080,
                "status": "unhealthy",
                "cpu_percent": 15.2,
                "memory_percent": 20.1,
                "restart_count": 1,
                "last_started": minutes_ago(10),
            },
        ]
    else:
        instances = [
            {
                "instance_id": f"{service_name}-{i + 1}",
                "ip": f"10.0.{i + 1}.{10 + i}",
                "port": 8080,
                "status": "running",
                "cpu_percent": round(20 + i * 5, 1),
                "memory_percent": round(30 + i * 3, 1),
                "restart_count": 0,
                "last_started": hours_ago(24 - i * 2),
            }
            for i in range(svc["instances"])
        ]

    return {
        "service_name": service_name,
        "total_instances": len(instances),
        "running_instances": sum(1 for i in instances if i["status"] in ("running",)),
        "instances": instances,
    }


@mcp.tool()
@log_tool_call
def get_service_topology(service_name: str) -> dict[str, Any]:
    """获取服务依赖拓扑图。

    Args:
        service_name: 服务名称（如 "payment-service"）

    Returns:
        上下游依赖关系图（上游调用方 + 下游被依赖服务）。
    """
    svc = get_service_by_name(service_name)
    if not svc:
        return {"error": f"未找到服务: {service_name}", "service_name": service_name}

    # 计算上游（谁调用了本服务）
    upstream = []
    for s in MOCK_SERVICES:
        if service_name in s.get("dependencies", []):
            upstream.append(
                {
                    "service_name": s["service_name"],
                    "display_name": s["display_name"],
                    "status": s["status"],
                }
            )

    # 下游（本服务依赖谁）
    downstream = []
    for dep in svc.get("dependencies", []):
        dep_svc = get_service_by_name(dep)
        if dep_svc:
            downstream.append(
                {
                    "service_name": dep_svc["service_name"],
                    "display_name": dep_svc["display_name"],
                    "status": dep_svc["status"],
                }
            )
        else:
            # 外部依赖（MySQL、Redis 等）
            downstream.append({"service_name": dep, "display_name": dep, "status": "unknown"})

    return {
        "service_name": service_name,
        "topology": {
            "upstream_callers": upstream,
            "downstream_dependencies": downstream,
        },
        "total_upstream": len(upstream),
        "total_downstream": len(downstream),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="127.0.0.1", port=8104)
