# 仓库架构分析（Framework Analysis）

> **文档定位**：当前仓库的完整架构与模块分析，回答"这个项目是怎么构建的"。
> 配套文档：[README.md](./README.md)（怎么用）· [CHANGELOG.md](./CHANGELOG.md)（改了什么）· [项目规划.md](./项目规划.md)（往哪走）
>
> 最后更新：2026-07-16（合并同事代码后全量重写）

---

## 一、项目概览

| 项 | 值 |
|----|-----|
| 项目名 | super-biz-agent-py（品牌"知行助手"） |
| 版本 | 1.2.1 |
| 定位 | 基于知识库 API 的知识中台提效助手，支持 RAG 检索、引用标注、反馈评价、Bug 上报 |
| 技术栈 | FastAPI + LangChain/LangGraph + vanilla JS |
| 端口 | 9983 |
| Python | ≥3.11, <3.14 |

**核心架构变迁**：原本地 Milvus 向量库 + Embedding + Rerank 的 RAG 链路已迁移为直接调用**内网知识库 API**（检索 + 重排由 KB 平台完成）。旧向量库代码保留但标记为废弃。

---

## 二、目录结构

```
helper/
├── app/                          # 后端核心（FastAPI）
│   ├── main.py                   # 应用入口，路由注册，lifes 管理
│   ├── run_server.py             # 服务启动
│   ├── config.py                 # Pydantic Settings 配置
│   ├── api/                      # API 路由层（7 个模块）
│   │   ├── chat.py               # RAG 问答 + 会话历史
│   │   ├── file.py               # 文档上传 + 知识库管理
│   │   ├── feedback.py           # 反馈评价
│   │   ├── bug.py                # Bug 上报
│   │   ├── admin.py              # 管理后台聚合（时间线）
│   │   ├── health.py             # 健康检查
│   │   └── aiops.py              # AIOps 智能运维（预留）
│   ├── services/                 # 业务服务层（14 个模块）
│   │   ├── kb_api_client.py      # ✅ 内网知识库 API 客户端
│   │   ├── rag_agent_service.py  # ✅ RAG 问答服务
│   │   ├── rag_retrieval_service.py  # ✅ 检索编排
│   │   ├── feedback_service.py   # ✅ 反馈存储（SQLite）
│   │   ├── bug_service.py        # ✅ Bug 存储（SQLite + 附件）
│   │   ├── aiops_service.py      # ✅ Plan-Execute-Replan
│   │   ├── vector_*.py           # 🗑️ 废弃（本地向量库链路）
│   │   ├── rerank_service.py     # 🗑️ 废弃
│   │   ├── document_splitter_service.py  # 🗑️ 废弃
│   │   └── embedding_input_guard.py     # 🗑️ 废弃
│   ├── agent/aiops/              # AIOps LangGraph Agent
│   │   ├── planner.py            # 制定诊断计划
│   │   ├── executor.py           # 执行 MCP 工具
│   │   ├── replanner.py          # 评估结果，决定下一步
│   │   ├── state.py / utils.py   # 状态与工具
│   ├── agent/mcp_client.py       # MCP 客户端单例
│   ├── core/
│   │   ├── llm_factory.py        # LLM 提供商路由
│   │   ├── session_persistence.py # 会话持久化（SQLite + Checkpointer）
│   │   ├── milvus_client.py      # 🗑️ 废弃
│   │   └── windows_event_loop.py # Windows asyncio 兼容
│   ├── models/                   # Pydantic 数据模型
│   ├── tools/                    # Agent 工具（knowledge_tool, time_tool）
│   └── utils/logger.py           # Loguru 日志配置
├── mcp_servers/                  # MCP 工具服务
│   ├── cls_server.py             # 腾讯 CLS 日志查询（端口 8003，Mock 数据）
│   └── monitor_server.py         # 监控指标查询（端口 8004，Mock 数据）
├── static/                       # 前端（纯 vanilla JS）
│   ├── index.html                # 主对话界面
│   ├── admin.html                # 管理后台
│   ├── app.js                    # 前端逻辑（~1780 行）
│   └── styles.css                # 样式（~1670 行）
├── tests/                        # 测试（11 个文件）
├── data/                         # 运行时数据
│   ├── chat_sessions.db          # 会话历史（SQLite）
│   ├── feedback.db               # 反馈数据（SQLite）
│   ├── bug.db                    # Bug 数据（SQLite）
│   └── uploads/                  # Bug 附件存储
├── aiops-docs/                   # AIOps 诊断剧本（5 个场景，入库文档）
├── docs/superpowers/             # 设计文档（PostgreSQL 会话持久化 plan + spec）
├── project-docs/                 # 项目跟踪文档（6 个，部分已过时）
├── job_hunter/                   # ⚠ 个人求职材料（非项目代码）
├── logs/                         # 运行时日志
└── 配置文件
    ├── pyproject.toml            # 依赖与工具配置
    ├── .env.example              # 环境变量模板
    ├── vector-database.yml       # 🗑️ Milvus docker-compose（不再需要）
    ├── Makefile                  # 自动化命令
    ├── pyrightconfig.json        # 类型检查配置（过时：Python 3.10/macOS）
    ├── .pre-commit-config.yaml   # Git hooks
    ├── start-windows.bat         # Windows 启动脚本
    └── stop-windows.bat          # Windows 停止脚本
```

