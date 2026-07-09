# 智能问答助手

> 基于知识库 API 的智能问答系统，支持 RAG 检索、引用来源标注、反馈评价

## ✨ 核心特性

- 🤖 **智能问答** - 调用知识库 API 完成混合语义检索，LLM 基于检索结果生成回答
- 📎 **引用标注** - 每条回答附带引用来源（文档名称、片段ID、相似度），可溯源核实，减少幻觉
- 👍 **反馈评价** - 点赞/不喜欢按钮 + 结构化负反馈收集（回答不准确、文档已过时等），反馈数据入库
- 💬 **多轮对话** - 保留最近 3-5 轮上下文，支持多轮问答
- 📚 **知识库管理** - 列出知识库、查看文档列表、上传文档（支持 PDF/Word/Excel/图片等）
- 🌐 **现代界面** - 参考 ChatGPT/Claude 风格，简洁好用

## 🏗️ 架构说明

```
用户提问
  ↓
[知识库 API] → 检索相关片段（混合语义检索 + 重排，由知识库平台完成）
  ↓
[上下文构建] → 格式化为带编号的参考资料
  ↓
[LLM] → 基于上下文生成回答，内联标注 [1][2] 引用编号
  ↓
返回 答案 + 引用来源 + message_id
  ↓
用户可点赞/不喜欢 → 反馈数据存入 SQLite
```

**与旧版区别**：不再需要本地 Milvus 向量库、Embedding 服务、Rerank 服务，RAG 检索直接调用内网知识库 API。

## 🚀 快速开始

### 环境要求
- Python 3.11、3.12 或 3.13
- Chat LLM API Key（DeepSeek / OpenAI / Qwen 等兼容接口）
- 内网知识库 API 可达（默认地址已配置）

### 安装和启动（Windows）

```powershell
# 1. 克隆项目并进入目录
cd helper

# 2. 编辑配置文件
notepad .env
# 填入 CHAT_API_KEY 等配置（参考 .env.example）

# 3. 一键启动
.\start-windows.bat

# 4. 停止服务
.\stop-windows.bat
```

### 访问服务
- **Web 界面**: http://localhost:9900
- **API 文档**: http://localhost:9900/docs

## 📡 API 接口

### 核心接口

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 流式对话 | POST | `/api/chat_stream` | SSE 流式输出，含引用来源 |
| 快速对话 | POST | `/api/chat` | 一次性返回答案 + 引用 |
| 清空会话 | POST | `/api/chat/clear` | 清空指定会话历史 |
| 会话列表 | GET | `/api/chat/sessions` | 获取所有会话摘要 |
| 会话历史 | GET | `/api/chat/session/{id}` | 获取指定会话消息 |
| 提交反馈 | POST | `/api/feedback` | 点赞/不喜欢 + 结构化负反馈 |
| 反馈列表 | GET | `/api/feedback` | 分页查询反馈 |
| 反馈统计 | GET | `/api/feedback/stats` | 点赞率、标签分布等 |
| 负反馈标签 | GET | `/api/feedback/tags` | 获取预设负反馈选项 |
| 知识库列表 | GET | `/api/knowledge-bases` | 列出所有知识库 |
| 文档列表 | GET | `/api/knowledge-bases/{kb_id}/docs` | 指定知识库的文档 |
| 上传文档 | POST | `/api/upload` | 上传文档到知识库 |
| 健康检查 | GET | `/api/health` | 服务状态 + KB API 连通性 |

### 使用示例

```bash
# 流式对话
curl -X POST "http://localhost:9900/api/chat_stream" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"寿险投保规则是什么？"}' \
  --no-buffer

# 提交反馈
curl -X POST "http://localhost:9900/api/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId":"session-123",
    "messageId":"msg-456",
    "rating":"dislike",
    "feedbackTags":["回答不准确"],
    "feedbackDescription":"回答中提到的体检标准和实际不符",
    "chunkIds":["859cffd18e948c98"]
  }'
```

## ⚙️ 配置说明

通过 `.env` 文件配置（参考 `.env.example`）：

### 必填配置

