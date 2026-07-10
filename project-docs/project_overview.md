# SuperBizAgent 项目概览

## 1. 项目定位

SuperBizAgent 是一个基于 Python 的智能业务 Agent 项目，当前主要面向两个场景：

- 普通知识库问答：用户通过 Web/API 提问，Agent 根据需要调用知识库检索工具、时间工具和 MCP 工具，生成回答。
- AIOps 智能运维诊断：系统通过 Plan-Execute-Replan 模式自动制定排查计划、调用监控/日志工具、动态重规划，并输出诊断报告。

整体上，它已经具备一个 Agent 应用闭环：前端页面、FastAPI 接口、LLM 调用、内网知识库平台 API
检索（RAG）、引用来源展示、反馈评价、MCP 工具调用、SSE 流式输出。

> 2026-07 起知识库已接口化改造：本地不再建立知识库（移除 Milvus / Embedding / Rerank /
> 文档切分链路），检索、向量化、重排全部由内网知识库平台完成，本项目只调用其 HTTP 接口。

## 2. 技术栈

| 层级       | 技术/组件                                             | 说明                                                                                          |
| ---------- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Web/API    | FastAPI、Uvicorn、SSE Starlette                       | 提供 HTTP API、SSE 流式响应和静态页面服务                                                     |
| Agent 编排 | LangChain、LangGraph                                  | RAG Agent 和 AIOps Plan-Execute-Replan 工作流                                                 |
| LLM        | OpenAI 兼容 Chat 接口（DeepSeek / Qwen / ChatOpenAI） | 聊天、规划、执行、重规划、报告生成                                                            |
| 知识库     | 内网知识库平台 API                                    | 文档解析、向量化、混合检索（向量+关键词）、重排均由平台完成，本项目通过 `kb_api_service` 调用 |
| 反馈存储   | SQLite（`data/feedback.db`）                          | 点赞/不喜欢 + 结构化标签 + 评论入库，可选转发内网反馈接口                                     |
| 工具协议   | MCP、FastMCP、langchain-mcp-adapters                  | 对接日志查询和监控查询工具                                                                    |
| 前端       | 原生 HTML/CSS/JS                                      | 支持聊天、流式输出、引用来源卡片、反馈评价、文件上传、AIOps 触发                              |

## 3. 启动与运行链路

主要启动入口是 `app/main.py`。

启动时：

1. FastAPI 创建应用实例。
1. 注册 CORS、静态文件和 API 路由。
1. 在 lifespan 中初始化会话持久化后端（memory 或 PostgreSQL）与反馈 SQLite 库。
1. 用户访问 `/` 时返回 `static/index.html`。
1. 用户通过前端或 API 调用
   `/api/chat`、`/api/chat_stream`、`/api/upload`、`/api/kb/*`、`/api/feedback*`、`/api/aiops`。

Windows 推荐使用：

```powershell
.\start-windows.bat
```

手动启动时通常需要：

1. 启动 MCP
   Server：`python mcp_servers/cls_server.py`、`python mcp_servers/monitor_server.py`（Agent
   初始化会调用 MCP，服务不可达会导致 `/api/chat` 失败）
1. 启动主服务：`python -m uvicorn app.main:app --host 0.0.0.0 --port 9900`
1. 访问：`http://localhost:9900`

不再需要 Docker 启动 Milvus；内网不可达时的本地联调方式见 `docs/local-dev-guide.md`（mock 知识库/LLM 服务）。

## 4. 目录职责