---

## 三、后端架构

### 3.1 应用入口（`app/main.py`）

FastAPI 应用，`lifespan` 上下文管理器依次初始化：
1. `session_persistence_manager.initialize_async()` — 会话持久化
2. `rag_agent_service.configure_checkpointer(...)` — 注入 checkpointer
3. `feedback_service.initialize()` — 反馈数据库
4. `bug_service.initialize()` — Bug 数据库

路由注册顺序：health → chat → file → feedback → bug → admin → aiops，全部挂载在 `/api` 前缀下。静态文件挂载 `/static` 和 `/uploads`，根路径 `/` 返回 `index.html`，`/admin` 返回 `admin.html`。

### 3.2 API 路由层（`app/api/`）

| 模块 | 端点 | 职责 |
|------|------|------|
| `chat.py` | `POST /chat`、`POST /chat_stream`、`POST /chat/clear`、`GET /chat/sessions`、`GET /chat/session/{id}`、`PUT /chat/session/{id}/rename`、`GET /chat/suggestions` | RAG 问答 + 会话历史管理 |
| `file.py` | `POST /upload`、`GET /knowledge-bases`、`GET /knowledge-bases/{kb_id}/docs`、`POST /kb/retrieve` | 文档上传 + 知识库管理 |
| `feedback.py` | `POST /feedback`、`GET /feedback`、`GET /feedback/stats`、`GET /feedback/tags`、`GET /feedback/timeline`、`GET /feedback/message/{id}`、`GET /feedback/{id}`、`DELETE /feedback/{id}` | 反馈评价全生命周期 |
| `bug.py` | `GET /bug/categories`、`POST /bug/report`、`GET /bug/list`、`GET /bug/stats`、`GET /bug/timeline`、`GET /bug/{id}`、`PUT /bug/{id}/status` | Bug 上报与管理 |
| `admin.py` | `GET /admin/timeline` | Bug + 反馈合并时间线 |
| `health.py` | `GET /health` | 服务状态 + KB API 连通性 |
| `aiops.py` | `POST /aiops` | AIOps 智能运维（预留） |

### 3.3 业务服务层（`app/services/`）

**当前使用的核心服务：**

| 服务 | 职责 |
|------|------|
| `kb_api_client.py` | 封装内网知识库平台所有 API（检索/上传/知识库管理/FAQ），统一鉴权头 |
| `rag_agent_service.py` | RAG 问答核心：LangGraph Agent 检索 → LLM 生成 → 引用标注；含会话历史读写 |
| `rag_retrieval_service.py` | 检索编排（调用 KB API 完成混合检索 + 重排） |
| `feedback_service.py` | 反馈存储（SQLite），支持外部 API 推送 |
| `bug_service.py` | Bug 存储（SQLite + 附件目录） |
| `aiops_service.py` | Plan-Execute-Replan 服务（LangGraph） |

