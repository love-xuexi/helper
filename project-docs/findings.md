# SuperBizAgent 项目理解发现

## 2026-05-09 初始理解

### 项目定位

SuperBizAgent 是一个基于 FastAPI 的 Python Agent 项目，面向企业智能对话和智能运维场景。

### 技术栈

- Web/API：FastAPI、Uvicorn、SSE Starlette
- Agent 编排：LangChain、LangGraph
- LLM：阿里云 DashScope / 通义千问，当前核心模型配置为 `qwen-max`
- 向量数据库：Milvus
- 工具协议：MCP，使用 `langchain-mcp-adapters` 与 `fastmcp`
- 前端：`static/` 下的原生 HTML/CSS/JS

### 已确认的核心入口

- `app/main.py`：FastAPI 应用入口，注册健康检查、聊天、文件上传、AIOps 路由，并在生命周期中连接/关闭 Milvus。
- `app/config.py`：Pydantic Settings 配置中心，读取 `.env`，管理 DashScope、Milvus、RAG、MCP Server 配置。
- `app/api/chat.py`：RAG Chat HTTP API，提供 `/api/chat` 和 `/api/chat_stream`。
- `app/api/aiops.py`：AIOps 流式诊断 API，提供 `/api/aiops`。
- `app/services/rag_agent_service.py`：RAG Chat Agent 编排层。
- `app/services/aiops_service.py`：AIOps Plan-Execute-Replan 工作流编排层。
- `app/agent/mcp_client.py`：MCP Client 全局管理与工具调用重试拦截器。

### 已确认的主要能力

- 普通对话：`POST /api/chat`，一次性返回完整答案。
- 流式对话：`POST /api/chat_stream`，SSE 返回增量内容、工具调用、错误和完成事件。
- 文档上传：`POST /api/upload`，用于构建/更新知识库索引。
- AIOps 诊断：`POST /api/aiops`，流式返回计划、步骤执行、重规划和最终报告。

### 初步架构判断

项目不是单纯的 RAG Demo，而是包含两类 Agent：

1. RAG Chat Agent：模型可根据问题决定是否调用 `retrieve_knowledge`、`get_current_time` 或 MCP 工具。
2. AIOps Agent：通过 planner、executor、replanner 三类节点构建循环式 LangGraph 状态机。

## 2026-05-09 深入阅读补充

### RAG Chat Agent

- `RagAgentService` 首次调用时异步初始化 Agent，合并本地工具和 MCP 工具后调用 `create_agent(...)`。
- 本地工具包括 `retrieve_knowledge` 和 `get_current_time`。
- 会话状态使用 `MemorySaver`，以 `session_id` 作为 LangGraph `thread_id`。
- 非流式接口返回最后一条消息内容；流式接口主要从 `AIMessage` / `AIMessageChunk` 的 `content_blocks` 中抽取文本片段。
- 文件中存在 `trim_messages_middleware`，但当前未实际接入 Agent 初始化流程。

### AIOps Agent

- `AIOpsService` 将 `planner -> executor -> replanner` 组装成 LangGraph 循环状态机。
- `planner` 会先用 `retrieve_knowledge` 检索内部经验，再结合工具描述生成结构化计划。
- `executor` 每次只执行一个步骤，绑定本地工具和 MCP 工具，由模型决定是否调用工具，再用 `ToolNode` 执行。
- `replanner` 在 `continue`、`replan`、`respond` 之间做结构化决策，并用最大步数限制防止无限循环。
- `/api/aiops` 当前使用固定诊断任务，不支持用户传入具体服务、告警或时间窗口。

### 知识库链路

- `/api/upload` 支持 `.txt` 和 `.md`，保存到 `uploads/` 后调用 `vector_index_service.index_single_file(...)`。
- Markdown 文档先按 `#`、`##` 标题切分，再按字符长度二次切分，并合并过短片段。
- Embedding 使用 DashScope `text-embedding-v4`，维度为 1024。
- Milvus collection 名称固定为 `biz`，字段包括 `id`、`vector`、`content`、`metadata`。
- 当前上传接口即使索引失败也会返回上传成功，后续应改为明确返回索引状态。

### MCP 链路

- MCP Client 使用全局单例，配置来自 `config.mcp_servers`。
- `get_mcp_client_with_retry()` 会为 MCP 工具调用增加重试拦截器。
- `cls_server.py` 和 `monitor_server.py` 当前主要提供 mock 数据，用于演示日志和监控工具调用。

### 前端链路

- 前端位于 `static/`，主要逻辑在 `static/app.js`。
- 快速对话调用 `/api/chat`，流式对话调用 `/api/chat_stream`，文件上传调用 `/api/upload`，AIOps 调用 `/api/aiops`。
- 前端支持 Markdown 渲染、代码高亮、本地历史记录和 AIOps 流式过程展示。

### 后续重点风险

- AIOps 输入固定、MCP 数据 mock、工具调用轨迹不透明，是后续最值得优先完善的三类问题。
- 会话状态仅内存保存，不适合长期会话和生产部署。
- 当前缺少系统测试和 Agent 评测体系，功能扩展后需要补齐。

