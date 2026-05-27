# 2026-05-27 PostgreSQL 会话持久化任务总结

## 背景

原项目的 RAG Chat 和 AIOps LangGraph 状态默认使用进程内 `MemorySaver`，前端历史主要依赖浏览器 `localStorage`。服务重启后，Agent 上下文和前端服务端历史无法稳定恢复。

本次改造目标是通过 PostgreSQL 实现可选的分布式会话隔离与状态保存，保障选择 PostgreSQL 模式后服务无损重启不丢 Agent 记忆。

## 设计决策

- 使用显式配置开关 `SESSION_CHECKPOINT_BACKEND=memory|postgres`。
- 默认 `memory`，保持本地开发和既有行为不变。
- 选择 `postgres` 时强依赖 `POSTGRES_DSN`，连接或初始化失败时启动失败。
- LangGraph checkpoint 是完整 Agent 状态的权威存储。
- 额外维护轻量 `chat_sessions` 表，只用于前端历史会话列表展示。

## 修改文件

### 后端配置与依赖

- `pyproject.toml`：新增 `langgraph-checkpoint-postgres`、`psycopg[binary,pool]`。
- `app/config.py`：新增 `SESSION_CHECKPOINT_BACKEND`、`POSTGRES_DSN`、PostgreSQL 连接超时等配置。

### 持久化核心

- `app/core/session_persistence.py`：新增 `SessionPersistenceManager`、`PostgresSessionStore` 和 `ChatSessionMetadata`。
- `app/main.py`：在 FastAPI lifespan 初始化/关闭会话持久化，并刷新 RAG/AIOps 服务 checkpointer。

### Agent 服务接入

- `app/services/rag_agent_service.py`：改为使用共享 checkpointer；成功回答后更新 `chat_sessions`；清空会话时同步删除 checkpoint 和索引；修复 checkpoint dict 历史读取兼容。
- `app/services/aiops_service.py`：改为使用共享 checkpointer，并支持启动后重新配置。

### API 与前端

- `app/models/response.py`：新增 `ChatSessionSummary`、`ChatSessionListResponse`。
- `app/api/chat.py`：新增 `GET /api/chat/sessions`。
- `static/app.js`：启动时优先加载服务端会话列表，发送消息后刷新服务端会话摘要，保留 `localStorage` 回退。

### 文档与测试

- `README.md`：新增 PostgreSQL 会话持久化配置、使用方式、API 和故障排查。
- `project-docs/project_overview.md`：更新架构说明、风险点和后续演进。
- `project-docs/findings.md`：记录持久化接入发现。
- `project-docs/progress.md`：记录本次实现与验证结果。
- `project-docs/task_plan.md`：标记 PostgreSQL 会话持久化完成。
- `tests/test_session_persistence.py`：覆盖配置和持久化核心。
- `tests/test_chat_sessions_api.py`：覆盖会话列表 API。
- `tests/test_rag_session_history.py`：覆盖 checkpoint dict 历史读取。

## 使用方式

### 继续使用内存模式

不配置或显式配置：

```bash
SESSION_CHECKPOINT_BACKEND=memory
```

适合本地开发。服务重启后 Agent 状态不会保留。

### 启用 PostgreSQL 模式

1. 安装新增依赖：

```bash
uv sync
# 或
pip install "langgraph-checkpoint-postgres>=2.0.0" "psycopg[binary,pool]>=3.2.0"
```

2. 创建 PostgreSQL 数据库，例如 `super_biz_agent`。

3. 在 `.env` 中配置：

```bash
SESSION_CHECKPOINT_BACKEND=postgres
POSTGRES_DSN=postgresql://user:password@localhost:5432/super_biz_agent
POSTGRES_CONNECT_TIMEOUT_SECONDS=10
```

4. 启动服务。启动成功后，应用会自动初始化 LangGraph checkpoint 表和 `chat_sessions` 会话索引表。

## 前端行为

- 页面启动时请求 `GET /api/chat/sessions?limit=50`。
- 如果服务端返回会话摘要，左侧历史列表优先展示服务端数据。
- 点击历史会话时继续通过 `GET /api/chat/session/{session_id}` 加载完整消息历史。
- 如果服务端没有会话列表或请求失败，前端继续使用 `localStorage` 回退。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/chat/sessions?limit=50` | 查询服务端会话摘要列表 |
| `GET` | `/api/chat/session/{session_id}` | 查询指定会话历史 |
| `POST` | `/api/chat/clear` | 清空指定会话 |

## 验证命令

```powershell
$env:DASHSCOPE_API_KEY='test-key'
$env:DASHSCOPE_API_BASE='https://example.com/v1'
$env:DASHSCOPE_MODEL='test-chat'
$env:DASHSCOPE_EMBEDDING_MODEL='test-embedding'
python -m pytest tests/test_session_persistence.py tests/test_chat_sessions_api.py tests/test_rag_session_history.py tests/test_openai_compatible_config.py tests/test_rag_retrieval_service.py -q --no-cov
python -m py_compile app/config.py app/core/session_persistence.py app/main.py app/api/chat.py app/models/response.py app/services/rag_agent_service.py app/services/aiops_service.py
node --check static/app.js
git diff --check
```

## 注意事项

- 当前环境如果没有安装 `uv`，需要后续在具备 `uv` 的环境执行 `uv lock` 或 `uv sync` 同步锁文件和依赖。
- 不要把真实 `POSTGRES_DSN`、API Key 或 `.env` 提交到仓库。
- `SESSION_CHECKPOINT_BACKEND=postgres` 是生产/演示持久化推荐模式；如果 PostgreSQL 不可用，请先改回 `memory` 以恢复本地开发。