**废弃服务（保留代码，不再使用）：**

`vector_embedding_service.py`、`vector_index_service.py`、`vector_search_service.py`、`vector_store_manager.py`、`rerank_service.py`、`document_splitter_service.py`、`embedding_input_guard.py` — 原本地向量库 RAG 链路，已被 KB API 替代。

### 3.4 核心组件（`app/core/`）

**`llm_factory.py` — LLM 提供商路由**

按 `CHAT_PROVIDER` 配置自动路由到原生 LangChain 接口：
- `deepseek` → `ChatDeepSeek`（原生接口，非 OpenAI 兼容模式）
- `qwen` → `ChatQwen`（DashScope）
- `openai` → `ChatOpenAI`（OpenAI 兼容兜底）
- 未显式配置时根据 `base_url`/`model` 自动推断，无法识别时回退 openai 兼容

**`session_persistence.py` — 会话持久化（详见第五节）**

三种可切换后端，由 `SESSION_CHECKPOINT_BACKEND` 配置决定：
- `memory`（默认）— SQLite 存元数据+消息 + `MemorySaver` 存 Agent 运行时状态
- `postgres` — PostgreSQL checkpoint（生产环境）
- `InMemorySessionStore` — 纯内存，重启丢失（仅开发用）

### 3.5 AIOps Agent（`app/agent/aiops/`）

基于 LangGraph 官方教程实现的 Plan-Execute-Replan 架构：
- `planner.py` — 分析问题，制定 4-6 步诊断计划
- `executor.py` — 根据计划调用 MCP 工具（查日志、查监控指标）
- `replanner.py` — 评估工具返回结果，决定继续/调整/输出最终报告
- `state.py` — 状态定义
- `utils.py` — 工具函数

通过 `mcp_client.py` 单例连接 MCP 服务（CLS 日志 + Monitor 监控）。

---

## 四、前端架构（`static/`）

纯 vanilla JS，无构建工具，无框架依赖。

| 文件 | 职责 |
|------|------|
| `index.html` | 主对话界面（ChatGPT 风格），含侧边栏"近期对话"、引用来源侧边栏、反馈弹窗、Bug 上报弹窗 |
| `admin.html` | 管理后台，标签页：Bug 列表、反馈记录、会话列表、统计仪表盘 |
| `app.js` | `SmartQAApp` 类，全部前端逻辑：流式对话、文件上传、引用展示、会话管理、反馈、Bug 上报、复制 |
| `styles.css` | 全部样式，CSS 变量主题 |

**前端核心机制：**
- **会话 ID**：每个浏览器窗口客户端生成，作为 `Id` 传入每次 `/chat_stream`
- **双存储**：`localStorage`（最多 50 条，保留 citations/messageId）+ 服务端 SQLite（持久化）
- **流式渲染**：SSE 事件 `retrieving`/`search_results`/`content`/`done`/`error`
- **引用侧边栏**：点击引用卡片 → 右侧边栏展示该文档片段完整内容

---

## 五、会话持久化深度分析

> 这是合并带来的核心子系统，也是 `framework_analysis.md` 原版的重点内容。

### 5.1 数据模型（`app/core/session_persistence.py`）

`SessionPersistenceManager` 门面模式，后端三选一：

**`SqliteSessionStore`（默认，DB: `data/chat_sessions.db`）**：

```sql
CREATE TABLE chat_sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT DEFAULT '新对话',
    created_at TEXT, updated_at TEXT,
    last_message_preview TEXT DEFAULT '',
    message_count INTEGER DEFAULT 0,
    user_id TEXT DEFAULT ''
)
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT, role TEXT,
    content TEXT, created_at TEXT
)
-- 索引：idx_chat_messages_session, idx_chat_sessions_updated_at(DESC), idx_chat_sessions_user_id
```