| 路径            | 职责                                                                                                                                                   |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app/main.py`   | FastAPI 应用入口，生命周期、路由、静态文件                                                                                                             |
| `app/config.py` | Pydantic Settings 配置中心，读取 `.env`                                                                                                                |
| `app/api/`      | HTTP API 层，负责请求/响应和 SSE 包装                                                                                                                  |
| `app/services/` | 业务服务层，包括 RAG Agent、知识库平台 API 客户端（`kb_api_service`）、检索上下文（`retrieval_context`）、反馈服务（`feedback_service`）、AIOps 工作流 |
| `app/agent/`    | Agent 相关实现，包括 MCP Client 和 AIOps 节点                                                                                                          |
| `app/tools/`    | LangChain 本地工具，如知识库检索、当前时间                                                                                                             |
| `app/core/`     | LLM Factory、会话持久化等基础组件                                                                                                                      |
| `app/models/`   | Pydantic 请求/响应模型                                                                                                                                 |
| `mcp_servers/`  | 本地 MCP Server，提供日志和监控 mock 工具                                                                                                              |
| `static/`       | 原生前端页面、样式和交互逻辑                                                                                                                           |
| `aiops-docs/`   | AIOps 运维经验语料（CPU/内存/磁盘/服务不可用等 Markdown 文档）                                                                                         |
| `docs/`         | 使用指南与本地联调手册（user-guide / local-dev-guide）                                                                                                 |
| `project-docs/` | 本次新建的项目理解、计划和后续开发沉淀目录                                                                                                             |

## 4.1 配置结构

- Chat：`CHAT_PROVIDER`（deepseek/qwen/openai）、`CHAT_API_KEY`、`CHAT_BASE_URL`、`CHAT_MODEL`；未配置时兼容旧的
  `DASHSCOPE_*` 变量。
- 知识库平台：`KB_API_TOKEN`（Bearer Token，形如
  kbmp-xxxx）、`KB_DOC_BASE_URL`（检索/上传）、`KB_MGMT_BASE_URL`（知识库/文档列表）、`KB_FAQ_BASE_URL`（FAQ
  检索）、`KB_BOTCODE`、`KB_FAQ_CHANNEL`、`KB_UPLOAD_KB_ID`、`KB_TIMEOUT_SECONDS`、`KB_MAX_CHUNKS`（传给
  LLM 的最相关片段数，3-5）、`KB_MIN_SIMILARITY`（相似度过滤阈值，0 为不过滤）。
- 反馈评价：`FEEDBACK_DB_PATH`（SQLite
  路径）、`FEEDBACK_API_URL`（可选，配置后异步转发到内网反馈入库接口，转发失败不影响本地入库）。

Embedding / Rerank / Milvus 相关配置已随知识库接口化改造移除。

## 会话持久化配置

当前会话持久化由 `app/core/session_persistence.py` 统一管理。

| 配置                                  | 说明                                                                              |
| ------------------------------------- | --------------------------------------------------------------------------------- |
| `SESSION_CHECKPOINT_BACKEND=memory`   | 默认模式，继续使用进程内 `MemorySaver`，服务重启后状态不保留                      |
| `SESSION_CHECKPOINT_BACKEND=postgres` | 使用 PostgreSQL checkpointer，启动时强依赖 PostgreSQL，连接或初始化失败则启动失败 |
| `POSTGRES_DSN`                        | PostgreSQL 连接串，例如 `postgresql://user:pass@localhost:5432/super_biz_agent`   |

PostgreSQL 模式下，LangGraph checkpoint 是 Agent 状态的权威存储；`chat_sessions`
表只保存前端历史列表所需的会话摘要，包括
`session_id`、`title`、`created_at`、`updated_at`、`last_message_preview` 和
`message_count`。

## 5. 核心链路一：RAG Chat Agent

### 入口

- API：`app/api/chat.py`
- Service：`app/services/rag_agent_service.py`
- 前端：`static/app.js` 中 `sendQuickMessage` 和 `sendStreamMessage`

### API

| 方法 | 路径                             | 说明                         |
| ---- | -------------------------------- | ---------------------------- |
| POST | `/api/chat`                      | 普通问答，一次性返回完整答案 |
| POST | `/api/chat_stream`               | SSE 流式问答                 |
| POST | `/api/chat/clear`                | 清空某个 session 的会话历史  |
| GET  | `/api/chat/session/{session_id}` | 查询某个 session 的历史消息  |
| GET  | `/api/chat/sessions`             | 查询服务端会话摘要列表       |

### 数据流

1. 前端发送 `{ Id, Question }`。
1. `ChatRequest` 使用 alias 将 `Id` 映射为 `id`，将 `Question` 映射为 `question`。
1. `chat.py` 调用 `rag_agent_service.query(...)` 或 `query_stream(...)`。
1. `RagAgentService` 首次调用时执行 `_initialize_agent()`：
   - 加载本地工具：`retrieve_knowledge`、`get_current_time`
   - 加载 MCP 工具：通过 `get_mcp_client_with_retry().get_tools()`
   - 使用 `create_agent(...)` 创建 LangChain Agent
   - 通过 `session_persistence_manager` 按 `thread_id=session_id` 保存会话上下文，支持
     `MemorySaver` 或 PostgreSQL checkpointer
