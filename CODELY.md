

## Codely Structured Memories

### User

### Feedback
- [2026-08-06 17:54:06] [feedback] 前端静态文件改动后必须 bump `index.html` 中的 `?v=N` 缓存版本号（当前 v=15），否则浏览器加载旧缓存。**Why:** 项目无构建工具，靠手动版本号刷新缓存。**How to apply:** 每次改 app.js 或 styles.css 后，同步更新 index.html 中两处 `?v=` 引用。






### Project
- [2026-08-06 17:38:20] [project] AIOps MCP 工具已大幅扩展。现有 5 个 MCP Server 共 ~41 个工具，端口统一使用 8100 段（不使用 8000 段）：CLS(8103, 10个日志工具)、Monitor(8104, 16个监控/服务工具)、Alert(8105, 6个告警工具)、Ops(8106, 7个部署/工单/运维操作工具)、DDG(8107, 2个联网搜索工具)。共享数据在 `mcp_servers/mock_data.py`。`start-windows.bat` 自动启动全部 5 个 MCP Server。Windows 下运行方式：`python -m mcp_servers.cls_server`（模块模式，非脚本模式，否则 `from mcp_servers.mock_data import` 会失败）。**注意端口迁移坑：** 系统/用户级环境变量 `MCP_CLS_URL`/`MCP_MONITOR_URL` 可能缓存了旧的 8003/8004 端口值，会覆盖 .env 和 config.py 的默认值。迁移端口时必须同时更新 .env + 系统环境变量 + .env.example，否则 `uv run` 仍读到旧端口。



- [2026-08-05 17:34:42] [project] ruff 未全局安装，需通过 `uv run python -m ruff` 调用（直接 `ruff` 会报 command not found）。格式化命令：`uv run python -m ruff format app/ mcp_servers/ tests/` + `uv run python -m ruff check --fix app/ mcp_servers/ tests/`。
- [2026-08-06 11:38:33] MCP 服务已从第三方 `fastmcp` 包（打包 bug 严重，2.12.0–2.14.7 和 3.4.x 全系列均有 ImportError）切换到底层 `mcp` SDK（v1.26.0）自带的 `FastMCP`。**改动：** `cls_server.py` 和 `monitor_server.py` 各 2 处——① `from fastmcp import FastMCP` → `from mcp.server.fastmcp import FastMCP`；② `mcp.run(transport=..., host=..., port=..., path="/mcp")` → `uvicorn.run(mcp.streamable_http_app(), host=..., port=...)`（`mcp` SDK 的 `run()` 不支持 host/port/path，需用 `streamable_http_app()` 返回 Starlette app 交给 uvicorn）。默认 mount path 仍是 `/mcp`。**Why:** `mcp` SDK 是 `fastmcp` 包的底层依赖，API 完全兼容且无打包 bug，venv 重建也不受影响。

- [2026-08-06 10:43:23] [project] Agent 模式（AIOps）流式光标 Bug：`.message.streaming` 类触发 CSS `::after` 闪烁光标，Agent 流程的 `finalizeAgentFlow` 必须移除 `streaming` 类才能停止光标。Chat 模式的 `handleStreamComplete` 已处理。
- [2026-08-06 11:27:23] [project] Agent 模式持久化方案：后端 `aiops_service.execute()` 完成后调 `session_persistence_manager.upsert_agent_session(task, plan, steps, report)`，存入 `chat_sessions`+`chat_messages` 表。assistant 消息以 JSON `{"type":"agent","plan":[...],"steps":[{step,result}],"report":"..."}` 存储。前端加载历史时 `JSON.parse` 后按 `type==='agent'` 识别，调 `addAgentMessageFromHistory` 还原执行流程。**注意：** JSON 检测不能用 `startsWith('{"type":"agent"')`，因为 `json.dumps` 默认冒号后有空格，必须用 `JSON.parse` + 字段判断。
- [2026-08-06 14:58:54] - [2026-08-06 14:57:00] [project] 多 Agent 协作模式（Supervisor-Worker）已实现（2026-08-06 完成）。前端三态切换：Chat → Agent（单 Agent Plan-Execute-Replan）→ Multi（多 Agent Supervisor-Worker）。多 Agent 代码全在 `app/agent/multi_agent/`（state/prompts/tool_registry/workers/supervisor/__init__）+ `app/services/multi_agent_service.py`，与现有单 Agent 完全独立。API 路由：`POST /api/aiops` 带 `{multi_agent: true}` 走多 Agent。Supervisor 不调工具只做路由决策（`with_structured_output(SupervisorDecision)`），4 个 Worker 各绑自己的工具子集（Researcher 13 / Analyst 14 / Executor 5 / Writer 2 个工具）。Worker 执行完自动回 Supervisor 循环，Supervisor 判 FINISH 时综合报告。最多 6 轮强制终止。持久化复用 `upsert_agent_session`，JSON type 为 `"multi_agent"`。
- [2026-08-06 17:38:58] - [2026-08-06 17:37:00] [project] 联网搜索 MCP 使用 DuckDuckGo（`mcp_servers/ddg_server.py`，端口 8107），用 `duckduckgo-search` 包（已通过 `uv add duckduckgo-search` 安装），完全免费无需 API Key。工具：`web_search(query, count, region)` + `web_search_suggest(query)`。网络不可达时返回 mock 结果保证 Agent 流程不中断。可选配置 `DDG_PROXY` 环境变量走代理（如 socks5://127.0.0.1:1080）。Multi-Agent 的 Researcher worker 已分配 web_search/web_search_suggest 工具。**Why:** 原 Brave Search 需要付费 API Key，用户无法获取，改为 DuckDuckGo 完全免费。
- [2026-08-06 18:43:17] - [2026-08-06 18:43:00] [project] MCP Server 改代码后必须重启进程才生效：运行中的 dev server 进程持有修改前的模块代码，改动 `mcp_servers/*.py` 后需杀掉旧进程（按 pid 文件或端口 nslookup）重新启动（`python -m mcp_servers.<name>`，隐窗启动），否则 MCP 客户端调用到的是旧逻辑。**排查法：** 直接 `from mcp_servers.ddg_server import web_search` 测函数 vs 通过 MCP 客户端调工具，两者结果不一致即说明进程未重载。
- [2026-08-06 18:43:43] - [2026-08-06 18:43:00] [project] DuckDuckGo mock 搜索已补真实 AI 新闻数据：`mcp_servers/ddg_server.py` 的 `_build_mock_search` 匹配"新闻/news/AI/人工智能/gpt/大模型/最新"关键词时返回 10 条真实 AI 新闻（OpenAI GPT-5.6 / 字节 Seeduplex / DeepSeek DSpark / Claude Managed Agents / xAI Grok Build / 谷歌 Gemini 2.5 / 苹果收购 PromptAI / 面壁智能 / 我国 1509 个大模型等，来源 web_search 真实结果）。其余关键词走各领域 mock。Multi-Agent 的 Researcher 已能从这批 mock 数据中提取有效新闻，AI 新闻类任务在内网可跑通完整流程。

### Reference

