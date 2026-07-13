# SuperBizAgent 项目概览

## 1. 项目定位

SuperBizAgent 是一个基于 Python 的智能业务 Agent 项目，当前主要面向两个场景：

- 普通知识库问答：用户通过 Web/API 提问，Agent 根据需要调用知识库检索工具、时间工具和 MCP 工具，生成回答。
- AIOps 智能运维诊断：系统通过 Plan-Execute-Replan 模式自动制定排查计划、调用监控/日志工具、动态重规划，并输出诊断报告。

整体上，它已经具备一个 Agent 应用闭环：前端页面、FastAPI 接口、LLM 调用、RAG 检索、Milvus 向量库、MCP 工具调用、SSE 流式输出。

## 2. 技术栈

| 层级 | 技术/组件 | 说明 |
|---|---|---|
| Web/API | FastAPI、Uvicorn、SSE Starlette | 提供 HTTP API、SSE 流式响应和静态页面服务 |
| Agent 编排 | LangChain、LangGraph | RAG Agent 和 AIOps Plan-Execute-Replan 工作流 |
| LLM | OpenAI 兼容 Chat 接口、`langchain_openai.ChatOpenAI` | 聊天、规划、执行、重规划、报告生成；可接入 DashScope、OpenAI 或其他兼容服务 |
| Embedding | OpenAI 兼容 Embedding 接口 | 文档和查询向量化，默认维度为 1024，可按服务商配置调整，并对长输入做 token 预算保护 |
| 向量库 | Milvus | 存储知识库文档分片和向量，collection 名称为 `biz` |
| 工具协议 | MCP、FastMCP、langchain-mcp-adapters | 对接日志查询和监控查询工具 |
| 前端 | 原生 HTML/CSS/JS | 支持聊天、流式输出、文件上传、AIOps 触发 |

## 3. 启动与运行链路

主要启动入口是 `app/main.py`。

启动时：

1. FastAPI 创建应用实例。
2. 注册 CORS、静态文件和 API 路由。
3. 在 lifespan 中连接 Milvus，并初始化/加载 `biz` collection。
4. 用户访问 `/` 时返回 `static/index.html`。
5. 用户通过前端或 API 调用 `/api/chat`、`/api/chat_stream`、`/api/upload`、`/api/aiops`。

Windows 推荐使用：

```powershell
.\start-windows.bat
```

手动启动时通常需要：

1. Docker 启动 Milvus：`docker compose -f vector-database.yml up -d`
2. 启动 MCP Server：`python mcp_servers/cls_server.py`、`python mcp_servers/monitor_server.py`
3. 启动主服务：`python -m uvicorn app.main:app --host 0.0.0.0 --port 9983`
4. 访问：`http://localhost:9983`

## 4. 目录职责

| 路径 | 职责 |
|---|---|
| `app/main.py` | FastAPI 应用入口，生命周期、路由、静态文件 |
| `app/config.py` | Pydantic Settings 配置中心，读取 `.env` |
| `app/api/` | HTTP API 层，负责请求/响应和 SSE 包装 |
| `app/services/` | 业务服务层，包括 RAG Agent、AIOps 工作流、向量索引/检索 |
| `app/agent/` | Agent 相关实现，包括 MCP Client 和 AIOps 节点 |
| `app/tools/` | LangChain 本地工具，如知识库检索、当前时间 |
| `app/core/` | Milvus Client、LLM Factory 等基础组件 |
| `app/models/` | Pydantic 请求/响应模型 |
| `mcp_servers/` | 本地 MCP Server，提供日志和监控 mock 工具 |
| `static/` | 原生前端页面、样式和交互逻辑 |
| `aiops-docs/` | 预期作为 AIOps 知识库语料目录，目前目录为空 |
| `project-docs/` | 本次新建的项目理解、计划和后续开发沉淀目录 |

## 4.1 模型配置结构

模型服务已拆分为三组独立配置：

