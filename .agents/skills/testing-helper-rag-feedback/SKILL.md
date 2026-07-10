______________________________________________________________________

## name: testing-helper-rag-feedback description: End-to-end UI testing procedure for the helper project's RAG citation sources card and like/dislike feedback flow, using local mock KB platform and mock LLM servers when the intranet is unreachable.

# Testing helper RAG citations + feedback UI

内网知识库/LLM 不可达时，用本地 mock 完成引用来源卡片与反馈评价的端到端 UI 回归测试。

## 环境准备

1. `.env` 指向本地 mock（详见 `docs/local-dev-guide.md`）：
   - `CHAT_PROVIDER=openai`、`CHAT_BASE_URL=http://127.0.0.1:9901/v1`、`CHAT_API_KEY=mock`、`CHAT_MODEL=mock`
   - `KB_DOC_BASE_URL=http://127.0.0.1:5353`、`KB_MGMT_BASE_URL=http://127.0.0.1:5353`、`KB_API_TOKEN=kbmp-mock`
1. 启动（各一个终端）：
   - `python scripts\dev\mock_kb_server.py`（:5353，返回 2 个片段：运维手册-CPU问题排查.pdf 0.92
     / JVM调优指南.docx 0.85）
   - `python scripts\dev\mock_llm_server.py`（:9901，首轮返回 retrieve_knowledge
     tool_call，随后返回带 \[1\]\[2\] 的回答）
   - `python mcp_servers\cls_server.py`、`python mcp_servers\monitor_server.py`
   - `python -m uvicorn app.main:app --host 0.0.0.0 --port 9900`
1. 打开 `http://127.0.0.1:9900`。注意：每个问答测试用**全新 session**（同 session 重复提问时会话记忆会让
   mock LLM 跳过工具调用）。

## Test 1: 流式问答显示引用来源卡片

新建会话，提问 “CPU 飙高怎么排查？”（默认流式）。

通过标准：

- 流式回答文本包含 `[1]`、`[2]` 引用编号；
- 回答下方出现可折叠的 “引用来源 (2)”；
- 展开后显示两个文档名、相似度与片段内容。

## Test 2: 点赞反馈

点击该回答的 👍。

通过标准：

- 按钮进入已提交/选中状态；
- `GET /api/feedback/stats` 中 like 计数 +1（测试前后各查一次）。

## Test 3: 不喜欢 → 结构化负反馈弹窗

点击 👎 → 弹窗；勾选 “回答不准确”“引用来源错误”；填写评论 “测试负反馈”；提交。

通过标准：

- 弹窗展示来自 `/api/feedback/tags` 的全部 6 个标签；
- 选中标签高亮，提交后弹窗关闭；
- `GET /api/feedback/list` 最新记录：rating=dislike、tags 与评论一致、chunk_ids 含
  `chunk-001`。

## Test 4: 非流式 /api/chat 返回 sources（shell 证据）

用全新 session `POST /api/chat`，返回 JSON 应含带引用编号的 `answer` 和 2 个
`sources`（id/document_name/similarity）。

## 注意事项

- mock
  返回结构需符合平台接口文档：`data.chunks[].{id, content, document_keyword, similarity}`。
- 上线前仍需用真实 `KB_API_TOKEN` 做冒烟（见 `docs/local-dev-guide.md` 第 4 节）。
