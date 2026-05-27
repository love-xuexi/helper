# SuperBizAgent 项目进度记录

## 2026-05-09

### 已完成

- 检查项目根目录，确认暂无已有 `task_plan.md` / `findings.md` / `progress.md`。
- 初步读取 README、`pyproject.toml`、目录结构、核心服务文件搜索结果。
- 新建 `project-docs/` 作为项目理解与后续开发沉淀目录。
- 创建 `task_plan.md`、`findings.md`、`progress.md` 三个持续维护文件。
- 深入阅读并理解 RAG Chat Agent、AIOps Plan-Execute-Replan Agent、MCP Client/Server、向量库构建和检索、文件上传、前端请求链路。
- 创建 `project_overview.md`，沉淀项目定位、技术栈、模块职责、核心数据流、风险点和后续演进路线。
- 更新 `task_plan.md` 和 `findings.md`，标记本轮项目理解任务完成。

### 本轮结论

- 项目当前已经具备端到端 Agent 应用闭环，包括前端、API、RAG、Milvus、MCP、LangGraph 工作流和 SSE。
- 后续优先完善方向建议聚焦在：AIOps 请求参数化、工具调用轨迹可观测、知识库管理能力、MCP 真实数据源适配、持久化会话和测试/评测体系。

### 待后续任务触发

- 根据用户下一步指定的功能方向，继续在 `project-docs/` 中补充设计方案、实施计划、变更记录和验证结果。

## 2026-05-10 / 2026-05-11

### 已完成

- 为 RAG 检索链路增加重排序设计与实现。
- 新增 `app/services/rerank_service.py`，封装 NVIDIA NeMo Retriever Reranking NIM 调用。
- 新增 `app/services/rag_retrieval_service.py`，将主链路调整为候选召回、rerank、最终截断。
- 修改 `app/tools/knowledge_tool.py`，让 `retrieve_knowledge` 通过新的检索流水线获取最终文档。
- 修改 `app/config.py`，新增 `rag_candidate_top_k`、`rerank_enabled`、`rerank_model`、`rerank_timeout_seconds`、`nvidia_api_key`、`nvidia_base_url`。
- 新增 `tests/test_rerank_service.py`，覆盖本地关键词降级、NVIDIA response index 排序、托管 endpoint 映射、显式 `/v1/ranking` 兼容、API 失败降级和检索流水线候选召回。
- 更新 README、`project_overview.md`、`findings.md`、`task_plan.md`，记录配置和链路变化。

### 验证结果

- 已运行 `python -m py_compile app\services\rerank_service.py app\services\rag_retrieval_service.py app\tools\knowledge_tool.py app\config.py tests\test_rerank_service.py`，语法编译通过。
- 已用 stub 注入方式验证 `rerank_service.py` 和 `rag_retrieval_service.py` 核心逻辑：本地关键词重排、NVIDIA URL 拼接、标准 `rankings` 响应解析、list 响应解析、API 失败降级、候选召回 top-k 和 rerank top-k 传递均通过。
- 已安装 dev 依赖并运行 `$env:DEBUG='false'; .\.venv\Scripts\python.exe -m pytest tests\test_rerank_service.py -q --no-cov`，结果 `7 passed`。
- 已用真实 NVIDIA API smoke test 验证托管 endpoint：`https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking` 调用成功，CPU 查询将 CPU 排查文档重排到第一名。
- 当前 `.env` 中 `DEBUG` 值会被 Pydantic 解析为非法布尔值，测试时需临时设置 `$env:DEBUG='false'`，或将 `.env` 中的 `DEBUG` 改为 `true/false`。

### 后续建议

- Windows 当前可用 `python -m uv` 绕过 `uv.exe` 不在 PATH 的问题，例如 `python -m uv pip install -e ".[dev]" --python .\.venv\Scripts\python.exe`。
- 启动服务后用真实知识库问题做端到端验证，观察日志中的候选召回数量、rerank 成功/降级状态和最终文档数量。

## 2026-05-11 Windows 启动脚本修复

### 已完成

- 将 `start-windows.bat` / `stop-windows.bat` 改为英文 ASCII 输出并保留 Windows CRLF 换行。
- 修复空 `.python-version`，当前内容为 `3.13`。
- 在 `start-windows.bat` 中增加虚拟环境 `pip` 检查和 `ensurepip` 兜底。
- 在 `stop-windows.bat` 中增加按端口 `9900`、`8003`、`8004` 查找并停止 PID 的兜底逻辑。
- 更新 README 的 Windows 启动说明、Python 版本要求和乱码 FAQ。

