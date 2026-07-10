"""本地联调用：模拟 OpenAI 兼容的 Chat Completions 接口，监听 127.0.0.1:9901。

用法见 docs/local-dev-guide.md。

行为：
- 如果请求带有 retrieve_knowledge 工具且对话中还没有 tool 结果 -> 返回 tool_call
- 如果对话中已有 tool 结果 -> 返回带 [1][2] 引用编号的最终回答
- 无工具（直连模式）-> 返回寒暄回答
支持 stream 与非 stream。
"""

import json
import time
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

FINAL_ANSWER = (
    "CPU 飙高可以按以下步骤排查：\n\n"
    "1. 使用 top 命令查看占用最高的进程，再用 top -Hp 定位具体线程，"
    "结合 jstack 分析热点代码 [1]。\n"
    "2. 如果是 GC 频繁导致，可通过 jstat -gcutil 观察 GC 情况，"
    "必要时调整堆大小或排查内存泄漏 [2]。"
)

SMALL_TALK_ANSWER = "你好！我是企业智能问答助手，可以帮你检索知识库并回答问题。"


def _chunk(id_, model, delta, finish_reason=None):
    return {
        "id": id_,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "mock")
    messages = body.get("messages", [])
    tools = body.get("tools") or []
    stream = body.get("stream", False)
    has_tool_result = any(m.get("role") == "tool" for m in messages)
    has_retrieve = any((t.get("function") or {}).get("name") == "retrieve_knowledge" for t in tools)
    user_msg = next((m for m in reversed(messages) if m.get("role") == "user"), {})
    question = user_msg.get("content", "") or ""

    comp_id = "chatcmpl-" + uuid.uuid4().hex[:12]

    if has_retrieve and not has_tool_result:
        # 第一步：让 Agent 调 retrieve_knowledge
        tool_call = {
            "id": "call_" + uuid.uuid4().hex[:8],
            "type": "function",
            "function": {
                "name": "retrieve_knowledge",
                "arguments": json.dumps({"query": question}, ensure_ascii=False),
            },
        }
        if not stream:
            return {
                "id": comp_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            }

        def gen_tool():
            first = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "index": 0,
                        "id": tool_call["id"],
                        "type": "function",
                        "function": {
                            "name": "retrieve_knowledge",
                            "arguments": tool_call["function"]["arguments"],
                        },
                    }
                ],
            }
            yield "data: " + json.dumps(_chunk(comp_id, model, first), ensure_ascii=False) + "\n\n"
            yield (
                "data: "
                + json.dumps(_chunk(comp_id, model, {}, "tool_calls"), ensure_ascii=False)
                + "\n\n"
            )
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen_tool(), media_type="text/event-stream")

    answer = FINAL_ANSWER if (has_tool_result or has_retrieve) else SMALL_TALK_ANSWER

    if not stream:
        return {
            "id": comp_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60},
        }

    def gen_content():
        yield (
            "data: "
            + json.dumps(
                _chunk(comp_id, model, {"role": "assistant", "content": ""}), ensure_ascii=False
            )
            + "\n\n"
        )
        # 按小片段流式输出
        step = 8
        for i in range(0, len(answer), step):
            piece = answer[i : i + step]
            yield (
                "data: "
                + json.dumps(_chunk(comp_id, model, {"content": piece}), ensure_ascii=False)
                + "\n\n"
            )
            time.sleep(0.03)
        yield "data: " + json.dumps(_chunk(comp_id, model, {}, "stop"), ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen_content(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9901)
