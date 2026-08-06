

## Codely Structured Memories

### User

### Feedback
- [2026-08-06 14:17:31] [feedback] 前端静态文件改动后必须 bump `index.html` 中的 `?v=N` 缓存版本号（当前 v=13），否则浏览器加载旧缓存。**Why:** 项目无构建工具，靠手动版本号刷新缓存。**How to apply:** 每次改 app.js 或 styles.css 后，同步更新 index.html 中两处 `?v=` 引用。




### Project
- [2026-08-06 12:05:02] [project] AIOps MCP 工具已大幅扩展（2026-08-06 完成）。现有 4 个 MCP Server 共 ~39 个工具：CLS(8003, 10个日志工具)、Monitor(8004, 16个监控/服务工具)、Alert(8005, 6个告警工具)、Ops(8006, 7个部署/工单/运维操作工具)。共享数据在 `mcp_servers/mock_data.py`，覆盖 7 个服务 + 5 条活跃告警(对应 aiops-docs 的 5 个场景) + 10 条历史工单 + 8 条部署记录 + 慢SQL + 系统事件 + Runbook。`start-windows.bat` 自动启动全部 4 个 MCP Server。Windows 下运行方式：`python -m mcp_servers.cls_server`（模块模式，非脚本模式，否则 `from mcp_servers.mock_data import` 会失败）。


- [2026-08-05 17:34:42] [project] ruff 未全局安装，需通过 `uv run python -m ruff` 调用（直接 `ruff` 会报 command not found）。格式化命令：`uv run python -m ruff format app/ mcp_servers/ tests/` + `uv run python -m ruff check --fix app/ mcp_servers/ tests/`。
- [2026-08-06 11:38:33] MCP 服务已从第三方 `fastmcp` 包（打包 bug 严重，2.12.0–2.14.7 和 3.4.x 全系列均有 ImportError）切换到底层 `mcp` SDK（v1.26.0）自带的 `FastMCP`。**改动：** `cls_server.py` 和 `monitor_server.py` 各 2 处——① `from fastmcp import FastMCP` → `from mcp.server.fastmcp import FastMCP`；② `mcp.run(transport=..., host=..., port=..., path="/mcp")` → `uvicorn.run(mcp.streamable_http_app(), host=..., port=...)`（`mcp` SDK 的 `run()` 不支持 host/port/path，需用 `streamable_http_app()` 返回 Starlette app 交给 uvicorn）。默认 mount path 仍是 `/mcp`。**Why:** `mcp` SDK 是 `fastmcp` 包的底层依赖，API 完全兼容且无打包 bug，venv 重建也不受影响。

- [2026-08-06 10:43:23] [project] Agent 模式（AIOps）流式光标 Bug：`.message.streaming` 类触发 CSS `::after` 闪烁光标，Agent 流程的 `finalizeAgentFlow` 必须移除 `streaming` 类才能停止光标。Chat 模式的 `handleStreamComplete` 已处理。
- [2026-08-06 11:27:23] [project] Agent 模式持久化方案：后端 `aiops_service.execute()` 完成后调 `session_persistence_manager.upsert_agent_session(task, plan, steps, report)`，存入 `chat_sessions`+`chat_messages` 表。assistant 消息以 JSON `{"type":"agent","plan":[...],"steps":[{step,result}],"report":"..."}` 存储。前端加载历史时 `JSON.parse` 后按 `type==='agent'` 识别，调 `addAgentMessageFromHistory` 还原执行流程。**注意：** JSON 检测不能用 `startsWith('{"type":"agent"')`，因为 `json.dumps` 默认冒号后有空格，必须用 `JSON.parse` + 字段判断。

### Reference