### 验证结果

- 已真实运行 `cmd /c "set NO_PAUSE=1&& call start-windows.bat"`，退出码 `0`；Milvus/MCP/FastAPI 启动成功，FastAPI `/health` 返回 `200`。
- 已真实运行 `cmd /c "set NO_PAUSE=1&& call stop-windows.bat"`，退出码 `0`；停止后 9900/8003/8004 监听数为 0，Milvus 运行容器数为 0。

## 2026-05-11 Windows 日志显示修复

### 已完成

- 新增 `tests/test_logger_config.py`，覆盖 Windows/GBK stdout 下中文日志和特殊字符导致 Loguru 控制台 sink 写入失败的问题。
- 修改 `app/utils/logger.py`，在配置日志前将 stdout 调整为 UTF-8，并在输出不是 TTY 时关闭颜色控制符。
- 修改 `app/main.py`，将启动/关闭日志中的 emoji 替换为中文标签文本，保留中文日志内容。
- 修改 `start-windows.bat`，设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，启动 `SuperBizAgent Logs` 窗口实时跟随 `server.log`，并在启动完成时打印最近 FastAPI 日志。
- 修改 `stop-windows.bat`，增加关闭实时日志窗口步骤。
- 更新 README，补充 Windows 下手动实时查看 `server.log` 的 PowerShell 命令。

### 验证结果

- 已运行 `$env:DEBUG='false'; .\.venv\Scripts\python.exe -m pytest tests\test_logger_config.py tests\test_rerank_service.py -q --no-cov`，结果 `8 passed`。
- 已运行 `.\.venv\Scripts\python.exe -m py_compile app\utils\logger.py app\main.py app\config.py`，语法编译通过。
- 已真实运行 `cmd /c "set NO_PAUSE=1&& call start-windows.bat"`，退出码 `0`；启动输出包含中文 FastAPI 日志，实时日志窗口 `SuperBizAgent Logs` 存在，`/health` 返回 `200`。
- 已真实运行 `cmd /c "set NO_PAUSE=1&& call stop-windows.bat"`，退出码 `0`。
- 停止后检查：`listen_port_count=0`，`superbizagent_log_windows=0`，`running_milvus_count=0`。
- 日志错误检查：`server_log_unicode_errors=0`。

### 仍需用户处理

- 如果继续使用旧 DashScope 变量作为 Embedding 兜底，文档上传索引仍依赖有效 API Key；也可以改用新的 `EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL` 和 `EMBEDDING_MODEL` 单独配置向量化服务。

## 2026-05-11 OpenAI-compatible 模型配置重构

### 已完成

- 修改 `app/config.py`，新增 Chat、Embedding、Rerank 三组独立 OpenAI-compatible 配置，并保留旧 DashScope / NVIDIA 配置作为兼容兜底。
- 修改 `app/core/llm_factory.py`，让默认 Chat 模型读取 `effective_chat_*` 配置。
- 修改 `app/services/vector_embedding_service.py`，将 embedding 调用从 DashScope 硬编码改为 OpenAI-compatible client，支持独立 API Key、Base URL、模型名、维度和编码格式。
- 修改 `app/services/rerank_service.py`，新增 `RerankProvider` 和通用 `RerankService`，支持 `openai_compatible` `/rerank` endpoint，并通过 `NvidiaRerankService` 保留 NVIDIA 特殊 endpoint 兼容。
- 修改 `app/services/rag_agent_service.py` 和 `app/agent/aiops/` 下的 planner、executor、replanner，让 RAG Chat 和 AIOps 均通过统一 `llm_factory` 创建模型。
- 新增 `tests/test_openai_compatible_config.py`，覆盖新配置独立性、旧配置兜底、LLMFactory、Embedding 和 OpenAI-compatible Rerank 行为。
- 更新 README、`project_overview.md`、`findings.md`，记录新的模型配置结构和兼容策略。

### 验证结果

- 已运行 `.\.venv\Scripts\python.exe -m pytest tests\test_openai_compatible_config.py tests\test_rerank_service.py -q --no-cov`，结果 `12 passed`。

### 后续建议