```bash
# Chat LLM 配置（用于生成回答）
CHAT_PROVIDER=deepseek
CHAT_API_KEY=sk-your-api-key
CHAT_BASE_URL=https://api.deepseek.com/v1
CHAT_MODEL=deepseek-chat

# 知识库 API 配置（内网地址，默认已填好）
KB_RETRIEVAL_BASE_URL=http://10.8.192.79:5353
KB_MANAGEMENT_BASE_URL=http://10.8.192.79:5354
KB_FAQ_BASE_URL=http://10.8.192.79:6000
KB_API_TOKEN=kbmp-i94DZSu3_pUMxcA0seYAe-Hcod3_EJRf
KB_BOTCODE=25d4c12e46834cc39bc211b84a9b2462
```

### 可选配置

```bash
# 反馈数据库路径（SQLite）
FEEDBACK_DB_PATH=./data/feedback.db

# 可选：反馈数据外部推送 API
FEEDBACK_EXTERNAL_API_URL=
FEEDBACK_EXTERNAL_API_TOKEN=

# 会话持久化（memory 或 postgres）
SESSION_CHECKPOINT_BACKEND=memory
```

## 📁 项目结构

```
helper/
├── app/                                # 应用核心
│   ├── main.py                         # FastAPI 应用入口
│   ├── config.py                       # 配置管理
│   ├── api/                            # API 路由层
│   │   ├── chat.py                     # 对话接口（RAG + 引用）
│   │   ├── feedback.py                 # 反馈评价接口
│   │   ├── file.py                     # 文件上传 + 知识库管理
│   │   ├── health.py                   # 健康检查
│   │   └── aiops.py                    # AIOps（预留）
│   ├── services/                       # 业务服务层
│   │   ├── kb_api_client.py            # 知识库 API 客户端
│   │   ├── rag_agent_service.py        # RAG 问答服务（检索 + 生成）
│   │   └── feedback_service.py         # 反馈评价服务（SQLite）
│   ├── models/                         # 数据模型
│   ├── core/                           # 核心组件（LLM工厂、会话持久化）
│   └── tools/                           # 工具模块
├── static/                             # Web 前端
│   ├── index.html                      # 主页面
│   ├── app.js                          # 前端逻辑
│   └── styles.css                      # 样式表
├── data/                               # 数据目录（反馈数据库）
├── .env                                # 环境变量配置
├── .env.example                        # 环境变量模板
├── start-windows.bat                   # Windows 启动脚本
├── stop-windows.bat                    # Windows 停止脚本
└── pyproject.toml                      # 项目配置
```

## 🎯 功能模块

### 1. 智能问答与多模态检索

- **混合语义检索**：调用知识库 API 完成向量检索 + 关键词检索 + 重排，返回最相关的 3-5 条片段
- **多源异构解析**：知识库平台支持 PDF、Word、Excel、图片等多种格式
- **上下文管理**：保留最近 3-5 轮对话历史，支持多轮问答
- **结构化答案生成**：AI 基于检索文档生成回答，强制要求附带引用来源 [1][2]，无答案时回答"根据现有知识库无法回答"

### 2. 精细化反馈与评价系统

- **多维评价机制**：每条回答下方设置"点赞"与"不喜欢"按钮
- **结构化负反馈收集**：点击"不喜欢"时弹出结构化选项（回答不准确、文档已过时、逻辑不清晰、未解决实际问题等），并预留文本框补充详细描述
- **反馈数据入库**：将用户原始提问、AI回答、评价标签、详细描述及关联的知识片段ID存入反馈数据库

### 3. 知识库自进化（预留，后续实现）

- 优质问答自动沉淀
- 知识盲区与纠错预警
- 黄金测试集自动化评估

### 4. 运维助手进阶（预留，最终形态）

- NL2SQL / 工具调用（Function Calling）
- 智能运维建议

## 📝 开发指南

### 代码质量

```bash
# 格式化
black app/ && isort app/

# 代码检查
ruff check app/

# 类型检查
pyright app/
```

### 反馈数据查看

反馈数据存储在 `./data/feedback.db`（SQLite），可直接查询：

```bash
# 查看所有反馈
sqlite3 data/feedback.db "SELECT id, rating, feedback_tags, feedback_description, created_at FROM feedback ORDER BY created_at DESC LIMIT 20;"

# 查看统计
sqlite3 data/feedback.db "SELECT rating, COUNT(*) FROM feedback GROUP BY rating;"
```

## 📄 许可证

MIT License
