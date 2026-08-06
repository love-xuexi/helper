

## Codely Structured Memories

### User

### Feedback
- [2026-08-06 10:43:23] [feedback] 前端静态文件改动后必须 bump `index.html` 中的 `?v=N` 缓存版本号（当前 v=10），否则浏览器加载旧缓存。**Why:** 项目无构建工具，靠手动版本号刷新缓存。**How to apply:** 每次改 app.js 或 styles.css 后，同步更新 index.html 中两处 `?v=` 引用。


### Project
- [2026-08-05 17:52:59] [project] AIOps Agent 模式已接入前端（2026-08-05 完成）。输入框有 Chat/Agent 模式切换按钮，Agent 模式走 `POST /api/aiops`（支持 `task` 自定义任务），前端展示 Plan-Execute-Replan 执行流程（计划列表+步骤卡片+最终报告）。MCP 服务仍用 mock 数据，需手动启动 `python mcp_servers/cls_server.py` 和 `monitor_server.py`。

- [2026-08-05 17:34:42] [project] ruff 未全局安装，需通过 `uv run python -m ruff` 调用（直接 `ruff` 会报 command not found）。格式化命令：`uv run python -m ruff format app/ mcp_servers/ tests/` + `uv run python -m ruff check --fix app/ mcp_servers/ tests/`。
- [2026-08-05 18:18:36] fastmcp 存在打包 bug（2.12.0–2.14.7、3.4.x 均已确认有 bug）。当前 .venv 中是 `fastmcp==2.12.0` + 3 处手动补丁（见下方），服务可正常运行。**补丁位置：** ①`server/auth/auth.py` 加 `PrivateKeyJWTClientAuthenticator`/`TokenHandler` stub 类；②`server/auth/__init__.py` 的 `oauth_proxy` 导入包 try/except；③`fastmcp/__init__.py` 的 `client` 导入包 try/except。**How to apply:** venv 重建（如 stop/start-windows.bat）后补丁丢失，需重打；或换 `mcp` SDK 原生写法重写 cls_server/monitor_server。
- [2026-08-06 10:43:23] [project] Agent 模式（AIOps）流式光标 Bug：`.message.streaming` 类触发 CSS `::after` 闪烁光标，Agent 流程的 `finalizeAgentFlow` 必须移除 `streaming` 类才能停止光标。Chat 模式的 `handleStreamComplete` 已处理。

### Reference