**核心操作：**
- `upsert_session(metadata)` — upsert `chat_sessions`（保留首轮标题，仅空/"新对话"时覆盖；递增 `message_count`），然后追加两行到 `chat_messages`（user + assistant）
- `get_messages(session_id)` — `SELECT role, content, created_at ORDER BY id ASC`
- `list_sessions` — `ORDER BY updated_at DESC LIMIT ? OFFSET ?`，可选 `user_id` 过滤
- `rename_session` / `delete_session`（两表同时操作）

**`PostgresSessionStore`** — 生产环境，注意：**只持久化 session 元数据，不存 per-message 行**（消息来自 checkpointer）

**`InMemorySessionStore`** — 纯 dict，重启丢失

### 5.2 会话写入流程

1. 客户端生成 `sessionId`，每次 `/chat_stream` 传入
2. `rag_agent_service.query_stream()` 运行 LangGraph RAG Agent（checkpointer 以 `thread_id=session_id` 为 key，提供多轮记忆）
3. 答案完成后调用：
   ```python
   session_persistence_manager.upsert_chat_session(
       session_id=session_id, question=question, answer=full_response
   )
   ```
4. 返回 `message_id = f"msg_{session_id}_{timestamp_ms}"` 给前端，用于反馈关联

### 5.3 会话读取流程

`rag_agent_service.get_session_history_async(session_id)`：

1. **优先查 SQLite**（`get_session_messages`）— 重启后仍可恢复
2. **降级到 LangGraph checkpointer**（postgres 后端 / 内存运行时会话）— 通过 `_checkpoint_to_history()` 转换，跳过 `SystemMessage`/`ToolMessage` 和含 tool_calls 的 AIMessage，从 prompt 模板提取真实用户问题

### 5.4 管理后台展示

`/admin` 页面复用同一套 `/api/chat/sessions` 和 `/api/chat/session/{id}` 端点：
- **会话列表 tab** — 分页表格，"查看历史"按钮弹窗展示完整对话
- **反馈上下文查看器** — 根据反馈的 `question` 匹配定位对话轮次，展示从第 1 轮到匹配轮次的完整上下文
- **全部时间线** — `GET /api/admin/timeline` 合并 Bug + 反馈，按 `created_at` 倒序，反馈项携带 `session_id`/`message_id` 可跳转关联对话

---

## 六、MCP 工具服务（`mcp_servers/`）

| 服务 | 端口 | 工具 | 数据状态 |
|------|------|------|----------|
| `cls_server.py` | 8003 | `get_current_timestamp`、`get_topic_info_by_name`、`search_log`、`search_service_logs`、`analyze_log_pattern` 等 | Mock 数据 |
| `monitor_server.py` | 8004 | `query_cpu_metrics`、`query_memory_metrics`、`query_process_list`、`search_historical_tickets` 等 | Mock 数据 |

设计为可对接真实腾讯 CLS / Prometheus API，当前返回 Mock 数据用于开发调试。

---

## 七、数据流

### 7.1 RAG 问答流

```
用户提问
  ↓
[chat.py] POST /chat_stream {Id, Question}
  ↓
[rag_agent_service] LangGraph Agent
  ├── 检索：kb_api_client → 内网 KB API（混合检索 + 重排）
  ├── 上下文构建：格式化为带编号的参考资料
  └── 生成：LLM 基于上下文生成带 [1][2] 引用的答案
  ↓
SSE 流式返回：retrieving → search_results → content → done
  ↓
[session_persistence] upsert_chat_session（SQLite 存元数据 + 消息）
  ↓
前端渲染答案 + 引用来源 + 反馈按钮
```

### 7.2 反馈闭环流

```
用户点击 赞/踩
  ↓
[feedback.py] POST /feedback {sessionId, messageId, rating, tags, desc, chunkIds}
  ↓
[feedback_service] SQLite 存储 + 可选外部 API 推送
  ↓
管理后台 GET /feedback 查看分析
```

### 7.3 Bug 上报流

```
用户点击 ⋯ → 上报 Bug
  ↓
[bug.py] POST /bug/report (multipart: 分类+标题+描述+附件+session_id)
  ↓
[bug_service] SQLite 存储 + 附件保存到 data/uploads/
  ↓
管理后台 GET /bug/list 查看，PUT /bug/{id}/status 更新状态
```

