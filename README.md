# 知行智能Agent

> 企业级智能对话和运维助手，支持 RAG 知识库问答和 AIOps 智能诊断

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-latest-orange.svg)](https://www.langchain.com/)

## ✨ 核心特性

- 🤖 **智能对话** - LangChain 多轮对话 + 流式输出，保留最近多轮上下文
- 📚 **RAG 问答** - 调用内网知识库平台接口完成混合检索（向量 + 关键词 + 重排），回答强制标注引用来源，无答案时明确兜底防止幻觉
- 👍 **反馈评价系统** - 每条回答支持点赞/不喜欢，负反馈弹窗支持结构化标签 + 补充描述，反馈数据入库（含关联知识片段 ID）供后续审核与知识修正
- 🔧 **AIOps 诊断** - Plan-Execute-Replan 自动故障诊断和根因分析
- 🌐 **Web 界面** - 现代化 UI（参考 ChatGPT/Claude），引用来源卡片展示、快速/流式对话、多格式文件上传
- 🔌 **MCP 集成** - 日志查询和监控数据工具接入

## 🛠️ 技术栈

- **框架**: FastAPI + LangChain + LangGraph
- **LLM**: OpenAI 兼容接口（可接入 DeepSeek、DashScope、OpenAI 或其他兼容服务）
- **知识库**: 内网知识库平台 API（文档解析/向量化/混合检索/重排均由平台完成）
- **反馈存储**: SQLite（可选同步转发内网反馈接口）
- **工具协议**: MCP (Model Context Protocol)

## 🏗️ 架构说明（知识库接口化改造）

本项目已不再在本地建立知识库（无需 Milvus / Embedding / Rerank 服务），RAG 链路为：

```
用户提问 -> LangGraph Agent -> retrieve_knowledge 工具
          -> 内网知识库平台 /v1/doc/retrieval/（混合检索 + 重排）
          -> 相似度过滤 + 截断最相关 3-5 个片段
          -> LLM 生成带引用编号 [1][2] 的回答（无答案时回复“无法基于当前知识库回答”）
          -> 接口返回 answer + sources（命中的知识片段），前端展示引用来源卡片
```

文件上传同样透传知识库平台的上传接口，支持 PDF/Word/Excel/PPT/图片等多源异构格式。

占位模块（本期不实现，预留扩展点）：

- **知识自进化**：反馈数据已入库（含关联 chunk ID），后续可基于 `GET /api/feedback/list` 接入 LLM 初筛 +
  人工审核 + 知识库回写流程
- **NL2SQL / 函数调用进阶**：Agent 工具链路（`app/tools/`）已支持多工具注册，后续可直接新增对应工具

## 🚀 快速开始

### 环境要求

- Python 3.11、3.12 或 3.13
- Chat 模型服务 API Key（DeepSeek / Qwen / OpenAI 兼容接口）
- 内网知识库平台的 Bearer Token（`KB_API_TOKEN`，形如 kbmp-xxxx）

### 安装和启动

#### Linux/macOS 环境

```bash
# 1. 克隆项目
git clone <repository_url>
cd super_biz_agent_py

# 2. 安装依赖（推荐使用 uv）
# 方式 1: 使用 uv（推荐，更快）
pip install uv
uv venv
source .venv/bin/activate
uv pip install -e .

# 方式 2: 使用 pip
pip install -e .

# 3. 编辑配置文件
# 首次使用需要编辑 .env 文件，填入 Chat API Key 和知识库平台 Token（KB_API_TOKEN）
vim .env  # 或使用其他编辑器

# 4. 启动服务
make start
```

#### Windows 环境（PowerShell/CMD）

如果Windows 不支持 `make` 命令，可以手动执行以下步骤以启动服务：

```powershell
# 1. 克隆项目
git clone <repository_url>
cd super_biz_agent_py

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .

# 可选：使用 uv 同步依赖
python -m pip install uv
python -m uv sync

# 3. 编辑配置文件
# 使用记事本或其他编辑器打开 .env 文件，填入 Chat API Key 和知识库平台 Token（KB_API_TOKEN）
notepad .env

# 4. （可选）启用 PostgreSQL 会话持久化时启动 PostgreSQL
docker run --name agent-postgres -e POSTGRES_USER=superbiz -e POSTGRES_PASSWORD=superbiz_dev -e POSTGRES_DB=super_biz_agent -p 5432:5432 -d postgres:16

# 5. 启动 MCP 服务
# 启动 CLS 日志查询服务（新开一个 PowerShell 窗口）
python mcp_servers/cls_server.py

# 启动 Monitor 监控服务（新开一个 PowerShell 窗口）
python mcp_servers/monitor_server.py

# 6. 启动 FastAPI 主服务（新开一个 PowerShell 窗口）
# 注意：日志会自动输出到 logs\app_YYYY-MM-DD.log
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
```

**Windows 一键启动脚本**（推荐）

使用启动脚本：

```powershell
# 启动所有服务
.\start-windows.bat

# 停止所有服务
.\stop-windows.bat
```

说明：Windows 批处理脚本已使用英文 ASCII 输出，避免 `cmd.exe` 在不同代码页下把中文 UTF-8 内容解析成乱码命令。启动脚本会打开
`SuperBizAgent Logs` 窗口实时跟随 `server.log`，并在启动完成时打印最近的 FastAPI 日志。

如需手动查看实时日志：

```powershell
powershell -NoProfile -Command "Get-Content -Path server.log -Wait -Tail 80 -Encoding UTF8"
```

### 访问服务

- **Web 界面**: http://localhost:9900
- **API 文档**: http://localhost:9900/docs

## 📡 API 接口

### 核心接口

| 功能       | 方法 | 路径                   | 说明                                                 |
| ---------- | ---- | ---------------------- | ---------------------------------------------------- |
| 普通对话   | POST | `/api/chat`            | 一次性返回 answer + sources（引用来源）              |
| 流式对话   | POST | `/api/chat_stream`     | SSE 流式输出，完成前推送 sources 事件                |
| AIOps 诊断 | POST | `/api/aiops`           | 自动故障诊断（流式）                                 |
| 文件上传   | POST | `/api/upload`          | 透传知识库平台上传接口（支持 PDF/Word/Excel/图片等） |
| 知识库列表 | GET  | `/api/kb/list`         | 获取知识库列表                                       |
| 文档列表   | GET  | `/api/kb/{kb_id}/docs` | 获取指定知识库的文档列表                             |
| FAQ 检索   | POST | `/api/kb/faq`          | FAQ 问答库检索                                       |
| 提交反馈   | POST | `/api/feedback`        | 点赞/不喜欢 + 结构化标签 + 补充描述                  |
| 反馈标签   | GET  | `/api/feedback/tags`   | 获取结构化负反馈标签选项                             |
| 反馈列表   | GET  | `/api/feedback/list`   | 查询反馈记录（供审核/知识修正）                      |
| 反馈统计   | GET  | `/api/feedback/stats`  | 点赞/不喜欢数量统计                                  |
| 健康检查   | GET  | `/api/health`          | 服务状态检查                                         |

### 使用示例

```bash
# 普通对话
curl -X POST "http://localhost:9900/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"你好"}'

# 流式对话
curl -X POST "http://localhost:9900/api/chat_stream" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"你好"}' \
  --no-buffer

# AIOps 诊断
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session-123"}' \
  --no-buffer
```

## 📁 项目结构

```
super_biz_agent_py/
├── app/                                    # 应用核心
│   ├── __init__.py                         # 包初始化（自动加载日志配置）
│   ├── main.py                             # FastAPI 应用入口
│   ├── config.py                           # 配置管理（环境变量、MCP 服务器配置）
│   ├── api/                                # API 路由层
│   │   ├── __init__.py
│   │   ├── chat.py                         # 对话接口（RAG 聊天，返回引用来源）
│   │   ├── aiops.py                        # AIOps 接口（故障诊断）
│   │   ├── file.py                         # 文件上传（透传知识库平台）
│   │   ├── kb.py                           # 知识库管理（列表/文档/FAQ 检索）
│   │   ├── feedback.py                     # 反馈评价（点赞/不喜欢/结构化负反馈）
│   │   └── health.py                       # 健康检查（服务状态）
│   ├── services/                           # 业务服务层
│   │   ├── __init__.py
│   │   ├── rag_agent_service.py            # RAG Agent（LangGraph 状态图）
│   │   ├── kb_api_service.py               # 内网知识库平台 API 客户端（检索/上传/列表/FAQ）
│   │   ├── retrieval_context.py            # 检索上下文（记录一次问答命中的知识片段）
│   │   ├── feedback_service.py             # 反馈评价服务（SQLite 存储 + 可选转发）
│   │   └── aiops_service.py                # AIOps 服务（计划-执行-重规划）
│   ├── agent/                              # Agent 模块
│   │   ├── __init__.py
│   │   ├── mcp_client.py                   # MCP 客户端（工具调用）
│   │   └── aiops/                          # AIOps 核心逻辑
│   │       ├── __init__.py
│   │       ├── planner.py                  # 计划制定器
│   │       ├── executor.py                 # 步骤执行器
│   │       ├── replanner.py                # 重规划器
│   │       ├── state.py                    # 状态定义
│   │       └── utils.py                    # 工具函数
│   ├── models/                             # 数据模型层
│   │   ├── __init__.py
│   │   ├── aiops.py                        # AIOps 模型
│   │   ├── document.py                     # 文档模型
│   │   ├── request.py                      # 请求模型
│   │   └── response.py                     # 响应模型
│   ├── tools/                              # Agent 工具集
│   │   ├── __init__.py
│   │   ├── knowledge_tool.py               # 知识库查询工具
│   │   └── time_tool.py                    # 时间工具
│   ├── core/                               # 核心组件
│   │   ├── __init__.py
│   │   ├── llm_factory.py                  # LLM 工厂（模型管理）
│   │   └── session_persistence.py          # 会话 checkpoint 与 PostgreSQL 会话索引
│   └── utils/                              # 工具类
│       ├── __init__.py
│       └── logger.py                       # 日志配置（Loguru）
├── static/                                 # Web 前端（纯静态）
│   ├── index.html                          # 主页面
│   ├── app.js                              # 前端逻辑
│   └── styles.css                          # 样式表
├── mcp_servers/                            # MCP 服务器
│   ├── cls_server.py                       # CLS 日志查询服务
│   ├── monitor_server.py                   # 监控数据服务
│   └── README.md                           # MCP 服务说明
├── aiops-docs/                             # 运维知识库（Markdown 文档）
├── logs/                                   # 日志目录（Loguru 自动创建）
│   └── app_YYYY-MM-DD.log                  # 按天轮转的日志文件
├── data/                                   # 本地数据目录（反馈 SQLite 库等，自动创建）
├── .env                                    # 环境变量配置（需手动创建）
├── Makefile                                # 项目管理命令（Linux/macOS）
├── start-windows.bat                       # Windows 启动脚本
├── stop-windows.bat                        # Windows 停止脚本
├── pyproject.toml                          # 项目配置（依赖、元数据）
├── uv.lock                                 # uv 依赖锁定文件
├── pyrightconfig.json                      # Pyright 类型检查配置
└── README.md                               # 项目说明
```

## ⚙️ 配置说明

通过 `.env` 文件配置：

```bash
# Chat LLM 配置
CHAT_API_KEY=your-chat-api-key
CHAT_BASE_URL=https://your-chat-provider.example.com/v1
CHAT_MODEL=your-chat-model

# 知识库平台 API 配置（内网）
KB_API_TOKEN=kbmp-xxxx
KB_DOC_BASE_URL=http://10.8.192.79:5353
KB_MGMT_BASE_URL=http://10.8.192.79:5354
KB_FAQ_BASE_URL=http://10.8.192.79:6000
KB_BOTCODE=your-botcode
KB_FAQ_CHANNEL=your-channel
KB_UPLOAD_KB_ID=
KB_TIMEOUT_SECONDS=30
KB_MAX_CHUNKS=5
KB_MIN_SIMILARITY=0

# 反馈评价系统配置
FEEDBACK_DB_PATH=data/feedback.db
FEEDBACK_API_URL=

# 会话持久化配置
# memory: 默认进程内 MemorySaver；postgres: PostgreSQL checkpoint，服务重启后保留 Agent 状态
SESSION_CHECKPOINT_BACKEND=memory
POSTGRES_DSN=postgresql://superbiz:superbiz_dev@localhost:5432/super_biz_agent
POSTGRES_CONNECT_TIMEOUT_SECONDS=10
```

Chat 模型配置使用 `CHAT_*`，未配置时会兼容旧的 `DASHSCOPE_*` 变量。知识库相关配置均以 `KB_`
开头：`KB_API_TOKEN` 为知识库平台的 Bearer Token；`KB_MAX_CHUNKS` 控制传给 LLM
的最相关片段数量（3-5）；`KB_MIN_SIMILARITY` 可选地按相似度过滤低质量片段。反馈数据默认存储在本地
SQLite（`FEEDBACK_DB_PATH`），配置 `FEEDBACK_API_URL`
后会异步转发到内网反馈入库接口（转发失败不影响本地入库）。会话持久化由 `SESSION_CHECKPOINT_BACKEND=memory|postgres`
显式控制，默认 `memory` 保持原行为，`postgres` 会强依赖 `POSTGRES_DSN`。

## 💾 PostgreSQL 会话持久化

项目支持通过显式开关选择会话 checkpoint 后端：

| 模式            | 配置                                  | 行为                                                                         |
| --------------- | ------------------------------------- | ---------------------------------------------------------------------------- |
| 内存模式        | `SESSION_CHECKPOINT_BACKEND=memory`   | 默认行为，使用 LangGraph `MemorySaver`，服务重启后会话状态不保留             |
| PostgreSQL 模式 | `SESSION_CHECKPOINT_BACKEND=postgres` | 使用 LangGraph PostgreSQL checkpointer，服务重启后按 `session_id` 恢复上下文 |

启用 PostgreSQL 模式时需要准备：

```bash
SESSION_CHECKPOINT_BACKEND=postgres
POSTGRES_DSN=postgresql://user:password@localhost:5432/super_biz_agent
POSTGRES_CONNECT_TIMEOUT_SECONDS=10
```

说明：

- `POSTGRES_DSN` 指向的数据库需要提前创建。
- 应用启动时会执行 LangGraph checkpoint 初始化，并自动创建轻量会话索引表 `chat_sessions`。
- `chat_sessions` 只保存前端历史列表摘要；完整 Agent 状态以 LangGraph checkpoint 为准。
- 选择 `postgres` 后，如果 PostgreSQL 不可达、DSN 缺失或初始化失败，FastAPI 会启动失败，避免误以为已经持久化。
- 前端启动时会请求 `GET /api/chat/sessions` 加载服务端历史会话；如果服务端没有返回历史，则继续使用本地 `localStorage`
  回退。

新增会话 API：

| 方法   | 路径                             | 说明                                          |
| ------ | -------------------------------- | --------------------------------------------- |
| `GET`  | `/api/chat/sessions?limit=50`    | 查询服务端会话摘要列表，按更新时间倒序返回    |
| `GET`  | `/api/chat/session/{session_id}` | 查询指定会话的历史消息                        |
| `POST` | `/api/chat/clear`                | 清空指定会话的 checkpoint，并删除会话索引摘要 |

依赖说明：

```bash
# 使用 uv 的环境建议同步依赖
uv sync

# 或使用 pip 安装新增依赖
pip install "langgraph-checkpoint-postgres>=2.0.0" "psycopg[binary,pool]>=3.2.0"
```

## 🎯 AIOps 智能运维

基于 **Plan-Execute-Replan** 模式实现自动故障诊断。

### 核心特性

- ✅ 自动制定诊断计划（Planner）
- ✅ 智能工具调用（Executor）
- ✅ 动态调整步骤（Replanner）
- ✅ 流式输出诊断过程
- ✅ 生成结构化报告

### 快速测试

```bash
# 服务已通过 make init 自动启动
# 如需重启服务：make restart

# 访问 Web 界面，点击"智能运维与诊断工具"
# 或使用 API
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test"}' \
  --no-buffer
```

### 诊断流程

```
1. Planner 制定计划 → 生成 4-6 个诊断步骤
2. Executor 执行步骤 → 调用 MCP 工具（日志查询、监控数据）
3. Replanner 评估结果 → 决定继续/调整/生成报告
4. 输出诊断报告 → 根因分析 + 运维建议
```

## 📝 开发指南

### 常用命令

```bash
# 项目管理
make init              # 一键初始化（Docker + 服务 + 文档）
make start             # 启动所有服务
make stop              # 停止所有服务
make restart           # 重启所有服务

# 依赖管理
make install-dev       # 安装开发依赖
make sync              # 同步依赖

# Docker 管理
make up                # 启动 Docker 容器
make down              # 停止 Docker 容器

# 代码质量
make format            # 格式化代码
make lint              # 代码检查
```

## 🐛 常见问题

### Windows 环境问题

#### 1. `make` 命令不可用

Windows 不支持 `make` 命令，请使用提供的批处理脚本：

```powershell
# 启动服务
.\start-windows.bat

# 停止服务
.\stop-windows.bat
```

#### 2. PowerShell 执行策略限制

如果遇到 "无法加载文件，因为在此系统上禁止运行脚本" 错误：

```powershell
# 临时允许脚本执行（管理员权限）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 或者使用 CMD 而不是 PowerShell
cmd
.\start-windows.bat
```

#### 3. 批处理脚本出现 `鍔?...` 乱码命令

请更新到当前版本的 `start-windows.bat` / `stop-windows.bat`。脚本内容应为英文 ASCII，并使用 Windows
CRLF 换行，避免 `cmd.exe` 代码页解析失败。

#### 4. 端口被占用（Windows）

```powershell
# 查看占用端口的进程
netstat -ano | findstr :9900

# 结束进程（替换 PID 为实际进程 ID）
taskkill /F /PID <PID>
```

### 通用问题

### API Key 错误

```bash
# 检查环境变量
cat .env | grep API_KEY        # Linux/macOS
type .env | findstr API_KEY    # Windows
```

### 知识库平台接口调用失败

```bash
# 1. 确认当前网络可以访问内网知识库平台（10.8.192.79）
# 2. 确认 KB_API_TOKEN 已配置且未过期（形如 kbmp-xxxx）
# 3. 查看服务日志中的具体错误（logs/app_YYYY-MM-DD.log）
# 检索失败时回答会降级为“无法基于当前知识库回答”，不会中断对话
```

### PostgreSQL 会话持久化启动失败

如果设置了 `SESSION_CHECKPOINT_BACKEND=postgres` 后服务启动失败，请检查：

```bash
# 1. 是否安装新增依赖
pip show langgraph-checkpoint-postgres psycopg

# 2. 是否配置 PostgreSQL DSN
# Windows
type .env | findstr POSTGRES

# Linux/macOS
cat .env | grep POSTGRES

# 3. PostgreSQL 是否可连接，且目标数据库已创建
```

如果只是本地开发且不需要重启保留会话，可以临时改回：

```bash
SESSION_CHECKPOINT_BACKEND=memory
```

### 服务无法启动

**Linux/macOS:**

```bash
# 查看服务日志
tail -f logs/app_$(date +%Y-%m-%d).log  # FastAPI 主服务（Loguru 日志）
tail -f mcp_cls.log                      # CLS MCP 服务
tail -f mcp_monitor.log                  # Monitor MCP 服务

# 检查端口占用
lsof -i :9900  # FastAPI
lsof -i :8003  # CLS MCP
lsof -i :8004  # Monitor MCP
```

**Windows:**

```powershell
# 查看服务日志（获取今天的日期）
$today = Get-Date -Format "yyyy-MM-dd"
type logs\app_$today.log  # FastAPI 主服务（Loguru 日志）
type mcp_cls.log          # CLS MCP 服务
type mcp_monitor.log      # Monitor MCP 服务

# 或者查看最新的日志文件
Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 50

# 检查端口占用
netstat -ano | findstr :9900  # FastAPI
netstat -ano | findstr :8003  # CLS MCP
netstat -ano | findstr :8004  # Monitor MCP
```

## 📚 参考资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [LangChain 文档](https://python.langchain.com/)
- [LangGraph Plan-Execute](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/)
- [OpenAI API](https://platform.openai.com/docs/api-reference)
- [阿里云 DashScope](https://dashscope.aliyun.com/)
- [MCP 协议](https://modelcontextprotocol.io/)

## 📄 许可证

author： chief

MIT License