- Chat：`CHAT_API_KEY`、`CHAT_BASE_URL`、`CHAT_MODEL`
- Embedding：`EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_DIMENSIONS`、`EMBEDDING_ENCODING_FORMAT`、`EMBEDDING_MAX_TOKENS`、`EMBEDDING_TOKEN_SAFETY_MARGIN`
- Rerank：`RERANK_API_KEY`、`RERANK_BASE_URL`、`RERANK_MODEL`、`RERANK_PROVIDER`

配置优先级是新变量优先，旧变量兼容兜底：

- Chat 未配置时兼容 `DASHSCOPE_API_KEY`、`DASHSCOPE_API_BASE`、`RAG_MODEL`、`DASHSCOPE_MODEL`。
- Embedding 未配置时兼容 `DASHSCOPE_API_KEY`、`DASHSCOPE_API_BASE`、`DASHSCOPE_EMBEDDING_MODEL`。
- Rerank 未配置时兼容 `NVIDIA_API_KEY`、`NVIDIA_BASE_URL`，并保留 NVIDIA API Catalog endpoint 自动映射逻辑。

默认路径统一走 OpenAI-compatible 调用；特殊模型或服务商通过 provider 或专用适配逻辑处理。

Embedding 输入预算默认按 `EMBEDDING_MAX_TOKENS - EMBEDDING_TOKEN_SAFETY_MARGIN` 计算。用户检索 query 过长时会先做智能压缩，优先保留服务名、告警、错误码、状态码、CPU/内存/磁盘等高信号片段；如果仍超限，再从尾部截断。知识库文档入库阶段不会对原文做智能压缩或静默截断，而是在文档分割阶段继续切分为更小分片，避免 embedding 服务返回 413 token 超限。

## 会话持久化配置

当前会话持久化由 `app/core/session_persistence.py` 统一管理。

| 配置 | 说明 |
|---|---|
| `SESSION_CHECKPOINT_BACKEND=memory` | 默认模式，继续使用进程内 `MemorySaver`，服务重启后状态不保留 |
| `SESSION_CHECKPOINT_BACKEND=postgres` | 使用 PostgreSQL checkpointer，启动时强依赖 PostgreSQL，连接或初始化失败则启动失败 |
| `POSTGRES_DSN` | PostgreSQL 连接串，例如 `postgresql://user:pass@localhost:5432/super_biz_agent` |

PostgreSQL 模式下，LangGraph checkpoint 是 Agent 状态的权威存储；`chat_sessions` 表只保存前端历史列表所需的会话摘要，包括 `session_id`、`title`、`created_at`、`updated_at`、`last_message_preview` 和 `message_count`。

## 5. 核心链路一：RAG Chat Agent

### 入口

- API：`app/api/chat.py`
- Service：`app/services/rag_agent_service.py`
- 前端：`static/app.js` 中 `sendQuickMessage` 和 `sendStreamMessage`

### API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 普通问答，一次性返回完整答案 |
| POST | `/api/chat_stream` | SSE 流式问答 |
| POST | `/api/chat/clear` | 清空某个 session 的会话历史 |
| GET | `/api/chat/session/{session_id}` | 查询某个 session 的历史消息 |
| GET | `/api/chat/sessions` | 查询服务端会话摘要列表 |

### 数据流

1. 前端发送 `{ Id, Question }`。
2. `ChatRequest` 使用 alias 将 `Id` 映射为 `id`，将 `Question` 映射为 `question`。
3. `chat.py` 调用 `rag_agent_service.query(...)` 或 `query_stream(...)`。
4. `RagAgentService` 首次调用时执行 `_initialize_agent()`：
   - 加载本地工具：`retrieve_knowledge`、`get_current_time`
   - 加载 MCP 工具：通过 `get_mcp_client_with_retry().get_tools()`
   - 使用 `create_agent(...)` 创建 LangChain Agent
   - 通过 `session_persistence_manager` 按 `thread_id=session_id` 保存会话上下文，支持 `MemorySaver` 或 PostgreSQL checkpointer
5. Agent 根据用户问题决定是否调用工具。
6. 最终将模型回答返回给 API 层。
7. 流式接口将内部 chunk 包装为 SSE `message` 事件返回前端。

### 当前特点

