# 知行智能Agent

> 企业级智能对话和运维助手，支持 RAG 知识库问答和 AIOps 智能诊断

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-latest-orange.svg)](https://www.langchain.com/)

## ✨ 核心特性

- 🤖 **智能对话** - LangChain 多轮对话 + 流式输出
- 📚 **RAG 问答** - 向量检索增强，支持文档上传、自动建立向量索引、OpenAI 兼容 / NVIDIA Rerank 重排序
- 🔧 **AIOps 诊断** - Plan-Execute-Replan 自动故障诊断和根因分析
- 🌐 **Web 界面** - 现代化 UI，支持多种对话模式：快速问答/流式对话
- 🔌 **MCP 集成** - 日志查询和监控数据工具接入

## 🛠️ 技术栈

- **框架**: FastAPI + LangChain + LangGraph
- **LLM**: OpenAI 兼容接口（可接入 DashScope、OpenAI 或其他兼容服务）
- **向量库**: Milvus
- **工具协议**: MCP (Model Context Protocol)

## 🚀 快速开始

### 环境要求
- Python 3.11、3.12 或 3.13
- Chat、Embedding、Rerank 所需的模型服务 API Key（可使用 OpenAI 兼容接口）

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
# 首次使用需要编辑 .env 文件，填入 Chat、Embedding、Rerank 对应的 API Key 和 Base URL
vim .env  # 或使用其他编辑器

# 4. 一键初始化（启动 Docker + 服务 + 上传文档）
make init

# 5. 一键启动
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
# 使用记事本或其他编辑器打开 .env 文件，填入 Chat、Embedding、Rerank 对应的 API Key 和 Base URL
notepad .env

# 4. 启动 Docker Desktop
# 确保 Docker Desktop 已安装并正在运行

# 5. 启动 Milvus 向量数据库（Docker Compose）
docker compose -f vector-database.yml up -d
docker run --name agent-postgres -e POSTGRES_USER=superbiz -e POSTGRES_PASSWORD=superbiz_dev -e POSTGRES_DB=super_biz_agent -p 5432:5432 -d postgres:16
# 6. 等待 Milvus 启动完成（约 5-10 秒）
timeout /t 10

# 7. 启动 MCP 服务
# 启动 CLS 日志查询服务（新开一个 PowerShell 窗口）
python mcp_servers/cls_server.py

# 启动 Monitor 监控服务（新开一个 PowerShell 窗口）
python mcp_servers/monitor_server.py

# 8. 启动 FastAPI 主服务（新开一个 PowerShell 窗口）
# 注意：日志会自动输出到 logs\app_YYYY-MM-DD.log
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900

# 9. 上传文档到向量库（新开一个 PowerShell 窗口）
# 等待服务启动完成后执行
timeout /t 5
python -c "import requests, os, time; [requests.post('http://localhost:9900/api/upload', files={'file': open(f'aiops-docs/{f}', 'rb')}) or time.sleep(1) for f in os.listdir('aiops-docs') if f.endswith('.md')]"
```

**Windows 一键启动脚本**（推荐）

使用启动脚本：

```powershell
# 启动所有服务
.\start-windows.bat

# 停止所有服务
.\stop-windows.bat
```

说明：Windows 批处理脚本已使用英文 ASCII 输出，避免 `cmd.exe` 在不同代码页下把中文 UTF-8 内容解析成乱码命令。启动脚本会打开 `SuperBizAgent Logs` 窗口实时跟随 `server.log`，并在启动完成时打印最近的 FastAPI 日志。

如需手动查看实时日志：

```powershell
powershell -NoProfile -Command "Get-Content -Path server.log -Wait -Tail 80 -Encoding UTF8"
```

### 访问服务
- **Web 界面**: http://localhost:9900
- **API 文档**: http://localhost:9900/docs

## 📡 API 接口

### 核心接口

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 普通对话 | POST | `/api/chat` | 一次性返回 |
| 流式对话 | POST | `/api/chat_stream` | SSE 流式输出 |
| AIOps 诊断 | POST | `/api/aiops` | 自动故障诊断（流式） |
| 文件上传 | POST | `/api/upload` | 上传并索引文档 |
| 健康检查 | GET | `/api/health` | 服务状态检查 |

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
│   │   ├── chat.py                         # 对话接口（RAG 聊天）
│   │   ├── aiops.py                        # AIOps 接口（故障诊断）
│   │   ├── file.py                         # 文件管理（文档上传）
│   │   └── health.py                       # 健康检查（服务状态）
│   ├── services/                           # 业务服务层
│   │   ├── __init__.py
│   │   ├── rag_agent_service.py            # RAG Agent（LangGraph 状态图）
│   │   ├── rag_retrieval_service.py        # RAG 检索流水线（候选召回 + 重排序）
│   │   ├── rerank_service.py               # OpenAI 兼容 / NVIDIA Rerank 服务与本地降级策略
│   │   ├── aiops_service.py                # AIOps 服务（计划-执行-重规划）
│   │   ├── vector_store_manager.py         # 向量存储管理器
│   │   ├── vector_embedding_service.py     # OpenAI 兼容向量 embedding 服务
│   │   ├── embedding_input_guard.py        # 检索 query 压缩与 token 预算估算
│   │   ├── vector_index_service.py         # 向量索引服务
│   │   ├── vector_search_service.py        # 向量检索服务
│   │   └── document_splitter_service.py    # 文档分割服务
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
│   │   ├── milvus_client.py                # Milvus 客户端
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
├── uploads/                                # 上传文件临时目录
├── volumes/                                # Milvus 数据持久化目录
├── .env                                    # 环境变量配置（需手动创建）
├── Makefile                                # 项目管理命令（Linux/macOS）
├── start-windows.bat                       # Windows 启动脚本
├── stop-windows.bat                        # Windows 停止脚本
├── vector-database.yml                     # Milvus Docker Compose 配置
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

# Embedding 配置
EMBEDDING_API_KEY=your-embedding-api-key
EMBEDDING_BASE_URL=https://your-embedding-provider.example.com/v1
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSIONS=1024
EMBEDDING_ENCODING_FORMAT=float
EMBEDDING_MAX_TOKENS=512
EMBEDDING_TOKEN_SAFETY_MARGIN=32

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530

# 会话持久化配置
# memory: 默认进程内 MemorySaver；postgres: PostgreSQL checkpoint，服务重启后保留 Agent 状态
SESSION_CHECKPOINT_BACKEND=memory
POSTGRES_DSN=postgresql://superbiz:superbiz_dev@localhost:5432/super_biz_agent
POSTGRES_CONNECT_TIMEOUT_SECONDS=10

# RAG 配置
RAG_TOP_K=3
RAG_CANDIDATE_TOP_K=20
RERANK_ENABLED=true
RERANK_PROVIDER=openai_compatible
RERANK_API_KEY=your-rerank-api-key
RERANK_BASE_URL=https://your-rerank-provider.example.com/v1
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_TIMEOUT_SECONDS=30
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100
```

模型配置按 Chat、Embedding、Rerank 三组独立读取。`CHAT_*`、`EMBEDDING_*`、`RERANK_*` 优先级最高；未配置时会兼容旧的 `DASHSCOPE_*` 和 `NVIDIA_*` 变量。会话持久化由 `SESSION_CHECKPOINT_BACKEND=memory|postgres` 显式控制，默认 `memory` 保持原行为，`postgres` 会强依赖 `POSTGRES_DSN`。Embedding 输入会按 `EMBEDDING_MAX_TOKENS - EMBEDDING_TOKEN_SAFETY_MARGIN` 控制预算：用户检索 query 过长时会优先保留服务名、告警、错误码、状态码等高信号信息，再用尾部截断兜底；知识库文档入库时不会智能压缩或截断原文，而是在文档分割阶段继续切成更小分片，避免服务商返回 `input must have less than 512 tokens`。使用 NVIDIA API Catalog 托管服务时，`RERANK_PROVIDER=nvidia`，代码会自动将 `https://integrate.api.nvidia.com` 映射到 `https://ai.api.nvidia.com/v1/retrieval/{model}/reranking`；如果使用自部署 NeMo Retriever Reranking NIM，也可以直接配置完整的 `/v1/ranking` 或 `/v1/retrieval/{model}/reranking` 地址。


## 💾 PostgreSQL 会话持久化

项目支持通过显式开关选择会话 checkpoint 后端：

| 模式 | 配置 | 行为 |
|---|---|---|
| 内存模式 | `SESSION_CHECKPOINT_BACKEND=memory` | 默认行为，使用 LangGraph `MemorySaver`，服务重启后会话状态不保留 |
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
- 前端启动时会请求 `GET /api/chat/sessions` 加载服务端历史会话；如果服务端没有返回历史，则继续使用本地 `localStorage` 回退。

新增会话 API：

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/chat/sessions?limit=50` | 查询服务端会话摘要列表，按更新时间倒序返回 |
| `GET` | `/api/chat/session/{session_id}` | 查询指定会话的历史消息 |
| `POST` | `/api/chat/clear` | 清空指定会话的 checkpoint，并删除会话索引摘要 |

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
请更新到当前版本的 `start-windows.bat` / `stop-windows.bat`。脚本内容应为英文 ASCII，并使用 Windows CRLF 换行，避免 `cmd.exe` 代码页解析失败。

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

### Milvus 连接失败
```bash
# 确保本机有 Docker 服务并且已经启动（可以使用 Docker Desktop）

# 检查 Milvus 状态
docker ps | grep milvus

# 重启 Milvus（使用 docker compose）
docker compose -f vector-database.yml restart

# 或者重启单个服务
docker compose -f vector-database.yml restart standalone
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
