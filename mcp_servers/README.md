# MCP Servers

为 AIOps 智能诊断提供丰富的 mock 工具集，覆盖告警、监控、日志、部署、工单等运维场景，并支持 DuckDuckGo 联网搜索。

> **端口约定**：所有 MCP 服务端口统一使用 **8100 段**（不使用 8000 段）。

## 📚 服务列表

### CLS Server (`cls_server.py`)
**日志查询服务** — 端口 **8103**

| 工具 | 说明 |
|------|------|
| `get_current_timestamp` | 获取当前毫秒时间戳 |
| `get_region_code_by_name` | 地区名称→地区代码 |
| `get_topic_info_by_name` | 按名称查询日志主题 |
| `search_topic_by_service_name` | 按服务名搜索日志主题 |
| `search_log` | 按 topic_id 搜索日志 |
| `search_service_logs` | 按服务名+级别+关键词查日志 |
| `analyze_log_pattern` | 日志模式分析（错误频率 Top N） |
| `query_slow_sql` | 慢 SQL 查询 |
| `search_system_events` | 系统事件查询（OOM/crash/restart） |
| `get_log_statistics` | 日志级别分布统计 |

### Monitor Server (`monitor_server.py`)
**监控数据服务** — 端口 **8104**

| 工具 | 说明 |
|------|------|
| `query_cpu_metrics` | CPU 使用率查询 |
| `query_memory_metrics` | 内存使用率查询 |
| `query_disk_metrics` | 磁盘使用率查询 |
| `query_network_metrics` | 网络流量/丢包率 |
| `query_process_list` | 进程列表（按 CPU/内存排序） |
| `query_gc_metrics` | JVM GC 统计 |
| `query_response_time_metrics` | 响应时间 P50/P90/P99 |
| `query_error_rate_metrics` | 错误率/HTTP 状态码分布 |
| `query_qps_metrics` | QPS 趋势 |
| `query_database_metrics` | 数据库连接池/慢查询 |
| `query_cache_metrics` | 缓存命中率/内存 |
| `list_all_services` | 列出所有服务及状态 |
| `get_service_info` | 服务元数据 |
| `query_service_health` | 健康检查状态 |
| `get_service_instances` | 实例列表 |
| `get_service_topology` | 服务依赖拓扑 |

### Alert Server (`alert_server.py`)
**告警管理服务** — 端口 **8105**

| 工具 | 说明 |
|------|------|
| `list_active_alerts` | 列出活跃告警 |
| `get_alert_detail` | 告警详情 |
| `query_alert_history` | 历史告警查询 |
| `get_alert_rules` | 告警规则配置 |
| `acknowledge_alert` | 确认告警（mock 操作） |
| `get_alert_summary` | 告警概览统计 |

### Ops Server (`ops_server.py`)
**运维操作服务** — 端口 **8106**

| 工具 | 说明 |
|------|------|
| `list_recent_deployments` | 近期部署记录 |
| `get_deployment_detail` | 部署详情 |
| `rollback_deployment` | 回滚部署（mock 操作） |
| `restart_service` | 重启服务实例（mock 操作） |
| `scale_service` | 扩缩容（mock 操作） |
| `search_historical_tickets` | 历史工单查询 |
| `get_runbook` | 获取运维手册/SOP |

### DuckDuckGo Search Server (`ddg_server.py`)
**联网搜索服务** — 端口 **8107**

| 工具 | 说明 |
|------|------|
| `web_search` | 通用网页搜索（DuckDuckGo，完全免费无需 API Key） |
| `web_search_suggest` | 搜索建议词查询 |

完全免费、无需注册、无需 API Key。如网络无法直接访问 DuckDuckGo，可配置 `DDG_PROXY` 环境变量走代理；无代理时返回 mock 搜索结果保证 Agent 流程不中断。

## 🚀 快速开始

### 启动服务

**方式一：Windows 一键启动（推荐）**
```bat
start-windows.bat
```
自动启动全部 5 个 MCP Server + FastAPI 服务。

**方式二：Makefile（Linux/macOS）**
```bash
make start       # 启动所有服务（5 MCP + FastAPI）
make stop        # 停止所有服务
make status-mcp  # 查看服务状态
```

**方式三：手动启动**
```bash
python mcp_servers/cls_server.py      # 端口 8103
python mcp_servers/monitor_server.py  # 端口 8104
python mcp_servers/alert_server.py    # 端口 8105
python mcp_servers/ops_server.py      # 端口 8106
python mcp_servers/ddg_server.py      # 端口 8107
```

## 💡 Mock 场景说明

所有 mock 数据定义在 `mock_data.py` 中，覆盖 5 个运维场景（对应 `aiops-docs/` 文档）：

| 服务 | 告警 | 场景 |
|------|------|------|
| `payment-service` | HighCPUUsage | CPU 95%，线程池满载 |
| `data-sync-service` | HighMemoryUsage | 内存 88%，Full GC 频繁 |
| `api-gateway` | HighDiskUsage | 磁盘 87%，日志未轮转 |
| `notification-service` | ServiceUnavailable | 部署失败，全部实例 crash |
| `order-service` | SlowResponse | P99 4.5s，慢 SQL + 缓存雪崩 |

数据形成完整证据链：**告警 → 指标 → 日志 → 系统事件 → 历史工单 → Runbook**。

### AIOps 诊断示例

```
用户: 分析当前系统告警，排查 payment-service 的 CPU 问题

Agent 自动执行:
1. list_active_alerts() → 发现 5 条活跃告警
2. get_alert_detail("ALT-2026-001") → CPU 告警详情
3. query_cpu_metrics("payment-service") → CPU 95% 趋势
4. query_process_list("payment-service") → 高 CPU 进程
5. search_service_logs("payment-service", log_level="ERROR") → 错误日志
6. search_historical_tickets("payment-service", "cpu_high") → 历史工单
7. get_runbook("cpu_high") → 排查手册
8. 综合分析 → 生成诊断报告
```