- RAG 不是固定的“先检索再生成”，而是 Agent 自主决定是否调用 `retrieve_knowledge`。
- 会话状态可通过 `SESSION_CHECKPOINT_BACKEND=memory|postgres` 显式选择；`postgres` 模式使用 PostgreSQL checkpointer 持久化 LangGraph 状态。
- 代码中定义了 `trim_messages_middleware`，但当前没有实际接入 `create_agent` 调用链路。
- 流式接口主要透出模型文本片段，对工具调用过程的前端可观测性还比较弱。

## 6. 核心链路二：知识库构建与检索

### 入口

- 文件上传 API：`app/api/file.py`
- 文档切分：`app/services/document_splitter_service.py`
- 向量索引：`app/services/vector_index_service.py`
- 向量存储：`app/services/vector_store_manager.py`
- Embedding：`app/services/vector_embedding_service.py`
- 检索工具：`app/tools/knowledge_tool.py`

### 构建数据流

1. 用户上传 `.txt` 或 `.md` 文件到 `/api/upload`。
2. 文件保存到 `uploads/`。
3. `vector_index_service.index_single_file(...)` 读取文件内容。
4. 根据 `_source` 删除 Milvus 中同文件旧分片。
5. `document_splitter_service.split_document(...)` 切分文档：
   - Markdown：先按 `#`、`##` 标题切分，再按字符长度二次切分，并合并过短分片。
   - TXT：直接使用递归字符切分。
6. `vector_store_manager.add_documents(...)` 生成 UUID、调用 embedding、写入 Milvus。
7. 文档进入 `biz` collection，字段包括 `id`、`content`、`vector`、`metadata`。如果分片超过 embedding token 预算，分割服务会继续切成更小分片，而不是压缩或截断原文。

### 检索数据流

1. Agent 调用 `retrieve_knowledge(query)`。
2. 工具调用 `rag_retrieval_service.retrieve(query)`。
3. 检索服务先将超长 query 压缩为 embedding 安全输入，再通过 LangChain Milvus retriever 扩大召回 `rag_candidate_top_k` 个候选分片。
4. `rerank_service` 根据 `RERANK_PROVIDER` 使用同一个安全 query，通过 OpenAI-compatible `/rerank` 或 NVIDIA 特殊 endpoint 对候选文档按 query-document 相关性重排序。
5. 重排序成功后截断为 `rag_top_k` 个最终文档；如果远程 rerank API 不可用，则降级为本地关键词重排序。
6. `format_docs(...)` 将最终文档格式化为带来源和标题的上下文文本。
7. 工具结果返回给 Agent，Agent 再组织答案。

### 当前特点

- 只支持 `.txt`、`.md`。
- 上传接口即使索引失败也会返回上传成功，只在日志中记录索引失败。
- `vector_search_service.py` 提供了更底层的 PyMilvus 检索封装；当前主 RAG 工具通过 `rag_retrieval_service.py` 使用 LangChain Milvus retriever 做候选召回，再进入 rerank。
- RAG 已支持 OpenAI-compatible Rerank，并保留 NVIDIA 特殊 provider；配置来自 `RERANK_*`，旧 `NVIDIA_*` 变量仍作为兼容兜底。
- RAG 检索入口会对长 query 做智能压缩；知识库入库阶段通过文档继续切分控制 token 预算，避免长文档片段触发 embedding provider 的 512 token 限制。
- 目前没有文档列表、删除文档、重建索引、检索结果调试等管理接口。

## 7. 核心链路三：AIOps Plan-Execute-Replan Agent

### 入口

- API：`app/api/aiops.py`
- Service：`app/services/aiops_service.py`
- 状态定义：`app/agent/aiops/state.py`
- 节点：`planner.py`、`executor.py`、`replanner.py`
- 前端：`static/app.js` 中 `triggerAIOps` 和 `sendAIOpsRequest`

### API

| 方法 | 路径 | 说明 |
|---|---|---|
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
2. `execute(...)` 初始化状态，并以 `thread_id=session_id` 执行图。
3. `planner`：
   - 先调用 `retrieve_knowledge` 检索内部经验文档。
   - 获取本地工具和 MCP 工具描述。
   - 调用 Qwen 结构化输出 `Plan(steps=[...])`。
