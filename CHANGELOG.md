# 变更日志（CHANGELOG）

> 本文件记录项目的所有重大变更，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式。
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
>
> **变更类型：** ✨ Added 新增 · 🔄 Changed 变更 · 🗑️ Deprecated 废弃 · ❌ Removed 移除 · 🐛 Fixed 修复 · 🔒 Security 安全

---

## [Unreleased]

_待发布变更记录于此。_

---

## [1.2.1] - 2026-07-16

### ✨ Added

- **用户消息复制按钮** — 对话界面中用户提问的消息悬停时显示复制按钮，点击可复制问题原文（`static/app.js`）
- **用户头像（预留）** — 为用户消息预留头像代码，暂通过 `display:none` 隐藏，后续可启用（`static/app.js`、`static/styles.css`）
- **项目规划文档** — 新增 `项目规划.md`，包含命名建议（"知行助手"）与 5 阶段演进路线图（知识问答 → 工具调用 → AIOps → 工作助手 → Agent 平台）

### 🐛 Fixed

- **app.js 多余空行** — 清理 `static/app.js` 中 435 行编辑残留的连续空行（2196 → 1761 行）

### 🔄 Changed

- **代码格式化** — 全项目 Python 文件通过 `ruff format` + `ruff check --fix` 统一格式（line-length=100，py311），36 个文件重新格式化，自动修复 234 个 lint 问题（主要是 isort 导入排序）
- **开发指南更新** — `README.md` 开发指南从 `black && isort` 改为 `ruff format` + `ruff check`
- **文档校正** — `README.md` 补充缺失 API 端点（`/admin/timeline`、`/bug/timeline`、`/feedback/timeline`）、项目结构（`admin.py`、`session_persistence.py`）、配置项（`SESSION_DB_PATH`、`POSTGRES_CONNECT_TIMEOUT_SECONDS`）；`内网步骤.md` 修正 LLM 配置示例（siliconflow → deepseek），补充会话管理端点

---

## [1.2.0] - 2026-07-15

### ✨ Added

- **引用来源侧边栏** — 点击对话中的引用来源卡片，右侧边栏展示该文档片段的完整内容（类似 Qwen/GPT 风格），后端 `Citation` 模型新增 `content` 字段传递完整片段内容
- **动态常见问题** — 推荐问题从 SQLite 反馈数据库动态拉取最受点赞的问题，替代静态预设
- **会话重命名** — 侧边栏会话列表支持内联重命名（铅笔图标），调用 `PUT /api/chat/session/{id}/rename`
- **管理后台会话列表** — `/admin` 页面新增"会话列表"标签页，基于 SQLite 分页展示所有对话会话，可查看完整对话历史

### 🔄 Changed

- **会话持久化升级** — 会话元数据与消息记录持久化到 SQLite（`data/chat_sessions.db`），重启后保留；`SessionPersistenceManager` 支持 `memory`（默认 SQLite + MemorySaver）和 `postgres` 两种后端

---

## [1.1.0] - 2026-07-13

### ✨ Added

- **Bug 上报与管理后台系统** — 新增完整 Bug 管理闭环：
  - 后端：`app/api/bug.py`（上报/列表/详情/状态更新/统计/分类）、`app/api/admin.py`（Bug+反馈合并时间线）、`app/services/bug_service.py`（SQLite + 附件存储）
  - 前端：`static/admin.html` 管理后台页面，支持 Bug 列表筛选、状态流转、详情查看、反馈记录、会话历史、统计仪表盘
  - 对话界面：输入框左侧「⋯」菜单新增 Bug 上报入口，支持附件上传（截图/日志，最大 20MB）
- **Windows 启动/停止脚本** — `start-windows.bat` / `stop-windows.bat` 重构，支持 uv/pip 双路径、依赖增量检测（`.deps_stamp`）、健康检查轮询、隐藏后台启动、精准 PID 停止
- **部署文档** — 新增 `内网步骤.md`（内网部署步骤）、`CLAUDE.md`（编码准则与 uv 已知问题）

### 🔄 Changed

- **默认端口** — 从 9900 改为 9983

### 🐛 Fixed

- **RAG 流式异常处理** — RAG 流式查询异常不再向上抛出，避免中断 SSE 连接

---

## [1.0.0] - 2026-07-09

### 🔄 Changed