1. Agent 根据用户问题决定是否调用工具。
1. 最终将模型回答返回给 API 层。
1. 流式接口将内部 chunk 包装为 SSE `message` 事件返回前端。

### 当前特点

- RAG 不是固定的“先检索再生成”，而是 Agent 自主决定是否调用 `retrieve_knowledge`。
- 会话状态可通过 `SESSION_CHECKPOINT_BACKEND=memory|postgres` 显式选择；`postgres` 模式使用
  PostgreSQL checkpointer 持久化 LangGraph 状态。
- 代码中定义了 `trim_messages_middleware`，但当前没有实际接入 `create_agent` 调用链路。
- 流式接口透出模型文本片段，并在 `complete` 前推送 `sources`
  事件（本次问答命中的知识片段），前端据此渲染引用来源卡片；工具调用中间过程（参数/耗时）的可观测性仍较弱。

## 6. 核心链路二：知识库平台 API 检索与引用溯源

### 入口

- 平台 API 客户端：`app/services/kb_api_service.py`（检索/上传/知识库列表/文档列表/FAQ）
- 检索工具：`app/tools/knowledge_tool.py`
- 检索上下文：`app/services/retrieval_context.py`（ContextVar 记录一次问答命中的知识片段）
- 文件上传 API：`app/api/file.py`（透传平台上传接口）
- 知识库管理 API：`app/api/kb.py`（列表/文档/FAQ 检索）

### 检索数据流

1. Agent 调用 `retrieve_knowledge(query)`。
1. 工具通过 `kb_api_service.retrieve(query)` 调用平台 `POST /v1/doc/retrieval/`（混合检索 +
   重排由平台完成）。
1. 按 `KB_MIN_SIMILARITY` 过滤低质量片段，截断为最相关 `KB_MAX_CHUNKS` 个。
1. `retrieval_context.record(chunks)` 记录本次命中的片段（问答开始时 `begin()`，结束时
   `collect()`）。
1. 片段以带 `[1][2]` 编号的上下文文本返回给 LLM，提示词强制引用编号；无答案时回复“无法基于当前知识库回答”防止幻觉。
1. API 层将 `answer + sources`（片段 id/文档名/相似度/内容）返回前端；流式接口在 `complete` 事件前推送
   `sources` 事件。

### 上传数据流

1. 用户上传文件到 `/api/upload`（支持 PDF/Word/Excel/PPT/图片等 14 种格式）。
1. `kb_api_service.upload_document(...)` 以 multipart 透传平台上传接口，目标知识库取
   `KB_UPLOAD_KB_ID`（留空则取知识库列表第一个）。
1. 解析、切分、向量化均由平台完成，本地不再保存或索引文件。

### 反馈评价链路

1. 前端每条回答提供 👍/👎；👎 弹出结构化负反馈弹窗（6 个标签 + 补充描述）。
1. `POST /api/feedback` 由 `feedback_service` 写入 SQLite（含
   question/answer/rating/tags/comment/chunk_ids）。
1. 配置 `FEEDBACK_API_URL` 后异步转发到内网反馈接口；`GET /api/feedback/list|stats|tags`
   供审核与知识修正使用。

### 当前特点

- 平台接口调用失败时降级返回空结果并记录日志，不中断对话。
- 反馈数据关联命中片段 ID，为后续“知识自进化”（LLM 初筛 + 人工审核 + 知识库回写）预留数据基础。

## 7. 核心链路三：AIOps Plan-Execute-Replan Agent

### 入口

- API：`app/api/aiops.py`
- Service：`app/services/aiops_service.py`
- 状态定义：`app/agent/aiops/state.py`
- 节点：`planner.py`、`executor.py`、`replanner.py`
- 前端：`static/app.js` 中 `triggerAIOps` 和 `sendAIOpsRequest`

### API

| 方法 | 路径         | 说明                                  |
| ---- | ------------ | ------------------------------------- |
| POST | `/api/aiops` | SSE 流式返回 AIOps 诊断过程和最终报告 |

### 状态结构

`PlanExecuteState` 包含：

