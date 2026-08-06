"""AIOps Mock 数据中心

本模块集中定义所有 MCP Server 共享的 mock 数据，确保告警↔指标↔日志↔工单
之间形成连贯的证据链。Agent 在诊断时可以跨服务、跨工具交叉验证。

数据场景对应 aiops-docs/ 下的 5 个运维文档：
  - cpu_high_usage.md       → payment-service   CPU 95%
  - memory_high_usage.md    → data-sync-service  内存 88%
  - disk_high_usage.md      → api-gateway        磁盘 87%
  - service_unavailable.md  → notification-service 健康检查失败
  - slow_response.md        → order-service      P99 4.5s
"""

from datetime import datetime, timedelta
from typing import Any

# ============================================================
# 时间辅助
# ============================================================

# 全局基准时间：所有 mock 数据以"当前时间"为锚点倒推，
# 这样无论何时启动 Agent，告警时间都是"最近"的，体验更真实。
_NOW: datetime | None = None


def now() -> datetime:
    """获取缓存的当前时间（同一次 Agent 调用内一致）"""
    global _NOW
    if _NOW is None:
        _NOW = datetime.now()
    return _NOW


def fmt(dt: datetime, _fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化时间"""
    return dt.strftime(_fmt)


def minutes_ago(m: int) -> str:
    """返回 m 分钟前的时间字符串"""
    return fmt(now() - timedelta(minutes=m))


def hours_ago(h: int) -> str:
    """返回 h 小时前的时间字符串"""
    return fmt(now() - timedelta(hours=h))


# ============================================================
# 服务清单
# ============================================================

MOCK_SERVICES: list[dict[str, Any]] = [
    {
        "service_name": "payment-service",
        "display_name": "支付服务",
        "region_code": "ap-beijing",
        "region_name": "北京",
        "status": "warning",
        "health": "degraded",
        "version": "v2.3.1",
        "instances": 4,
        "healthy_instances": 3,
        "owner": "payments-team",
        "owner_email": "payments-team@company.com",
        "description": "处理在线支付交易的核心服务",
        "dependencies": ["order-service", "user-service", "inventory-service"],
        "tech_stack": ["Java 17", "Spring Boot 3.2", "MySQL 8.0", "Redis 7.0"],
        "created_at": "2023-06-15 09:00:00",
    },
    {
        "service_name": "data-sync-service",
        "display_name": "数据同步服务",
        "region_code": "ap-beijing",
        "region_name": "北京",
        "status": "warning",
        "health": "degraded",
        "version": "v1.8.0",
        "instances": 3,
        "healthy_instances": 3,
        "owner": "data-platform-team",
        "owner_email": "data-platform-team@company.com",
        "description": "跨数据源数据同步与 ETL 处理",
        "dependencies": ["MySQL", "Kafka", "Elasticsearch"],
        "tech_stack": ["Java 17", "Spring Boot 3.1", "MyBatis-Plus"],
        "created_at": "2023-09-20 14:30:00",
    },
    {
        "service_name": "api-gateway",
        "display_name": "API 网关",
        "region_code": "ap-shanghai",
        "region_name": "上海",
        "status": "warning",
        "health": "degraded",
        "version": "v3.1.2",
        "instances": 2,
        "healthy_instances": 2,
        "owner": "infra-team",
        "owner_email": "infra-team@company.com",
        "description": "统一 API 入口网关，负责路由、限流、鉴权",
        "dependencies": ["payment-service", "order-service", "user-service"],
        "tech_stack": ["Go 1.21", "Gin", "Redis"],
        "created_at": "2023-03-10 10:00:00",
    },
    {
        "service_name": "notification-service",
        "display_name": "通知服务",
        "region_code": "ap-guangzhou",
        "region_name": "广州",
        "status": "critical",
        "health": "unhealthy",
        "version": "v1.5.3",
        "instances": 3,
        "healthy_instances": 0,
        "owner": "platform-team",
        "owner_email": "platform-team@company.com",
        "description": "邮件、短信、推送通知发送服务",
        "dependencies": ["Redis", "Kafka", "SMTP"],
        "tech_stack": ["Python 3.12", "FastAPI", "Celery"],
        "created_at": "2023-11-05 11:20:00",
    },
    {
        "service_name": "order-service",
        "display_name": "订单服务",
        "region_code": "ap-guangzhou",
        "region_name": "广州",
        "status": "warning",
        "health": "degraded",
        "version": "v4.2.0",
        "instances": 5,
        "healthy_instances": 5,
        "owner": "orders-team",
        "owner_email": "orders-team@company.com",
        "description": "订单创建、查询、状态管理",
        "dependencies": ["MySQL", "Redis", "inventory-service"],
        "tech_stack": ["Java 17", "Spring Cloud", "MyBatis-Plus"],
        "created_at": "2023-05-18 08:45:00",
    },
    {
        "service_name": "user-service",
        "display_name": "用户服务",
        "region_code": "ap-beijing",
        "region_name": "北京",
        "status": "healthy",
        "health": "healthy",
        "version": "v2.0.1",
        "instances": 4,
        "healthy_instances": 4,
        "owner": "identity-team",
        "owner_email": "identity-team@company.com",
        "description": "用户注册、登录、权限管理",
        "dependencies": ["MySQL", "Redis"],
        "tech_stack": ["Java 17", "Spring Boot 3.2"],
        "created_at": "2023-07-22 09:15:00",
    },
    {
        "service_name": "inventory-service",
        "display_name": "库存服务",
        "region_code": "ap-shanghai",
        "region_name": "上海",
        "status": "healthy",
        "health": "healthy",
        "version": "v1.3.0",
        "instances": 3,
        "healthy_instances": 3,
        "owner": "inventory-team",
        "owner_email": "inventory-team@company.com",
        "description": "商品库存管理与扣减",
        "dependencies": ["MySQL", "Redis"],
        "tech_stack": ["Go 1.21", "Gin"],
        "created_at": "2023-08-30 13:00:00",
    },
]


# ============================================================
# 活跃告警（5 条，对应 5 个场景文档）
# ============================================================

MOCK_ALERTS: list[dict[str, Any]] = [
    {
        "alert_id": "ALT-2026-001",
        "alert_name": "HighCPUUsage",
        "severity": "critical",
        "service_name": "payment-service",
        "status": "firing",
        "first_triggered_at": minutes_ago(28),
        "last_triggered_at": minutes_ago(1),
        "duration_minutes": 28,
        "description": "CPU 使用率持续 5 分钟超过 80%",
        "current_value": 95.2,
        "threshold": 80.0,
        "region": "ap-beijing",
        "metric": "cpu_usage_percent",
        "message": "payment-service CPU 使用率 95.2%，超过阈值 80%",
        "related_alerts": ["HighMemoryUsage", "SlowResponse"],
    },
    {
        "alert_id": "ALT-2026-002",
        "alert_name": "HighMemoryUsage",
        "severity": "critical",
        "service_name": "data-sync-service",
        "status": "firing",
        "first_triggered_at": minutes_ago(42),
        "last_triggered_at": minutes_ago(2),
        "duration_minutes": 42,
        "description": "内存使用率持续 5 分钟超过 85%",
        "current_value": 88.4,
        "threshold": 85.0,
        "region": "ap-beijing",
        "metric": "memory_usage_percent",
        "message": "data-sync-service 内存使用率 88.4%，存在 OOM 风险",
        "related_alerts": ["HighCPUUsage", "OOMError"],
    },
    {
        "alert_id": "ALT-2026-003",
        "alert_name": "HighDiskUsage",
        "severity": "warning",
        "service_name": "api-gateway",
        "status": "firing",
        "first_triggered_at": minutes_ago(55),
        "last_triggered_at": minutes_ago(3),
        "duration_minutes": 55,
        "description": "磁盘使用率超过 80%（警告）/ 90%（严重）",
        "current_value": 87.3,
        "threshold": 80.0,
        "region": "ap-shanghai",
        "metric": "disk_usage_percent",
        "message": "api-gateway 磁盘使用率 87.3%，/var/log 分区即将写满",
        "related_alerts": ["DiskIOHigh"],
    },
    {
        "alert_id": "ALT-2026-004",
        "alert_name": "ServiceUnavailable",
        "severity": "urgent",
        "service_name": "notification-service",
        "status": "firing",
        "first_triggered_at": minutes_ago(15),
        "last_triggered_at": minutes_ago(0),
        "duration_minutes": 15,
        "description": "服务健康检查失败或错误率超过 50%",
        "current_value": 62.0,
        "threshold": 50.0,
        "region": "ap-guangzhou",
        "metric": "error_rate_percent",
        "message": "notification-service 错误率 62%，所有实例健康检查失败",
        "related_alerts": ["HealthCheckFailed", "AllInstancesDown"],
    },
    {
        "alert_id": "ALT-2026-005",
        "alert_name": "SlowResponse",
        "severity": "warning",
        "service_name": "order-service",
        "status": "firing",
        "first_triggered_at": minutes_ago(35),
        "last_triggered_at": minutes_ago(1),
        "duration_minutes": 35,
        "description": "P99 响应时间持续 5 分钟超过 3 秒",
        "current_value": 4520.0,
        "threshold": 3000.0,
        "region": "ap-guangzhou",
        "metric": "response_time_p99_ms",
        "message": "order-service P99 响应时间 4520ms，超过阈值 3000ms",
        "related_alerts": ["DatabaseSlowQuery", "HighCPUUsage"],
    },
]


# ============================================================
# 历史工单（每个告警服务 2 条）
# ============================================================

MOCK_HISTORICAL_TICKETS: list[dict[str, Any]] = [
    {
        "ticket_id": "TKT-2025-0142",
        "service_name": "payment-service",
        "issue_type": "cpu_high",
        "title": "payment-service CPU 飙升导致支付超时",
        "severity": "critical",
        "created_at": "2025-12-10 14:20:00",
        "resolved_at": "2025-12-10 15:05:00",
        "resolution_time_minutes": 45,
        "root_cause": "定时任务与支付高峰重叠，线程池满载导致 CPU 100%",
        "solution": "调整定时任务执行时间至凌晨，扩容线程池上限，添加限流保护",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2026-0031",
        "service_name": "payment-service",
        "issue_type": "cpu_high",
        "title": "支付服务 CPU 持续高位告警",
        "severity": "critical",
        "created_at": "2026-01-15 09:30:00",
        "resolved_at": "2026-01-15 10:15:00",
        "resolution_time_minutes": 45,
        "root_cause": "新版本引入的 JSON 序列化库性能较差，高频调用导致 CPU 升高",
        "solution": "回退 JSON 序列化库版本至 fastjson 1.2.83，CPU 恢复正常",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2025-0205",
        "service_name": "data-sync-service",
        "issue_type": "memory_high",
        "title": "数据同步服务内存泄漏导致 OOM",
        "severity": "critical",
        "created_at": "2025-11-20 03:15:00",
        "resolved_at": "2025-11-20 04:00:00",
        "resolution_time_minutes": 45,
        "root_cause": "大批量同步任务未分页处理，一次性加载全量数据导致内存溢出",
        "solution": "改为游标分页同步，限制单批 5000 条，增加 JVM 堆内存至 4GB",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2026-0018",
        "service_name": "data-sync-service",
        "issue_type": "memory_high",
        "title": "同步服务 Full GC 频繁告警",
        "severity": "critical",
        "created_at": "2026-02-05 22:40:00",
        "resolved_at": "2026-02-05 23:25:00",
        "resolution_time_minutes": 45,
        "root_cause": "缓存未设置过期时间，长时间运行后缓存对象堆积",
        "solution": "为缓存添加 TTL 30 分钟，启用 LRU 淘汰策略，重启实例释放内存",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2025-0178",
        "service_name": "api-gateway",
        "issue_type": "disk_high",
        "title": "API 网关磁盘写满导致服务不可用",
        "severity": "critical",
        "created_at": "2025-10-12 16:00:00",
        "resolved_at": "2025-10-12 16:30:00",
        "resolution_time_minutes": 30,
        "root_cause": "访问日志未配置轮转，单个日志文件增长至 80GB",
        "solution": "配置 logrotate 每日轮转 + gzip 压缩，保留 7 天，清理旧日志",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2026-0027",
        "service_name": "api-gateway",
        "issue_type": "disk_high",
        "title": "网关磁盘使用率持续增长",
        "severity": "warning",
        "created_at": "2026-03-01 10:20:00",
        "resolved_at": "2026-03-01 10:50:00",
        "resolution_time_minutes": 30,
        "root_cause": "Docker 镜像未清理，停止的容器日志堆积",
        "solution": "执行 docker system prune -a 清理未使用镜像和容器日志",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2025-0199",
        "service_name": "notification-service",
        "issue_type": "service_unavailable",
        "title": "通知服务全部实例宕机",
        "severity": "urgent",
        "created_at": "2025-12-28 08:00:00",
        "resolved_at": "2025-12-28 08:20:00",
        "resolution_time_minutes": 20,
        "root_cause": "Redis 连接池配置错误导致连接泄漏，所有实例连接耗尽后崩溃",
        "solution": "修复连接池配置 max-active=50，添加连接超时回收，重启全部实例",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2026-0022",
        "service_name": "notification-service",
        "issue_type": "service_unavailable",
        "title": "通知服务部署后无法启动",
        "severity": "urgent",
        "created_at": "2026-02-18 14:30:00",
        "resolved_at": "2026-02-18 15:10:00",
        "resolution_time_minutes": 40,
        "root_cause": "新版本配置项缺失 required_env SMTP_HOST，导致启动失败",
        "solution": "回滚至上一稳定版本，补充缺失的环境变量配置后重新发布",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2025-0166",
        "service_name": "order-service",
        "issue_type": "slow_response",
        "title": "订单查询接口响应变慢",
        "severity": "warning",
        "created_at": "2025-10-25 11:00:00",
        "resolved_at": "2025-10-25 11:40:00",
        "resolution_time_minutes": 40,
        "root_cause": "订单表缺少 (user_id, created_at) 复合索引，全表扫描",
        "solution": "添加复合索引，优化分页查询使用覆盖索引，P99 降至 800ms",
        "status": "resolved",
    },
    {
        "ticket_id": "TKT-2026-0014",
        "service_name": "order-service",
        "issue_type": "slow_response",
        "title": "订单服务 P99 告警",
        "severity": "warning",
        "created_at": "2026-01-20 15:30:00",
        "resolved_at": "2026-01-20 16:00:00",
        "resolution_time_minutes": 30,
        "root_cause": "Redis 缓存批量过期导致缓存雪崩，请求穿透到数据库",
        "solution": "缓存过期时间添加随机抖动，启用多级缓存（本地+Redis），P99 恢复 600ms",
        "status": "resolved",
    },
]


# ============================================================
# 近期部署记录
# ============================================================

MOCK_DEPLOYMENTS: list[dict[str, Any]] = [
    {
        "deployment_id": "DEP-2026-0089",
        "service_name": "notification-service",
        "version": "v1.5.3",
        "environment": "production",
        "status": "failed",
        "deployed_at": minutes_ago(18),
        "deployed_by": "ci-bot",
        "image": "registry.company.com/notification:v1.5.3",
        "changes": "升级 Celery 5.3 → 5.4，修改 Redis 连接池配置",
        "instances_updated": 3,
        "instances_failed": 3,
        "rollback_available": True,
        "previous_version": "v1.5.2",
        "error_message": "启动失败: 缺少环境变量 SMTP_HOST，3 个实例均 crash loop",
    },
    {
        "deployment_id": "DEP-2026-0088",
        "service_name": "order-service",
        "version": "v4.2.0",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(2),
        "deployed_by": "zhang.san",
        "image": "registry.company.com/order:v4.2.0",
        "changes": "新增批量查询接口，优化订单导出功能",
        "instances_updated": 5,
        "instances_failed": 0,
        "rollback_available": True,
        "previous_version": "v4.1.2",
    },
    {
        "deployment_id": "DEP-2026-0087",
        "service_name": "payment-service",
        "version": "v2.3.1",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(5),
        "deployed_by": "li.si",
        "image": "registry.company.com/payment:v2.3.1",
        "changes": "接入新的风控引擎，增加交易限额校验逻辑",
        "instances_updated": 4,
        "instances_failed": 0,
        "rollback_available": True,
        "previous_version": "v2.3.0",
    },
    {
        "deployment_id": "DEP-2026-0086",
        "service_name": "data-sync-service",
        "version": "v1.8.0",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(8),
        "deployed_by": "wang.wu",
        "image": "registry.company.com/data-sync:v1.8.0",
        "changes": "新增 Elasticsearch 数据源支持，重构同步任务调度器",
        "instances_updated": 3,
        "instances_failed": 0,
        "rollback_available": True,
        "previous_version": "v1.7.2",
    },
    {
        "deployment_id": "DEP-2026-0085",
        "service_name": "api-gateway",
        "version": "v3.1.2",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(12),
        "deployed_by": "ci-bot",
        "image": "registry.company.com/gateway:v3.1.2",
        "changes": "升级 Go 1.20 → 1.21，优化限流算法",
        "instances_updated": 2,
        "instances_failed": 0,
        "rollback_available": True,
        "previous_version": "v3.1.1",
    },
    {
        "deployment_id": "DEP-2026-0084",
        "service_name": "user-service",
        "version": "v2.0.1",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(20),
        "deployed_by": "zhao.liu",
        "image": "registry.company.com/user:v2.0.1",
        "changes": "修复密码重置 token 过期逻辑",
        "instances_updated": 4,
        "instances_failed": 0,
        "rollback_available": True,
        "previous_version": "v2.0.0",
    },
    {
        "deployment_id": "DEP-2026-0083",
        "service_name": "inventory-service",
        "version": "v1.3.0",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(26),
        "deployed_by": "ci-bot",
        "image": "registry.company.com/inventory:v1.3.0",
        "changes": "新增库存预警功能",
        "instances_updated": 3,
        "instances_failed": 0,
        "rollback_available": True,
        "previous_version": "v1.2.1",
    },
    {
        "deployment_id": "DEP-2026-0082",
        "service_name": "order-service",
        "version": "v4.1.2",
        "environment": "production",
        "status": "success",
        "deployed_at": hours_ago(48),
        "deployed_by": "zhang.san",
        "image": "registry.company.com/order:v4.1.2",
        "changes": "修复订单状态机并发问题",
        "instances_updated": 5,
        "instances_failed": 0,
        "rollback_available": False,
        "previous_version": "v4.1.1",
    },
]


# ============================================================
# 慢 SQL 记录（主要关联 order-service）
# ============================================================

MOCK_SLOW_SQLS: list[dict[str, Any]] = [
    {
        "sql_id": "SQL-SLOW-001",
        "service_name": "order-service",
        "query": "SELECT * FROM orders WHERE user_id = ? AND status = 'PAID' ORDER BY created_at DESC",
        "execution_time_ms": 3420,
        "scan_rows": 1850000,
        "return_rows": 50,
        "database": "order_db",
        "table": "orders",
        "timestamp": minutes_ago(10),
        "index_used": "idx_user_id",
        "suggestion": "缺少 (user_id, status, created_at) 复合索引，建议添加",
    },
    {
        "sql_id": "SQL-SLOW-002",
        "service_name": "order-service",
        "query": "SELECT COUNT(*) FROM orders WHERE created_at > ? AND status != 'CANCELLED'",
        "execution_time_ms": 2850,
        "scan_rows": 980000,
        "return_rows": 1,
        "database": "order_db",
        "table": "orders",
        "timestamp": minutes_ago(15),
        "index_used": "None",
        "suggestion": "全表扫描，建议在 created_at 字段添加索引",
    },
    {
        "sql_id": "SQL-SLOW-003",
        "service_name": "order-service",
        "query": "SELECT o.*, u.username FROM orders o JOIN users u ON o.user_id = u.id WHERE o.amount > 1000",
        "execution_time_ms": 2100,
        "scan_rows": 560000,
        "return_rows": 1200,
        "database": "order_db",
        "table": "orders JOIN users",
        "timestamp": minutes_ago(20),
        "index_used": "PRIMARY",
        "suggestion": "JOIN 操作缺少 user_id 外键索引，建议添加",
    },
    {
        "sql_id": "SQL-SLOW-004",
        "service_name": "order-service",
        "query": "UPDATE orders SET status = 'SHIPPING' WHERE id IN (?, ?, ?, ...) AND warehouse = ?",
        "execution_time_ms": 1850,
        "scan_rows": 320000,
        "return_rows": 0,
        "database": "order_db",
        "table": "orders",
        "timestamp": minutes_ago(25),
        "index_used": "PRIMARY",
        "suggestion": "批量 UPDATE 锁定行数过多，建议分批小事务执行",
    },
    {
        "sql_id": "SQL-SLOW-005",
        "service_name": "payment-service",
        "query": "SELECT * FROM payment_transactions WHERE merchant_id = ? AND created_at BETWEEN ? AND ?",
        "execution_time_ms": 1560,
        "scan_rows": 420000,
        "return_rows": 30,
        "database": "payment_db",
        "table": "payment_transactions",
        "timestamp": minutes_ago(12),
        "index_used": "idx_merchant_id",
        "suggestion": "时间范围查询未命中索引，建议添加 (merchant_id, created_at) 复合索引",
    },
    {
        "sql_id": "SQL-SLOW-006",
        "service_name": "order-service",
        "query": "SELECT * FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id = ?)",
        "execution_time_ms": 1320,
        "scan_rows": 280000,
        "return_rows": 15,
        "database": "order_db",
        "table": "order_items",
        "timestamp": minutes_ago(30),
        "index_used": "None",
        "suggestion": "子查询未走索引，建议改为 JOIN 查询并添加 order_id 索引",
    },
]


# ============================================================
# 系统事件（OOM kill、重启、crash 等）
# ============================================================

MOCK_SYSTEM_EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "EVT-001",
        "service_name": "data-sync-service",
        "event_type": "oom_kill",
        "severity": "critical",
        "timestamp": minutes_ago(30),
        "instance_id": "data-sync-2",
        "message": "JVM OutOfMemoryError: Java heap space，进程被 OOM Killer 终止",
        "details": "heap dump 分析显示大量 HashMap Entry 未释放，疑似内存泄漏",
    },
    {
        "event_id": "EVT-002",
        "service_name": "data-sync-service",
        "event_type": "full_gc",
        "severity": "warning",
        "timestamp": minutes_ago(25),
        "instance_id": "data-sync-1",
        "message": "Full GC 持续时间 3.2s，STW 导致短暂卡顿",
        "details": "老年代使用率 92%，Full GC 后仅回收 3%，存在内存泄漏迹象",
    },
    {
        "event_id": "EVT-003",
        "service_name": "notification-service",
        "event_type": "crash",
        "severity": "critical",
        "timestamp": minutes_ago(18),
        "instance_id": "notification-1",
        "message": "实例 crash loop，启动失败: KeyError: 'SMTP_HOST'",
        "details": "环境变量 SMTP_HOST 未配置，应用启动时抛出异常并退出",
    },
    {
        "event_id": "EVT-004",
        "service_name": "notification-service",
        "event_type": "restart",
        "severity": "warning",
        "timestamp": minutes_ago(16),
        "instance_id": "notification-2",
        "message": "实例被 Kubernetes 自动重启（重启策略: Always）",
        "details": "这是过去 15 分钟内第 6 次重启",
    },
    {
        "event_id": "EVT-005",
        "service_name": "api-gateway",
        "event_type": "disk_full_warning",
        "severity": "warning",
        "timestamp": minutes_ago(40),
        "instance_id": "gateway-1",
        "message": "/var/log 分区使用率 87%，接近写满",
        "details": "access.log 文件大小 42GB，未配置 logrotate 轮转",
    },
    {
        "event_id": "EVT-006",
        "service_name": "payment-service",
        "event_type": "thread_pool_exhausted",
        "severity": "warning",
        "timestamp": minutes_ago(20),
        "instance_id": "payment-1",
        "message": "HTTP 线程池活跃线程数 200/200，拒绝连接 34 次",
        "details": "maxThreads=200 已满载，大量请求排队等待",
    },
    {
        "event_id": "EVT-007",
        "service_name": "payment-service",
        "event_type": "high_cpu",
        "severity": "critical",
        "timestamp": minutes_ago(28),
        "instance_id": "payment-1",
        "message": "进程 java(pid=12345) CPU 使用率 98.7%",
        "details": "top 进程: java(pid=12345) 98.7%, java(pid=12346) 85.3%",
    },
    {
        "event_id": "EVT-008",
        "service_name": "order-service",
        "event_type": "slow_query",
        "severity": "warning",
        "timestamp": minutes_ago(10),
        "instance_id": "order-3",
        "message": "检测到 4 条执行时间超过 1s 的慢 SQL",
        "details": "最慢 SQL: SELECT * FROM orders WHERE user_id=? 耗时 3420ms",
    },
]


# ============================================================
# 告警规则配置
# ============================================================

MOCK_ALERT_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "RULE-001",
        "rule_name": "HighCPUUsage",
        "metric": "cpu_usage_percent",
        "condition": ">",
        "threshold": 80.0,
        "duration_seconds": 300,
        "severity": "critical",
        "description": "CPU 使用率持续 5 分钟超过 80%",
        "enabled": True,
    },
    {
        "rule_id": "RULE-002",
        "rule_name": "HighMemoryUsage",
        "metric": "memory_usage_percent",
        "condition": ">",
        "threshold": 85.0,
        "duration_seconds": 300,
        "severity": "critical",
        "description": "内存使用率持续 5 分钟超过 85%",
        "enabled": True,
    },
    {
        "rule_id": "RULE-003",
        "rule_name": "HighDiskUsage",
        "metric": "disk_usage_percent",
        "condition": ">",
        "threshold": 80.0,
        "duration_seconds": 300,
        "severity": "warning",
        "description": "磁盘使用率持续 5 分钟超过 80%",
        "enabled": True,
    },
    {
        "rule_id": "RULE-004",
        "rule_name": "ServiceUnavailable",
        "metric": "error_rate_percent",
        "condition": ">",
        "threshold": 50.0,
        "duration_seconds": 60,
        "severity": "urgent",
        "description": "错误率超过 50% 或健康检查失败",
        "enabled": True,
    },
    {
        "rule_id": "RULE-005",
        "rule_name": "SlowResponse",
        "metric": "response_time_p99_ms",
        "condition": ">",
        "threshold": 3000.0,
        "duration_seconds": 300,
        "severity": "warning",
        "description": "P99 响应时间持续 5 分钟超过 3 秒",
        "enabled": True,
    },
]


# ============================================================
# 告警历史（已恢复的历史告警）
# ============================================================

MOCK_ALERT_HISTORY: list[dict[str, Any]] = [
    {
        "alert_id": "ALT-2025-0312",
        "alert_name": "HighCPUUsage",
        "service_name": "payment-service",
        "severity": "critical",
        "status": "resolved",
        "first_triggered_at": "2025-12-10 14:20:00",
        "resolved_at": "2025-12-10 15:05:00",
        "duration_minutes": 45,
        "peak_value": 97.5,
    },
    {
        "alert_id": "ALT-2025-0298",
        "alert_name": "HighMemoryUsage",
        "service_name": "data-sync-service",
        "severity": "critical",
        "status": "resolved",
        "first_triggered_at": "2025-11-20 03:15:00",
        "resolved_at": "2025-11-20 04:00:00",
        "duration_minutes": 45,
        "peak_value": 94.2,
    },
    {
        "alert_id": "ALT-2025-0285",
        "alert_name": "HighDiskUsage",
        "service_name": "api-gateway",
        "severity": "critical",
        "status": "resolved",
        "first_triggered_at": "2025-10-12 16:00:00",
        "resolved_at": "2025-10-12 16:30:00",
        "duration_minutes": 30,
        "peak_value": 98.1,
    },
    {
        "alert_id": "ALT-2025-0301",
        "alert_name": "ServiceUnavailable",
        "service_name": "notification-service",
        "severity": "urgent",
        "status": "resolved",
        "first_triggered_at": "2025-12-28 08:00:00",
        "resolved_at": "2025-12-28 08:20:00",
        "duration_minutes": 20,
        "peak_value": 100.0,
    },
    {
        "alert_id": "ALT-2025-0276",
        "alert_name": "SlowResponse",
        "service_name": "order-service",
        "severity": "warning",
        "status": "resolved",
        "first_triggered_at": "2025-10-25 11:00:00",
        "resolved_at": "2025-10-25 11:40:00",
        "duration_minutes": 40,
        "peak_value": 5200.0,
    },
]


# ============================================================
# 日志主题映射（CLS Server 使用）
# ============================================================

MOCK_LOG_TOPICS: list[dict[str, Any]] = [
    {
        "topic_id": "topic-001",
        "topic_name": "payment-service-app-log",
        "service_name": "payment-service",
        "region_code": "ap-beijing",
        "log_type": "application",
        "description": "支付服务应用日志",
    },
    {
        "topic_id": "topic-002",
        "topic_name": "data-sync-service-app-log",
        "service_name": "data-sync-service",
        "region_code": "ap-beijing",
        "log_type": "application",
        "description": "数据同步服务应用日志",
    },
    {
        "topic_id": "topic-003",
        "topic_name": "api-gateway-access-log",
        "service_name": "api-gateway",
        "region_code": "ap-shanghai",
        "log_type": "access",
        "description": "API 网关访问日志",
    },
    {
        "topic_id": "topic-004",
        "topic_name": "notification-service-app-log",
        "service_name": "notification-service",
        "region_code": "ap-guangzhou",
        "log_type": "application",
        "description": "通知服务应用日志",
    },
    {
        "topic_id": "topic-005",
        "topic_name": "order-service-app-log",
        "service_name": "order-service",
        "region_code": "ap-guangzhou",
        "log_type": "application",
        "description": "订单服务应用日志",
    },
    {
        "topic_id": "topic-006",
        "topic_name": "user-service-app-log",
        "service_name": "user-service",
        "region_code": "ap-beijing",
        "log_type": "application",
        "description": "用户服务应用日志",
    },
    {
        "topic_id": "topic-007",
        "topic_name": "inventory-service-app-log",
        "service_name": "inventory-service",
        "region_code": "ap-shanghai",
        "log_type": "application",
        "description": "库存服务应用日志",
    },
    {
        "topic_id": "topic-sys-001",
        "topic_name": "system-metrics",
        "service_name": None,
        "region_code": "all",
        "log_type": "system",
        "description": "系统指标日志（CPU/内存/磁盘）",
    },
    {
        "topic_id": "topic-sys-002",
        "topic_name": "system-events",
        "service_name": None,
        "region_code": "all",
        "log_type": "event",
        "description": "系统事件日志（OOM/restart/crash）",
    },
    {
        "topic_id": "topic-db-001",
        "topic_name": "database-slow-query",
        "service_name": None,
        "region_code": "all",
        "log_type": "database",
        "description": "数据库慢查询日志",
    },
]


# ============================================================
# 服务日志内容模板（按服务名返回不同日志）
# ============================================================

MOCK_SERVICE_LOGS: dict[str, list[dict[str, Any]]] = {
    "payment-service": [
        {
            "timestamp": minutes_ago(25),
            "level": "WARN",
            "message": "HTTP 线程池活跃数: 198/200，接近上限",
            "instance": "payment-1",
        },
        {
            "timestamp": minutes_ago(22),
            "level": "ERROR",
            "message": "线程池满载，拒绝连接: RejectedExecutionException",
            "instance": "payment-1",
        },
        {
            "timestamp": minutes_ago(20),
            "level": "WARN",
            "message": "支付处理耗时 3200ms，超过阈值 2000ms",
            "instance": "payment-1",
        },
        {
            "timestamp": minutes_ago(15),
            "level": "ERROR",
            "message": "java(pid=12345) CPU 使用率 98.7%，触发告警",
            "instance": "payment-1",
        },
        {
            "timestamp": minutes_ago(10),
            "level": "ERROR",
            "message": "调用 inventory-service 超时，connect timed out after 5000ms",
            "instance": "payment-2",
        },
        {
            "timestamp": minutes_ago(5),
            "level": "WARN",
            "message": "GC pause: Young GC 480ms，System GC triggered",
            "instance": "payment-1",
        },
    ],
    "data-sync-service": [
        {
            "timestamp": minutes_ago(35),
            "level": "INFO",
            "message": "开始执行全量数据同步任务: sync_user_data",
            "instance": "data-sync-1",
        },
        {
            "timestamp": minutes_ago(30),
            "level": "ERROR",
            "message": "OutOfMemoryError: Java heap space，同步任务中断",
            "instance": "data-sync-2",
        },
        {
            "timestamp": minutes_ago(28),
            "level": "WARN",
            "message": "Full GC 持续 3200ms，老年代使用率 92%",
            "instance": "data-sync-1",
        },
        {
            "timestamp": minutes_ago(25),
            "level": "ERROR",
            "message": "Full GC 后内存仅回收 3%，疑似内存泄漏",
            "instance": "data-sync-1",
        },
        {
            "timestamp": minutes_ago(20),
            "level": "WARN",
            "message": "缓存对象数量: 1850000，超过预警阈值 1000000",
            "instance": "data-sync-2",
        },
        {
            "timestamp": minutes_ago(10),
            "level": "ERROR",
            "message": "OOM Killer 终止进程 java(pid=23456)",
            "instance": "data-sync-2",
        },
    ],
    "api-gateway": [
        {
            "timestamp": minutes_ago(50),
            "level": "WARN",
            "message": "磁盘使用率告警: /var/log 87.3%",
            "instance": "gateway-1",
        },
        {
            "timestamp": minutes_ago(40),
            "level": "ERROR",
            "message": "写入日志失败: No space left on device",
            "instance": "gateway-1",
        },
        {
            "timestamp": minutes_ago(35),
            "level": "WARN",
            "message": "access.log 文件大小: 42GB，未配置轮转",
            "instance": "gateway-1",
        },
        {
            "timestamp": minutes_ago(25),
            "level": "WARN",
            "message": "磁盘 IO 等待时间增加: iowait 25%",
            "instance": "gateway-1",
        },
        {
            "timestamp": minutes_ago(15),
            "level": "ERROR",
            "message": "临时文件写入失败: disk full",
            "instance": "gateway-2",
        },
    ],
    "notification-service": [
        {
            "timestamp": minutes_ago(18),
            "level": "ERROR",
            "message": "启动失败: KeyError: 'SMTP_HOST'，环境变量未配置",
            "instance": "notification-1",
        },
        {
            "timestamp": minutes_ago(17),
            "level": "FATAL",
            "message": "Application startup failed, exiting...",
            "instance": "notification-1",
        },
        {
            "timestamp": minutes_ago(16),
            "level": "ERROR",
            "message": "健康检查失败: HTTP 503 Service Unavailable",
            "instance": "notification-2",
        },
        {
            "timestamp": minutes_ago(15),
            "level": "ERROR",
            "message": "所有实例健康检查失败，触发 ServiceUnavailable 告警",
            "instance": "notification-3",
        },
        {
            "timestamp": minutes_ago(10),
            "level": "ERROR",
            "message": "crash loop: 过去 15 分钟重启 6 次",
            "instance": "notification-2",
        },
    ],
    "order-service": [
        {
            "timestamp": minutes_ago(30),
            "level": "WARN",
            "message": "P99 响应时间 4520ms，超过阈值 3000ms",
            "instance": "order-3",
        },
        {
            "timestamp": minutes_ago(25),
            "level": "WARN",
            "message": "数据库连接池使用率 95%，活跃连接 48/50",
            "instance": "order-1",
        },
        {
            "timestamp": minutes_ago(20),
            "level": "ERROR",
            "message": "慢 SQL: SELECT * FROM orders WHERE user_id=? 耗时 3420ms",
            "instance": "order-3",
        },
        {
            "timestamp": minutes_ago(15),
            "level": "WARN",
            "message": "Redis 缓存命中率下降: 45%（正常 85%）",
            "instance": "order-2",
        },
        {
            "timestamp": minutes_ago(10),
            "level": "ERROR",
            "message": "订单查询超时: Read timeout after 5000ms",
            "instance": "order-3",
        },
        {
            "timestamp": minutes_ago(5),
            "level": "WARN",
            "message": "请求堆积: 等待队列长度 320",
            "instance": "order-1",
        },
    ],
    "user-service": [
        {
            "timestamp": minutes_ago(20),
            "level": "INFO",
            "message": "用户登录成功，userId=USR_88234",
            "instance": "user-1",
        },
        {
            "timestamp": minutes_ago(15),
            "level": "INFO",
            "message": "Token 刷新完成",
            "instance": "user-2",
        },
        {
            "timestamp": minutes_ago(10),
            "level": "WARN",
            "message": "密码尝试失败 3 次，账户临时锁定",
            "instance": "user-1",
        },
    ],
    "inventory-service": [
        {
            "timestamp": minutes_ago(30),
            "level": "INFO",
            "message": "库存扣减成功: productId=P001, qty=2",
            "instance": "inventory-1",
        },
        {
            "timestamp": minutes_ago(20),
            "level": "INFO",
            "message": "库存预警检查完成，无预警项",
            "instance": "inventory-2",
        },
        {
            "timestamp": minutes_ago(10),
            "level": "WARN",
            "message": "商品 P099 库存不足，剩余 3 件",
            "instance": "inventory-1",
        },
    ],
}


# ============================================================
# 运维手册 / Runbook（按问题类型）
# ============================================================

MOCK_RUNBOOKS: dict[str, dict[str, Any]] = {
    "cpu_high": {
        "issue_type": "cpu_high",
        "title": "CPU 使用率过高排查手册",
        "reference_doc": "aiops-docs/cpu_high_usage.md",
        "steps": [
            "1. 使用 query_cpu_metrics 获取 CPU 趋势，确认告警时间范围",
            "2. 使用 query_process_list 查看 CPU 消耗最高的进程",
            "3. 使用 search_service_logs 查询告警时段的 ERROR/WARN 日志",
            "4. 分析原因：死循环/流量突增/定时任务重叠/数据库慢查询",
            "5. 紧急处理：扩容/限流/重启问题实例",
            "6. 长期优化：代码优化/增加监控/完善扩缩容策略",
        ],
        "common_causes": ["死循环或无限递归", "流量突增", "定时任务重叠", "数据库慢查询"],
    },
    "memory_high": {
        "issue_type": "memory_high",
        "title": "内存使用率过高排查手册",
        "reference_doc": "aiops-docs/memory_high_usage.md",
        "steps": [
            "1. 使用 query_memory_metrics 获取内存趋势",
            "2. 使用 query_gc_metrics 查看 GC 频率和耗时",
            "3. 使用 search_system_events 查询 OOM kill 事件",
            "4. 使用 search_service_logs 查询 OutOfMemoryError 日志",
            "5. 分析原因：内存泄漏/流量突增/缓存配置不当/JVM 参数不合理",
            "6. 紧急处理：重启实例/扩容/dump 内存快照",
        ],
        "common_causes": ["内存泄漏", "流量突增导致对象激增", "缓存配置不当", "JVM 参数不合理"],
    },
    "disk_high": {
        "issue_type": "disk_high",
        "title": "磁盘使用率过高排查手册",
        "reference_doc": "aiops-docs/disk_high_usage.md",
        "steps": [
            "1. 使用 query_disk_metrics 获取磁盘使用趋势",
            "2. 使用 search_service_logs 查询 'No space left on device' 日志",
            "3. 分析大文件：日志/临时文件/数据文件/备份/Docker 镜像",
            "4. 紧急清理：删除旧日志/清理临时文件/压缩备份",
            "5. 长期优化：配置 logrotate/数据归档/容量规划",
        ],
        "common_causes": [
            "日志文件过大",
            "临时文件堆积",
            "数据文件增长过快",
            "备份文件占用",
            "Docker 镜像和容器",
        ],
    },
    "service_unavailable": {
        "issue_type": "service_unavailable",
        "title": "服务不可用排查手册",
        "reference_doc": "aiops-docs/service_unavailable.md",
        "steps": [
            "1. 使用 query_service_health 确认服务健康状态",
            "2. 使用 list_recent_deployments 检查是否有近期部署",
            "3. 使用 search_service_logs 查询 ERROR/FATAL 日志",
            "4. 使用 search_system_events 查询 crash/restart 事件",
            "5. 分析原因：应用崩溃/数据库连接失败/依赖故障/配置错误/资源耗尽",
            "6. 紧急处理：回滚/重启/降级/启用备用服务",
        ],
        "common_causes": [
            "应用崩溃或无法启动",
            "数据库连接失败",
            "依赖服务故障",
            "配置错误",
            "资源耗尽",
        ],
    },
    "slow_response": {
        "issue_type": "slow_response",
        "title": "响应时间过长排查手册",
        "reference_doc": "aiops-docs/slow_response.md",
        "steps": [
            "1. 使用 query_response_time_metrics 获取 P99 趋势",
            "2. 使用 query_slow_sql 查询慢 SQL 记录",
            "3. 使用 query_database_metrics 检查数据库连接池",
            "4. 使用 query_cache_metrics 检查缓存命中率",
            "5. 使用 query_cpu_metrics 检查 CPU 是否瓶颈",
            "6. 分析原因：慢查询/外部 API 超时/代码性能/缓存失效/资源不足",
        ],
        "common_causes": [
            "数据库慢查询",
            "外部 API 调用超时",
            "代码性能问题",
            "缓存失效或穿透",
            "系统资源不足",
        ],
    },
}


# ============================================================
# 辅助查询函数
# ============================================================


def get_service_by_name(service_name: str) -> dict[str, Any] | None:
    """按名称查找服务，返回服务元数据"""
    for svc in MOCK_SERVICES:
        if svc["service_name"] == service_name:
            return svc
    return None


def get_alerts_by_service(service_name: str) -> list[dict[str, Any]]:
    """返回某服务的所有活跃告警"""
    return [a for a in MOCK_ALERTS if a["service_name"] == service_name]


def get_active_alert_by_name(alert_name: str) -> dict[str, Any] | None:
    """按告警名称查找活跃告警"""
    for alert in MOCK_ALERTS:
        if alert["alert_name"] == alert_name:
            return alert
    return None


def get_alert_by_id(alert_id: str) -> dict[str, Any] | None:
    """按告警 ID 查找"""
    for alert in MOCK_ALERTS:
        if alert["alert_id"] == alert_id:
            return alert
    return None


def get_logs_by_service(service_name: str) -> list[dict[str, Any]]:
    """返回某服务的 mock 日志列表"""
    return MOCK_SERVICE_LOGS.get(service_name, [])


def get_topic_by_service(service_name: str) -> dict[str, Any] | None:
    """按服务名查找日志主题"""
    for topic in MOCK_LOG_TOPICS:
        if topic.get("service_name") == service_name:
            return topic
    return None


def get_tickets_by_service(service_name: str) -> list[dict[str, Any]]:
    """返回某服务的历史工单"""
    return [t for t in MOCK_HISTORICAL_TICKETS if t["service_name"] == service_name]


def get_deployments_by_service(service_name: str) -> list[dict[str, Any]]:
    """返回某服务的近期部署"""
    return [d for d in MOCK_DEPLOYMENTS if d["service_name"] == service_name]


def get_system_events_by_service(service_name: str) -> list[dict[str, Any]]:
    """返回某服务的系统事件"""
    return [e for e in MOCK_SYSTEM_EVENTS if e["service_name"] == service_name]


def get_slow_sqls_by_service(service_name: str) -> list[dict[str, Any]]:
    """返回某服务的慢 SQL"""
    return [s for s in MOCK_SLOW_SQLS if s["service_name"] == service_name]


def generate_metric_series(
    service_name: str,
    metric_type: str,
    start_time: datetime,
    end_time: datetime,
    interval_minutes: int = 1,
) -> list[dict[str, Any]]:
    """生成监控指标时间序列

    根据服务名和指标类型返回与告警场景一致的数据曲线：
    - payment-service + cpu: 从 30% 升到 95%
    - data-sync-service + memory: 从 40% 升到 88%
    - api-gateway + disk: 85%-88% 平稳高位
    - notification-service + error_rate: 0% 升到 62%
    - order-service + response_time: 500ms 升到 4500ms
    - 其他服务/指标: 返回正常范围数据
    """
    data_points = []
    current = start_time
    total_minutes = int((end_time - start_time).total_seconds() / 60)
    step_count = 0

    while current <= end_time:
        value = _get_metric_value(service_name, metric_type, step_count, total_minutes)
        data_points.append(
            {
                "timestamp": current.strftime("%H:%M"),
                "value": value,
                "datetime": fmt(current),
            }
        )
        current += timedelta(minutes=interval_minutes)
        step_count += 1

    return data_points


def _get_metric_value(service_name: str, metric_type: str, step: int, total_steps: int) -> float:
    """根据服务和指标类型计算单个数据点值"""
    progress = step / max(total_steps, 1)

    # 场景化数据曲线
    if service_name == "payment-service" and metric_type == "cpu":
        # CPU 从 30% 上升到 95%
        return round(30 + 65 * progress + _noise(2), 1)

    if service_name == "data-sync-service" and metric_type == "memory":
        # 内存从 40% 上升到 88%
        return round(40 + 48 * progress + _noise(1.5), 1)

    if service_name == "api-gateway" and metric_type == "disk":
        # 磁盘 85%-88% 平稳高位
        return round(85 + 3 * progress + _noise(0.5), 1)

    if service_name == "notification-service" and metric_type == "error_rate":
        # 错误率 0% 升到 62%
        return round(62 * progress + _noise(2), 1)

    if service_name == "order-service" and metric_type == "response_time":
        # P99 从 500ms 升到 4500ms
        return round(500 + 4000 * progress + _noise(100), 0)

    if service_name == "order-service" and metric_type == "cpu":
        # order-service CPU 略高（因慢查询），50%-70%
        return round(50 + 20 * progress + _noise(3), 1)

    if metric_type == "cpu":
        return round(15 + 20 * progress + _noise(3), 1)
    if metric_type == "memory":
        return round(35 + 15 * progress + _noise(2), 1)
    if metric_type == "disk":
        return round(40 + 10 * progress + _noise(1), 1)

    return round(50 + _noise(5), 1)


def _noise(amplitude: float) -> float:
    """生成小幅随机波动（基于时间的伪随机，确定性）"""
    import random

    rng = random.Random(int(now().timestamp()) % 1000 + int(amplitude * 100))
    return rng.uniform(-amplitude, amplitude)
