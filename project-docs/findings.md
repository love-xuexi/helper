# SuperBizAgent 项目理解发现

## 2026-05-09 初始理解

### 项目定位

SuperBizAgent 是一个基于 FastAPI 的 Python Agent 项目，面向企业智能对话和智能运维场景。

### 技术栈

- Web/API：FastAPI、Uvicorn、SSE Starlette
- Agent 编排：LangChain、LangGraph
- LLM：统一通过 OpenAI-compatible Chat 配置接入，当前保留 DashScope / 通义千问旧配置作为兼容兜底
- 向量数据库：Milvus
- 工具协议：MCP，使用 `langchain-mcp-adapters` 与 `fastmcp`
- 前端：`static/` 下的原生 HTML/CSS/JS

### 已确认的核心入口

- `app/main.py`：FastAPI 应用入口，注册健康检查、聊天、文件上传、AIOps 路由，并在生命周期中连接/关闭 Milvus。
- `app/config.py`：Pydantic Settings 配置中心，读取 `.env`，管理 Chat、Embedding、Rerank、Milvus、RAG、MCP Server 配置，并兼容旧 DashScope / NVIDIA 变量。
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
- 会话状态通过 `session_persistence_manager` 管理，以 `session_id` 作为 LangGraph `thread_id`，可在内存和 PostgreSQL checkpointer 之间显式切换。
- 非流式接口返回最后一条消息内容；流式接口兼容从 `AIMessage` / `AIMessageChunk` 的 `content_blocks` 或字符串 `content` 中抽取文本片段。
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
- Embedding 使用 OpenAI-compatible Embedding 配置，默认维度为 1024；旧 DashScope embedding 配置仍可作为兜底；长 query 会在检索阶段压缩，长文档片段会在入库分割阶段继续切分。
- Milvus collection 名称固定为 `biz`，字段包括 `id`、`vector`、`content`、`metadata`。
- 当前上传接口即使索引失败也会返回上传成功，后续应改为明确返回索引状态。

## 2026-05-10 RAG 重排序实现补充

- 新增 `app/services/rag_retrieval_service.py`，将主 RAG 检索链路从 `retrieve_knowledge` 中拆出。
- 新增 `app/services/rerank_service.py`，实现远程 Rerank 和本地关键词重排序降级。
- 主链路变为：Milvus 候选召回 `rag_candidate_top_k` -> Rerank -> 截断 `rag_top_k` -> Agent 上下文。
- 当前 Rerank 支持 `openai_compatible` 和 `nvidia` 两类 provider；新配置读取 `RERANK_API_KEY`、`RERANK_BASE_URL`、`RERANK_MODEL`、`RERANK_PROVIDER`，旧 `NVIDIA_API_KEY` 和 `NVIDIA_BASE_URL` 仍作为兼容兜底。
- NVIDIA API Catalog 托管服务实测应调用 `https://ai.api.nvidia.com/v1/retrieval/{model}/reranking`；当 provider 为 `nvidia` 且配置 `https://integrate.api.nvidia.com` 时，代码会自动映射到该托管 endpoint。自部署 NeMo Retriever Reranking NIM 仍兼容显式 `/v1/ranking` 地址。
- 当 API key、base url 缺失或远程 Rerank API 调用失败时，系统不会中断 RAG，而是降级为本地关键词重排序。
- 企业级 rerank 方法主要包括 Cross-Encoder/Neural Rerank、Hybrid Retrieval + Rank Fusion、Metadata/Business Rule Rerank、LLM Judge/Listwise Rerank；本次实现了 OpenAI-compatible / NVIDIA remote rerank 和本地关键词 fallback 两类。

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
- 会话状态已支持 PostgreSQL 持久化模式；生产部署需显式配置 `SESSION_CHECKPOINT_BACKEND=postgres` 和 `POSTGRES_DSN`。
- 当前缺少系统测试和 Agent 评测体系，功能扩展后需要补齐。

## 2026-05-11 Windows 启动问题修复补充

- 根因 1：`start-windows.bat` / `stop-windows.bat` 原先包含中文 UTF-8 文本且使用 LF 换行，在 Windows `cmd.exe` 代码页不一致时会把中文字节解析成类似 `鍔?...` 的乱码命令。
- 根因 2：当前 `.python-version` 曾为空文件，启动脚本读取后不会得到有效 Python 版本。
- 根因 3：当前 `.venv` 中缺少 `pip`，真实运行 `start-windows.bat` 时在依赖安装阶段报 `No module named pip`。
- 根因 4：`stop-windows.bat` 原先只按窗口标题停止 FastAPI，但实际 Python 子进程窗口标题可能变成 `OleMainThreadWndName`，导致 9900 端口遗留监听。
- 修复：Windows 批处理脚本改为英文 ASCII 输出并保持 CRLF；`start-windows.bat` 增加 `.python-version` 空值修复、Python 版本检查、`ensurepip` 兜底、配置检查和日志重定向；`stop-windows.bat` 增加按 9900/8003/8004 端口查 PID 并停止的兜底逻辑。
- 验证：`start-windows.bat` 真实启动成功，Milvus/MCP/FastAPI 启动并且 `/health` 返回 200；`stop-windows.bat` 真实停止成功，最终 9900/8003/8004 监听数为 0，Milvus 运行容器数为 0。
- 注意：如果继续使用旧 DashScope 变量作为 Embedding 兜底，文档上传阶段仍会受该 API Key 有效性影响；这不影响 Windows 脚本可用性，但会影响知识库向量化。

