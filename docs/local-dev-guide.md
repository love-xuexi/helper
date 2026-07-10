# 本地联调与测试手册

知识库平台和部分 LLM 接口仅内网可达。本手册说明在**内网不可达的开发机**上如何用 mock 服务完成端到端联调，以及如何运行测试。

## 1. Mock 服务

`scripts/dev/` 提供两个本地 mock 服务（真实链路代码不变，只替换外部依赖端点）：

| 脚本                             | 端口 | 模拟对象                                                                                                                                   |
| -------------------------------- | ---: | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `scripts/dev/mock_kb_server.py`  | 5353 | 知识库平台文档检索 `/v1/doc/retrieval/`、知识库/文档列表接口，返回 2 个固定的运维知识片段                                                  |
| `scripts/dev/mock_llm_server.py` | 9901 | OpenAI 兼容 `/v1/chat/completions`（含 stream）：首轮返回 `retrieve_knowledge` tool_call，拿到工具结果后返回带 `[1][2]` 引用编号的最终回答 |

## 2. 联调步骤

1. 配置 `.env`（指向本地 mock）：

   ```bash
   CHAT_PROVIDER=openai
   CHAT_API_KEY=mock
   CHAT_BASE_URL=http://127.0.0.1:9901/v1
   CHAT_MODEL=mock

   KB_API_TOKEN=kbmp-mock
   KB_DOC_BASE_URL=http://127.0.0.1:5353
   KB_MGMT_BASE_URL=http://127.0.0.1:5353
   ```

1. 分别启动（各开一个终端窗口）：

   ```powershell
   python scripts\dev\mock_kb_server.py
   python scripts\dev\mock_llm_server.py
   python mcp_servers\cls_server.py
   python mcp_servers\monitor_server.py
   python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
   ```

1. 访问 `http://localhost:9900`，提问“CPU 飙高怎么排查？”，应看到：

   - 流式回答带 `[1][2]` 引用编号；
   - 回答下方出现可展开的“引用来源 (2)”卡片（运维手册-CPU问题排查.pdf、JVM调优指南.docx）；
   - 👍/👎 反馈可提交，`GET /api/feedback/list`、`/api/feedback/stats` 可查到落库数据。

也可用命令行验证：

```bash
curl -X POST "http://localhost:9900/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"Id":"local-test","Question":"CPU 飙高怎么排查？"}'
```

返回 JSON 中应包含 `answer`（带引用编号）和 `sources`（2 个片段）。

## 3. 运行单元测试

单元测试全部基于 mock，不依赖内网：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

覆盖范围包括 `kb_api_service`（检索/过滤/降级）、`feedback_service`（入库/统计/转发）、会话历史、配置兼容等。

## 4. 上线前真实冒烟

内网环境部署后建议做一次真实冒烟：

1. `.env` 填入真实 `CHAT_*` 与 `KB_API_TOKEN` 等（见 `.env.example`）。
1. `GET /api/kb/list` 确认平台连通与 Token 有效。
1. 用一个知识库内确有答案的问题调用 `/api/chat`，确认回答带引用且 `sources` 非空。
1. 提交一条 👎 反馈，确认 `GET /api/feedback/list` 可查到；若配置了
   `FEEDBACK_API_URL`，在内网反馈系统侧确认已同步。

## 5. UI 回归测试

前端引用来源卡片 + 反馈弹窗的完整 UI
测试步骤已沉淀为技能：`.agents/skills/testing-helper-rag-feedback/SKILL.md`。