- 根据实际服务商补齐 `.env` 中的 `CHAT_*`、`EMBEDDING_*`、`RERANK_*` 配置；如果继续使用旧变量，代码仍会兜底兼容。
- 对真实 Chat、Embedding、Rerank 服务分别做 smoke test，确认各服务商 endpoint、payload 和返回结构完全匹配。

## 2026-05-11 Embedding 输入 token 限制处理

### 已完成

- 新增 `app/services/embedding_input_guard.py`，实现保守 token 粗估、检索 query 智能压缩和尾部截断兜底。
- 修改 `app/config.py`，新增 `embedding_max_tokens` 和 `embedding_token_safety_margin`，默认按 512 token 上限预留 32 token 安全边际。
- 修改 `app/services/document_splitter_service.py`，知识库文档入库时按 embedding token 预算继续切分超长分片，不智能压缩或静默截断原文。
- 修改 `app/services/vector_embedding_service.py`，`embed_query()` 保留检索 query 压缩，`embed_documents()` 逐条请求并拒绝超预算文档片段。
- 修改 `app/services/rag_retrieval_service.py`，在向量召回和 rerank 前先压缩超长 query，形成 RAG 入口层防护。
- 新增 `tests/test_document_splitter_service.py`，覆盖文档入库分片不会超过 embedding token 预算。
- 新增 `tests/test_embedding_input_guard.py`，覆盖高信号信息保留、低信号文本尾部兜底、截断行为和保守 token 估算。
- 新增 `tests/test_rag_retrieval_service.py`，验证 RAG 检索和 rerank 使用压缩后的安全 query。
- 更新 README、`project_overview.md`、`findings.md`、`task_plan.md`，记录长 embedding 输入的处理策略和配置项。

### 验证结果

- 已运行 `.\.venv\Scripts\python.exe -m pytest tests\test_document_splitter_service.py tests\test_embedding_input_guard.py tests\test_openai_compatible_config.py tests\test_rag_retrieval_service.py -q --no-cov`，结果通过。
- 已用本地脚本检查 `aiops-docs` 下 5 个文档分割结果，所有分片 `over_budget=0`。

### 后续建议

- 如果切换到 tokenizer 约束更严格的 embedding provider，可按实际限制调整 `EMBEDDING_MAX_TOKENS` 和 `EMBEDDING_TOKEN_SAFETY_MARGIN`。
- 如需更精确 token 计数，可后续按目标模型接入专用 tokenizer，但当前实现避免新增 tokenizer 依赖。


## 2026-05-27 PostgreSQL 会话持久化

### 已完成

- 新增 `SESSION_CHECKPOINT_BACKEND=memory|postgres`、`POSTGRES_DSN` 和 PostgreSQL 连接相关配置。
- 新增 `app/core/session_persistence.py`，统一创建内存或 PostgreSQL checkpointer，并维护 `chat_sessions` 会话摘要索引。
- FastAPI lifespan 启动时初始化会话持久化；`postgres` 模式下缺少 DSN 或数据库初始化失败会阻止启动。
- RAG Chat 和 AIOps 服务改为使用共享 checkpointer；RAG 成功回答后更新会话摘要，清空会话时同步删除会话索引。
- 新增 `GET /api/chat/sessions`，前端启动时优先加载服务端会话列表，`localStorage` 继续作为回退。
- 修复 `get_session_history()` 对 checkpoint dict 返回值的兼容性，避免历史消息读取为空。

### 验证结果

- 已运行 `python -m pytest tests/test_session_persistence.py tests/test_chat_sessions_api.py tests/test_rag_session_history.py -q --no-cov`，结果通过。
- 已运行 `python -m py_compile app/config.py app/core/session_persistence.py app/main.py app/api/chat.py app/models/response.py app/services/rag_agent_service.py app/services/aiops_service.py`，语法编译通过。
- 已运行 `node --check static/app.js`，前端脚本语法检查通过。

### 注意事项

- 当前环境未安装 `uv`，`uv.lock` 尚未同步新增 PostgreSQL 依赖；部署前需要在具备 `uv` 的环境执行 `uv lock` 或等效依赖同步。
- 当前虚拟环境尚未安装 `langgraph-checkpoint-postgres` 和 `psycopg`，启用 `SESSION_CHECKPOINT_BACKEND=postgres` 前需要安装依赖并准备 PostgreSQL。