## 2026-05-11 OpenAI-compatible 模型配置重构补充

- `app/config.py` 已新增 Chat、Embedding、Rerank 三组独立模型配置，并通过 `effective_*` 属性兼容旧变量。
- `app/core/llm_factory.py` 默认读取 `effective_chat_*`，RAG Agent 和 AIOps Planner/Executor/Replanner 均改为通过统一工厂创建 `ChatOpenAI`。
- `app/services/vector_embedding_service.py` 已从 DashScope 专用实现改为 OpenAI-compatible Embedding 实现，支持独立 `api_key`、`base_url`、`model`、`dimensions` 和 `encoding_format`。
- `app/services/rerank_service.py` 已抽象出 `RerankProvider` 和 `RerankService`，默认走 OpenAI-compatible `/rerank`，并保留 `NvidiaRerankService` 兼容 NVIDIA 特殊 endpoint。
- 新增 `tests/test_openai_compatible_config.py`，覆盖独立配置、旧配置兜底、LLMFactory、Embedding client 和 OpenAI-compatible Rerank endpoint 行为。

## 2026-05-11 Embedding 输入 token 限制处理

- 根因：SiliconFlow embedding 接口对单次 input 有 512 token 限制，长 query 或过大的文档分片原样传入时会触发 413。
- 新增 `app/services/embedding_input_guard.py`，提供保守 token 粗估、检索 query 智能压缩和尾部截断兜底。
- `app/config.py` 新增 `embedding_max_tokens` 和 `embedding_token_safety_margin`，默认按 512 - 32 = 480 的预算控制实际 embedding 输入。
- `rag_retrieval_service.retrieve()` 会先把长 query 压缩为安全 query，并将同一个安全 query 用于向量召回和 rerank。
- `document_splitter_service` 在知识库入库阶段按 embedding token 预算继续切分文档分片，不对原文做智能压缩或静默截断。
- `OpenAICompatibleEmbeddings.embed_documents()` 会逐条请求 embedding provider，并拒绝超预算文档片段，避免 batch 总长度或绕过分割导致 413。
- 智能压缩只用于用户检索 query，优先保留服务名、告警、错误码、状态码、CPU/内存/磁盘、日志、超时等高信号片段；若仍超限则截取尾部。

## 2026-05-11 Windows 日志可见性修复

- 根因 1：Windows 启动脚本用 `start ... > server.log 2>&1` 将 FastAPI 输出重定向到文件，启动窗口只显示批处理步骤，不会实时显示 FastAPI/业务日志。
- 根因 2：Windows 重定向场景下 Python stdout 可能使用 GBK 编码，应用启动日志中的 emoji 会触发 `UnicodeEncodeError`，导致 Loguru 控制台 sink 写入失败。
- 修复：`app/utils/logger.py` 在配置 Loguru 前将 `sys.stdout` reconfigure 为 UTF-8，并在非 TTY 输出时关闭颜色控制符。
- 修复：`app/main.py` 启动/关闭日志改为中文标签文本，例如 `[启动]`、`[Milvus]`、`[关闭]`，避免 Windows 终端对 emoji 的编码兼容问题。
- 修复：`start-windows.bat` 设置 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`，启动 FastAPI 后打开 `SuperBizAgent Logs` 窗口实时跟随 `server.log`，并在启动完成时打印最近 FastAPI 日志。
- 修复：`stop-windows.bat` 增加关闭 `SuperBizAgent Logs` 实时日志窗口的步骤。
- 验证：真实启动时控制台已能看到中文 FastAPI 日志，`server.log` 中 `UnicodeEncodeError` 数量为 0，停止后日志窗口数量为 0。


## 2026-05-27 PostgreSQL 会话持久化发现

- RAG Chat 和 AIOps 都使用 LangGraph `thread_id=session_id`，适合接入统一 checkpointer。
- FastAPI 路由会在 lifespan 前导入服务单例，因此 PostgreSQL 初始化后需要刷新 RAG/AIOps 服务持有的 checkpointer。
- LangGraph `checkpointer.get(...)` 在当前版本返回 checkpoint dict；历史读取逻辑需要兼容 dict、checkpoint tuple 和带 `checkpoint` 属性的对象。
- 前端历史列表不能只依赖 `localStorage`，需要后端提供轻量 `chat_sessions` 索引表用于跨重启展示会话摘要。