- `input`：原始任务描述
- `plan`：待执行步骤列表
- `past_steps`：已执行步骤和结果，使用 `operator.add` 追加
- `response`：最终报告/响应

### 工作流

`AIOpsService._build_graph()` 构建 LangGraph 状态机：

```text
planner -> executor -> replanner -> executor -> replanner -> ... -> END
```

执行过程：

1. `diagnose(...)` 构造固定 AIOps 任务描述，要求输出 Markdown 告警分析报告。
1. `execute(...)` 初始化状态，并以 `thread_id=session_id` 执行图。
1. `planner`：
   - 先调用 `retrieve_knowledge` 检索内部经验文档。
   - 获取本地工具和 MCP 工具描述。
   - 调用 Qwen 结构化输出 `Plan(steps=[...])`。
1. `executor`：
   - 每次只执行 `plan[0]`。
   - 将本地工具和 MCP 工具绑定到模型。
   - 模型决定是否生成 tool calls。
   - `ToolNode` 执行工具调用。
   - 模型基于工具结果整理当前步骤执行结果。
1. `replanner`：
   - 根据 `past_steps` 和剩余 `plan` 做结构化决策。
   - 决策包括 `continue`、`replan`、`respond`。
   - 超过最大步数会强制生成响应，避免无限循环。
1. `aiops_service` 将节点状态增量转换为 SSE 事件：
   - `plan`
   - `step_complete`
   - `status`
   - `report`
   - `complete`
   - `error`

### 当前特点

- AIOps 设计上比普通 RAG 更像 Agent 工作流，有明确状态、计划、执行、评估和终止条件。
- `planner` 会先查知识库经验，这为后续沉淀 SOP/Runbook 留了入口。
- `executor` 每步重新加载 MCP 工具并创建 LLM/ToolNode，逻辑清晰但有性能优化空间。
- `replanner` 有最大步数和 replan 限制，具备基本防无限循环机制。
- 目前 `/api/aiops` 的任务描述是固定的，不支持用户传入具体告警、服务名或时间窗口。

## 8. MCP 工具链路

### Client

- `app/agent/mcp_client.py`
- 使用全局单例 `_mcp_client`。
- 默认配置来自 `config.mcp_servers`：
  - `cls`：`http://localhost:8003/mcp`
  - `monitor`：`http://localhost:8004/mcp`
- `get_mcp_client_with_retry()` 自动添加 `retry_interceptor`。
- 工具调用失败时最多重试 3 次，失败后包装为 `CallToolResult(isError=True)`，避免整个 Agent 链路直接崩掉。

### Server

| 文件                            | 端口 | 主要工具                                | 当前性质               |
| ------------------------------- | ---: | --------------------------------------- | ---------------------- |
| `mcp_servers/cls_server.py`     | 8003 | 当前时间戳、地区/日志主题查询、日志查询 | Mock 日志数据          |
| `mcp_servers/monitor_server.py` | 8004 | CPU 指标、内存指标                      | 动态生成 mock 监控数据 |

当前 MCP Server 主要用于演示 Agent 调用外部工具的流程，不是真实云服务集成。

## 9. 前端交互

前端位于 `static/`，核心文件是 `static/app.js`。

主要能力：

- 新建会话与本地历史记录管理。
- 普通聊天：请求 `/api/chat`。
- 流式聊天：请求 `/api/chat_stream`，消费 SSE/stream 数据。
- 引用来源卡片：回答下方展示可折叠“引用来源 (N)”卡片，含文档名、相似度、片段内容，与回答中 `[1][2]` 编号对应。
- 反馈评价：每条回答支持 👍/👎；👎 弹出结构化负反馈弹窗（标签多选 + 评论），提交后按钮置为已提交状态。
- 文件上传：请求 `/api/upload`，透传知识库平台（支持 PDF/Word/Excel/PPT/图片等格式）。
- AIOps：点击侧边栏按钮触发 `/api/aiops`，展示计划、步骤进度和报告。
- Markdown 渲染和代码高亮。

当前前端启动时优先调用 `/api/chat/sessions` 加载服务端会话摘要，打开具体会话时调用
`/api/chat/session/{session_id}` 获取 LangGraph 历史；`localStorage` 保留为兼容回退。

## 10. 当前项目优势