---

## 八、测试覆盖（`tests/`）

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_admin_timeline.py` | 管理后台 Bug+反馈时间线聚合 |
| `test_chat_sessions_api.py` | 会话列表/历史 API（SQLite） |
| `test_session_persistence.py` | Checkpoint 后端（memory/postgres）行为 |
| `test_rag_session_history.py` | RAG 多轮历史过滤 |
| `test_rag_retrieval_service.py` | 检索服务 |
| `test_openai_compatible_config.py` | LLM 提供商路由 / effective config |
| `test_document_splitter_service.py` | 文档分块（废弃功能） |
| `test_embedding_input_guard.py` | Token 预算保护（废弃功能） |
| `test_rerank_service.py` | Rerank 服务（废弃功能） |
| `test_logger_config.py` | 日志配置 |
| `test_windows_event_loop.py` | Windows asyncio 策略 |

---

## 九、配置体系

### 9.1 环境变量（`.env.example`）

**核心配置：**
- `CHAT_PROVIDER` / `CHAT_API_KEY` / `CHAT_BASE_URL` / `CHAT_MODEL` — LLM 配置
- `KB_RETRIEVAL_BASE_URL` / `KB_MANAGEMENT_BASE_URL` / `KB_FAQ_BASE_URL` / `KB_API_TOKEN` / `KB_BOTCODE` — 知识库 API
- `KB_TOP_K` / `KB_SIMILARITY_THRESHOLD` / `KB_TIMEOUT_SECONDS` — 检索参数
- `FEEDBACK_DB_PATH` / `BUG_DB_PATH` / `BUG_UPLOAD_DIR` — 数据存储路径
- `SESSION_CHECKPOINT_BACKEND` / `SESSION_DB_PATH` / `POSTGRES_DSN` — 会话持久化
- `MCP_CLS_URL` / `MCP_MONITOR_URL` — MCP 服务地址

**废弃配置块（底部标记）：**
`MILVUS_*`、`EMBEDDING_*`、`RERANK_*`、`CHUNK_*` — 旧本地向量库配置，不再使用

### 9.2 工具配置（`pyproject.toml`）

- ruff / black / isort — 代码格式化（line-length=100）
- pytest + pytest-asyncio + pytest-cov — 测试（asyncio_mode=auto, `--cov=app`）
- mypy — 类型检查
- bandit — 安全检查
- pre-commit — Git hooks

### 9.3 已知配置漂移

| 问题 | 说明 |
|------|------|
| `pyrightconfig.json` 过时 | 写的 Python 3.10 / macOS，与 pyproject 的 3.11+ 不一致 |
| `Makefile` 注释乱码 | GBK 编码环境生成，非 UTF-8 |
| `.env.example` 废弃块 | 底部旧向量库配置不再生效但保留 |
| `project-docs/project_overview.md` 过时 | 仍描述废弃的 Milvus 架构 |

---

## 十、已知问题与待清理项

| 项 | 建议 |
|----|------|
| `job_hunter/` | 个人求职材料（简历 + 面试笔记），非项目代码，建议加入 `.gitignore` |
| `project-docs/project_overview.md` | 内容过时（引用废弃 Milvus 链路），建议更新或删除 |
| `pyrightconfig.json` | Python 版本/平台不一致，建议修正 |
| `vector-database.yml` | Milvus docker-compose，不再需要，可考虑移除 |
| 废弃的 `vector_*` 服务 | 代码保留但不再使用，确认无引用后可清理 |

---

## 附录：文档体系

| 文档 | 关注点 | 时间维度 |
|------|--------|----------|
| `README.md` | 怎么用 | 当前 |
| `CHANGELOG.md` | 改了什么 | 历史 → 现在 → 未来 |
| `framework_analysis.md`（本文档） | 怎么构建的 | 当前深析 |
| `项目规划.md` | 往哪走 | 未来 |
| `CLAUDE.md` | 编码准则 | 当前 |
| `内网步骤.md` | 部署步骤 | 当前 |
| `MinerU_LangChain_集成方案报告.md` | 多模态方案 | 前瞻方案 |
