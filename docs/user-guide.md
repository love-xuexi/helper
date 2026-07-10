# 使用指南（操作手册）

面向使用者的 Web 界面与 API 操作说明。部署与配置见根目录 `README.md`，本地联调见 `docs/local-dev-guide.md`。

## 1. Web 界面使用

访问 `http://<host>:9900` 打开界面（参考 ChatGPT/Claude 风格）。

### 1.1 智能问答

1. 在底部输入框输入问题，回车或点击发送。
1. 回答以流式输出，支持 Markdown 渲染与代码高亮。
1. 回答引用知识库内容时，正文会带 `[1][2]` 引用编号。
1. 知识库中没有相关内容时，回答为“无法基于当前知识库回答”，不会编造答案。

### 1.2 引用来源卡片

- 回答下方显示可折叠的 **“引用来源 (N)”** 卡片，点击展开/收起。
- 每条来源包含：编号（与正文 `[1][2]` 对应）、文档名、相似度、命中片段内容。
- 用于核对回答依据，判断答案是否可信。

### 1.3 反馈评价

- 每条回答下方有 👍（点赞）/ 👎（不喜欢）按钮。
- 点击 👍 直接提交好评。
- 点击 👎 弹出负反馈弹窗：
  1. 勾选一个或多个问题标签（回答不准确、文档已过时、逻辑不清晰、未解决实际问题、引用来源错误、其他）。
  1. 可填写补充描述（如“第 2 步命令写错了”）。
  1. 点击提交。
- 提交后按钮进入已提交状态，反馈会写入本地 SQLite（并可选转发内网反馈接口），同时关联本次回答命中的知识片段 ID，供后续审核与知识修正。

### 1.4 会话管理

- 左侧边栏可新建会话、切换历史会话。
- 配置 `SESSION_CHECKPOINT_BACKEND=postgres` 时，历史会话在服务重启后仍可恢复。

### 1.5 文件上传（知识库入库）

- 点击输入框附近的上传按钮选择文件。
- 支持 PDF / Word / Excel / PPT / 图片 / txt / md 等多种格式。
- 文件透传给知识库平台，由平台完成解析、切分与向量化；上传目标知识库由 `KB_UPLOAD_KB_ID` 决定（留空取知识库列表第一个）。

### 1.6 AIOps 智能诊断

- 点击侧边栏“智能运维与诊断工具”触发。
- 界面流式展示：诊断计划 → 每步执行进度 → 最终 Markdown 诊断报告（根因分析 + 运维建议）。

## 2. API 使用示例

完整接口列表见 README“API 接口”一节和 `http://<host>:9900/docs`。

### 2.1 问答

```bash
# 普通对话（一次性返回 answer + sources）
curl -X POST "http://localhost:9900/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"CPU 飙高怎么排查？"}'

# 流式对话（SSE；完成前会推送 sources 事件，携带本次命中的知识片段）
curl -X POST "http://localhost:9900/api/chat_stream" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"CPU 飙高怎么排查？"}' \
  --no-buffer
```

`sources` 中每个片段包含 `id`、`document_keyword`（文档名）、`similarity`、`content`，编号顺序与回答中的
`[1][2]` 对应。

### 2.2 反馈评价

```bash
# 获取负反馈标签选项（前端弹窗数据源）
curl "http://localhost:9900/api/feedback/tags"

# 提交反馈（rating: like / dislike；dislike 时可带 tags + comment）
curl -X POST "http://localhost:9900/api/feedback" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "session-123",
    "question": "CPU 飙高怎么排查？",
    "answer": "可以先使用 top...",
    "rating": "dislike",
    "tags": ["回答不准确"],
    "comment": "第 2 步命令写错了",
    "chunkIds": ["chunk-id-1", "chunk-id-2"]
  }'

# 查询反馈记录（供审核 / 知识修正；可按 rating 过滤）
curl "http://localhost:9900/api/feedback/list?limit=50&rating=dislike"

# 反馈统计（点赞/不喜欢数量）
curl "http://localhost:9900/api/feedback/stats"
```

### 2.3 知识库管理

```bash
# 知识库列表
curl "http://localhost:9900/api/kb/list"

# 指定知识库的文档列表
curl "http://localhost:9900/api/kb/<kb_id>/docs"

# FAQ 问答库检索
curl -X POST "http://localhost:9900/api/kb/faq" \
  -H "Content-Type: application/json" \
  -d '{"question":"如何重置密码"}'

# 上传文档到知识库
curl -X POST "http://localhost:9900/api/upload" \
  -F "file=@./运维手册.pdf"
```

## 3. 常见问题

- **回答总是“无法基于当前知识库回答”**：检索未命中或知识库平台不可达。确认内网可访问 `KB_DOC_BASE_URL`、`KB_API_TOKEN`
  有效，并查看 `logs/app_YYYY-MM-DD.log`。
- **没有引用来源卡片**：本次回答未调用知识库检索（如闲聊、时间类问题），属正常现象。
- **反馈提交失败**：检查 `data/feedback.db` 所在目录可写；配置了 `FEEDBACK_API_URL` 时转发失败不影响本地入库。
- 更多部署类问题见 README“常见问题”。