- 已有端到端闭环，不只是孤立脚本。
- 同时包含 RAG 和 Agent Workflow 两类典型 LLM 应用模式。
- AIOps 采用 Plan-Execute-Replan，有一定工程复杂度和可扩展性。
- MCP 工具接入方式清晰，后续可替换为真实日志/监控系统。
- 知识库能力全部托管给内网平台，本项目保持轻量（无向量库/Embedding/Rerank 运维负担）。
- 回答强制引用溯源 + 反馈闭环入库，具备企业级问答的可信度与可运营性基础。
- SSE 流式输出已覆盖聊天和 AIOps 两个场景。

## 11. 当前风险与可完善点

| 优先级 | 问题                                          | 影响                                        | 后续方向                                                                           |
| ------ | --------------------------------------------- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| 高     | AIOps 输入固定                                | 无法诊断指定服务/告警/时间窗口              | 扩展 `AIOpsRequest`，支持服务名、告警名、时间范围、诊断目标                        |
| 高     | MCP Server 是 mock                            | 面试/项目展示时真实性不足                   | 增加真实/半真实数据源适配层，或沉淀可复现实验数据集                                |
| 高     | 工具调用过程可观测性不足                      | 前端难展示 Agent 为什么这么做               | 在 RAG/AIOps 流式事件中输出工具名、参数、结果摘要、耗时                            |
| 中     | 知识库平台接口无鉴权外的可用性依赖            | 内网平台不可达时检索降级为空结果            | 增加健康探测与前端提示；本地联调用 mock（见 docs/local-dev-guide.md）              |
| 低     | `/api/feedback/list` 无鉴权                   | 反馈数据（含问答内容）可被任意访问          | 后续统一接入认证/权限层                                                            |
| 低     | PostgreSQL 会话持久化依赖外部数据库和依赖同步 | `postgres` 模式下数据库不可用会导致启动失败 | 部署时配置 `SESSION_CHECKPOINT_BACKEND`、`POSTGRES_DSN` 并确保依赖安装和数据库可达 |
| 中     | 缺少测试                                      | 后续改功能风险较高                          | 增加 API、Service、工具和状态机测试                                                |
| 中     | AIOps 每步重复初始化模型/工具                 | 性能和延迟可优化                            | 缓存工具列表，复用 LLM/ToolNode，增加超时控制                                      |
| 低     | `trim_messages_middleware` 未接入             | 长对话上下文可能增长                        | 接入消息裁剪或总结记忆                                                             |
| 低     | 知识自进化仅有数据基础                        | 反馈未自动回写知识库                        | 基于 `GET /api/feedback/list` 接入 LLM 初筛 + 人工审核 + 平台回写                  |

## 12. 建议的后续功能演进路线

### 第一阶段：让项目更可用

- 扩展 AIOps 请求参数：服务名、告警类型、时间范围、诊断目标。
- 前端添加 AIOps 表单，而不是固定点击后直接诊断。
- 上传接口返回索引成功/失败状态。
- 增加知识库文件列表、删除、重建索引接口。

### 第二阶段：让 Agent 更透明

- RAG 流式输出增加工具调用事件。
- AIOps 输出每一步的工具名、参数、结果摘要、耗时。
- 前端增加“执行轨迹/证据链”面板。
- 为最终报告附带引用来源、指标截图/数据摘要、日志证据。

### 第三阶段：让项目更像企业级 Agent

- MCP Server 增加真实适配层或可配置数据源。
- 在 PostgreSQL 会话持久化基础上继续扩展用户/租户隔离、会话归档和管理能力。
- 增加权限、租户、数据源隔离配置。
- 增加 Agent 评测：工具调用准确率、诊断成功率、报告事实一致性、延迟和成本统计。
- 增加 observability：trace_id、span、结构化日志、调用耗时、错误分类。

## 13. 后续开发文档维护规则

后续每次改功能时，同步维护：

- `project-docs/task_plan.md`：记录当前任务目标、阶段、状态和关键决策。
- `project-docs/findings.md`：记录代码阅读发现、风险点、设计取舍。
- `project-docs/progress.md`：记录本次做了什么、改了哪些文件、如何验证。
- `project-docs/project_overview.md`：当架构、核心链路或模块职责发生变化时更新。