4. `executor`：
   - 每次只执行 `plan[0]`。
   - 将本地工具和 MCP 工具绑定到模型。
   - 模型决定是否生成 tool calls。
   - `ToolNode` 执行工具调用。
   - 模型基于工具结果整理当前步骤执行结果。
5. `replanner`：
   - 根据 `past_steps` 和剩余 `plan` 做结构化决策。
   - 决策包括 `continue`、`replan`、`respond`。
   - 超过最大步数会强制生成响应，避免无限循环。
6. `aiops_service` 将节点状态增量转换为 SSE 事件：
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

| 文件 | 端口 | 主要工具 | 当前性质 |
|---|---:|---|---|
| `mcp_servers/cls_server.py` | 8003 | 当前时间戳、地区/日志主题查询、日志查询 | Mock 日志数据 |
| `mcp_servers/monitor_server.py` | 8004 | CPU 指标、内存指标 | 动态生成 mock 监控数据 |

当前 MCP Server 主要用于演示 Agent 调用外部工具的流程，不是真实云服务集成。

## 9. 前端交互

前端位于 `static/`，核心文件是 `static/app.js`。

主要能力：

- 新建会话与本地历史记录管理。
- 普通聊天：请求 `/api/chat`。
- 流式聊天：请求 `/api/chat_stream`，消费 SSE/stream 数据。
- 文件上传：请求 `/api/upload`。
- AIOps：点击侧边栏按钮触发 `/api/aiops`，展示计划、步骤进度和报告。
- Markdown 渲染和代码高亮。

当前前端启动时优先调用 `/api/chat/sessions` 加载服务端会话摘要，打开具体会话时调用 `/api/chat/session/{session_id}` 获取 LangGraph 历史；`localStorage` 保留为兼容回退。

## 10. 当前项目优势

- 已有端到端闭环，不只是孤立脚本。
- 同时包含 RAG 和 Agent Workflow 两类典型 LLM 应用模式。
- AIOps 采用 Plan-Execute-Replan，有一定工程复杂度和可扩展性。
- MCP 工具接入方式清晰，后续可替换为真实日志/监控系统。
- 文档切分、向量化、Milvus 写入和检索链路完整。
- SSE 流式输出已覆盖聊天和 AIOps 两个场景。

## 11. 当前风险与可完善点

| 优先级 | 问题 | 影响 | 后续方向 |
|---|---|---|---|
| 高 | AIOps 输入固定 | 无法诊断指定服务/告警/时间窗口 | 扩展 `AIOpsRequest`，支持服务名、告警名、时间范围、诊断目标 |
| 高 | MCP Server 是 mock | 面试/项目展示时真实性不足 | 增加真实/半真实数据源适配层，或沉淀可复现实验数据集 |
| 高 | 工具调用过程可观测性不足 | 前端难展示 Agent 为什么这么做 | 在 RAG/AIOps 流式事件中输出工具名、参数、结果摘要、耗时 |
| 中 | 上传成功不代表索引成功 | 用户会误以为知识库已更新 | 上传接口返回索引状态，失败时给出明确错误 |
| 低 | PostgreSQL 会话持久化依赖外部数据库和依赖同步 | `postgres` 模式下数据库不可用会导致启动失败 | 部署时配置 `SESSION_CHECKPOINT_BACKEND`、`POSTGRES_DSN` 并确保依赖安装和数据库可达 |
| 中 | RAG 检索链路较简单 | 缺少召回质量保障 | 增加检索调试、得分展示、rerank、metadata filter |
| 中 | 缺少测试 | 后续改功能风险较高 | 增加 API、Service、工具和状态机测试 |
| 中 | AIOps 每步重复初始化模型/工具 | 性能和延迟可优化 | 缓存工具列表，复用 LLM/ToolNode，增加超时控制 |
| 低 | `trim_messages_middleware` 未接入 | 长对话上下文可能增长 | 接入消息裁剪或总结记忆 |
| 低 | 仅支持 txt/md | 知识库格式有限 | 支持 PDF、DOCX、HTML、日志文件等格式 |

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