- **架构迁移：切换到知识库 API** — 最大的架构变更，原本地 Milvus 向量库 + Embedding + Rerank 完整 RAG 链路替换为直接调用内网知识库 API（混合语义检索 + 重排由 KB 平台完成）：
  - 新增 `app/services/kb_api_client.py` 封装内网 KB 平台所有 API（检索/上传/知识库管理/FAQ）
  - `app/services/rag_agent_service.py` 重写为基于 KB API 的检索增强问答
  - 保留旧向量库代码（`vector_*` 服务、`milvus_client.py`）标记为废弃，向后兼容
  - 配置新增 `KB_*` 系列（检索/管理/FAQ 地址、Token、Botcode、TopK、阈值）

### ✨ Added

- **引用来源标注** — 每条 AI 回答附带引用来源（文档名、片段 ID、相似度、内容预览），可溯源核实
- **反馈评价系统** — 点赞/不喜欢按钮 + 结构化负反馈收集（回答不准确、文档已过时等），反馈数据存入 SQLite
- **LLM 提供商路由** — `app/core/llm_factory.py` 支持按配置自动路由到原生 LangChain 接口：
  - `deepseek` → `ChatDeepSeek`（原生，非 OpenAI 兼容模式）
  - `qwen` → `ChatQwen`（DashScope）
  - `openai` → `ChatOpenAI`（OpenAI 兼容兜底）
  - 未显式配置时根据 `base_url`/`model` 自动推断，无法识别时回退 openai 兼容
- **PostgreSQL 会话持久化** — LangGraph Checkpoint 支持 PostgreSQL 后端，实现会话中断恢复（`app/core/session_persistence.py`）
- **多模态文档支持** — 知识库平台支持 PDF/Word/Excel/图片等多格式上传解析

### 🗑️ Deprecated

- **本地向量库链路** — 以下模块标记为废弃（代码保留，实际检索改用 KB API）：
  - `app/services/vector_embedding_service.py`
  - `app/services/vector_index_service.py`
  - `app/services/vector_search_service.py`
  - `app/services/vector_store_manager.py`
  - `app/services/rerank_service.py`
  - `app/services/document_splitter_service.py`
  - `app/services/embedding_input_guard.py`
  - `app/core/milvus_client.py`
  - `vector-database.yml`（Milvus docker-compose，不再需要）

---

## [0.9.0] - 2026-05-09 ~ 2026-05-11

> 项目初始阶段，基于本地 Milvus 向量库的 RAG 问答系统。

### ✨ Added

- **FastAPI 应用骨架** — 路由、中间件、静态文件、SSE 流式响应
- **RAG 问答核心** — LangChain Agent + LangGraph 状态机，支持多轮对话
- **本地向量库** — Milvus 向量存储 + Embedding 服务 + BAAI bge-reranker 重排序
- **AIOps 智能运维** — Plan-Execute-Replan 架构（`app/agent/aiops/`），LangGraph 官方教程实现
- **MCP 工具服务** — `mcp_servers/cls_server.py`（CLS 日志查询，端口 8003）、`mcp_servers/monitor_server.py`（监控指标查询，端口 8004），当前返回 Mock 数据
- **文档分块** — `MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter` 两阶段切分，小片段合并 + Token 预算控制
- **Embedding 输入保护** — Token 预算控制防溢出截断
- **Rerank 重排序** — NVIDIA NeMo Retriever Reranking NIM 集成，支持本地关键词降级
- **Windows 事件循环修复** — `app/core/windows_event_loop.py` 解决 Windows asyncio 兼容性

---

## 维护指南

### 如何更新本文件

每次提交重大变更时，在 `[Unreleased]` 下新增条目，按类型分组：

```markdown
### ✨ Added
- 新功能描述（涉及文件）

### 🐛 Fixed
- 修复的问题（涉及文件）

### 🔄 Changed
- 变更的内容
```

发布版本时，将 `[Unreleased]` 改为版本号 + 日期，并在顶部新建空的 `[Unreleased]`。

### 版本号规则

- **MAJOR**（x.0.0）：不兼容的架构变更（如 1.0.0 的 KB API 迁移）
- **MINOR**（1.x.0）：向后兼容的新功能（如 1.1.0 的 Bug 系统）
- **PATCH**（1.0.x）：向后兼容的修复/优化（如 1.2.1 的格式化）

### 变更类型说明

| 图标 | 类型 | 含义 |
|------|------|------|
| ✨ | Added | 新增功能 |
| 🔄 | Changed | 变更已有功能 |
| 🗑️ | Deprecated | 标记废弃（代码保留但不再推荐） |
| ❌ | Removed | 移除功能 |
| 🐛 | Fixed | 修复 Bug |
| 🔒 | Security | 安全修复 |
