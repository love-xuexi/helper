"""对话接口.

提供基于 RAG Agent 的普通对话和流式对话接口

这个文件是“HTTP API 层”，本身不直接调用大模型、不直接查 Milvus。
它主要负责：
1. 接收前端传来的聊天请求
2. 调用 rag_agent_service.query(...) 或 query_stream(...)
3. 把 Agent 返回的结果包装成前端容易消费的 JSON / SSE 格式

核心接口：
- POST /chat：非流式问答，一次性返回完整答案
- POST /chat_stream：流式问答，通过 SSE 一段一段返回模型输出
- POST /chat/clear：清空某个 session 的会话历史
- GET /chat/session/{session_id}：查询某个 session 的历史消息

curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "user-123",
    "question": "CPU 飙高怎么排查？"
  }'
"""

import json

from fastapi import APIRouter, HTTPException
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.core.session_persistence import session_persistence_manager
from app.models.request import ChatRequest, ClearRequest
from app.models.response import ApiResponse, ChatSessionListResponse, SessionInfoResponse
from app.services.rag_agent_service import rag_agent_service

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """快速对话接口.

    请求示例：
    POST /chat
    {
        "id": "user-123",
        "question": "CPU 飙高怎么排查？"
    }

    这个接口走非流式链路：
    HTTP 请求进来 -> 调用 rag_agent_service.query(...) -> 等 Agent 完整回答生成完 -> 一次性返回 JSON

    最终返回示例：
    {
        "code": 200,
        "message": "success",
        "data": {
            "success": true,
            "answer": "回答内容",
            "errorMessage": null
        }
    }

    Args:
        request: 对话请求

    Returns:
        统一格式的对话响应
    """
    try:
        logger.info(f"[会话 {request.id}] 收到快速对话请求: {request.question}")
        # 调用 RAG Agent 的非流式接口。
        # request.question 是用户问题。
        # request.id 会作为 session_id/thread_id，用于区分不同会话并保存上下文。
        # 返回值包含完整答案和命中的引用来源片段。
        result = await rag_agent_service.query(request.question, session_id=request.id)

        logger.info(f"[会话 {request.id}] 快速对话完成")

        return {
            # 这里返回的是业务层统一 JSON，不是 FastAPI 的 response_model
            "code": 200,
            "message": "success",
            "data": {
                "success": True,
                "answer": result["answer"],
                "sources": result["sources"],
                "errorMessage": None,
            },
        }

    except Exception as e:
        logger.error(f"对话接口错误: {e}")
        # 注意：这里没有 raise HTTPException，而是返回 code=500 的 JSON。
        # 所以 HTTP 状态码可能仍是 200，但业务 code 表示失败。
        return {
            "code": 500,
            "message": "error",
            "data": {"success": False, "answer": None, "errorMessage": str(e)},
        }


@router.post("/chat_stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口（基于 RAG Agent，SSE）

    请求示例：
    POST /chat_stream
    {
        "id": "user-123",
        "question": "CPU 飙高怎么排查？"
    }

    这个接口返回的是 SSE（Server-Sent Events）事件流，不是普通 JSON。
    前端会持续收到 event: message，每个 message 的 data 字段是一段 JSON 字符串。

    返回 SSE 格式，data 字段为 JSON：

    工具调用事件:
    event: message
    data: {"type":"tool_call","data":{"tool":"工具名","status":"start|end","input":{...}}}

    内容流式事件:
    event: message
    data: {"type":"content","data":"内容块"}

    完成事件:
    event: message
    data: {"type":"done","data":{"answer":"完整答案","tool_calls":[...]}}

    Args:
        request: 对话请求

    Returns:
        SSE 事件流
    """
    logger.info(f"[会话 {request.id}] 收到流式对话请求: {request.question}")

    async def event_generator():
        """SSE 事件生成器.

        rag_agent_service.query_stream(...) 会不断 yield 内部 chunk，例如：
        {"type": "content", "data": "CPU"}
        {"type": "content", "data": " 飙高"}
        {"type": "complete"}

        这里会把这些内部 chunk 转换成 SSE 协议需要的格式：
        {
            "event": "message",
            "data": "{\"type\":\"content\",\"data\":\"CPU\"}"
        }

        EventSourceResponse 会再把它序列化成真正的 SSE 文本流：
        event: message
        data: {"type":"content","data":"CPU"}

        event: message
        data: {"type":"done","data":null}
        """
        try:
            # 调用 RAG Agent 的流式接口。
            # 这里不会等完整答案生成完，而是模型每产生一段内容就处理一段。
            async for chunk in rag_agent_service.query_stream(
                request.question, session_id=request.id
            ):
                chunk_type = chunk.get("type", "unknown")
                chunk_data = chunk.get("data", None)

                # 处理调试类型消息（新增）
                if chunk_type == "debug":
                    # 调试信息，可以选择发送或忽略
                    # 最终前端收到的 data JSON 大概是：
                    # {"type": "debug", "node": "...", "message_type": "..."}
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {
                                "type": "debug",
                                "node": chunk.get("node", "unknown"),
                                "message_type": chunk.get("message_type", "unknown"),
                            },
                            ensure_ascii=False,
                        ),
                    }
                elif chunk_type == "tool_call":
                    # 发送工具调用事件（可选，前端可以显示工具调用状态）
                    # 如果 Agent 暴露了工具调用过程，前端可以用这个事件展示“正在检索知识库”等状态。
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "tool_call", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "search_results":
                    # 发送检索结果（可选，前端可以忽略）
                    # 如果底层 Agent 返回了知识库检索结果，可以通过这个事件发给前端。
                    # 当前 rag_agent_service.query_stream(...) 主要 yield content/complete/error，
                    # 所以这个分支是为扩展预留的。
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "search_results", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "sources":
                    # 发送引用来源（命中的知识片段），前端用于展示引用来源和反馈关联
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "sources", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "content":
                    # 发送内容块 - 关键：data 必须是 JSON 字符串
                    # 这是最核心的流式内容事件。
                    # 前端一般会把每个 content.data 追加到当前回答文本后面。
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "content", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "complete":
                    # 发送完成信号
                    # rag_agent_service 里 complete 会被这里转换成 type="done"。
                    # 前端收到 done 后，可以停止 loading 状态。
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "done", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "error":
                    # 发送错误信息
                    # Agent 流式过程中出错时，会通过 SSE 发给前端。
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "error", "data": str(chunk_data)}, ensure_ascii=False
                        ),
                    }

            logger.info(f"[会话 {request.id}] 流式对话完成")

        except Exception as e:
            logger.error(f"流式对话接口错误: {e}")
            # event_generator 自己出错时，也尽量通过 SSE 发出 error 事件，
            # 避免前端一直等待流结束。
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False),
            }

    # EventSourceResponse 会把 async generator 包装成 text/event-stream 响应。
    # 浏览器端可以用 EventSource 或 fetch stream 方式消费。
    return EventSourceResponse(event_generator())


@router.post("/chat/clear", response_model=ApiResponse)
async def clear_session(request: ClearRequest):
    """清空会话历史.

    请求示例：
    POST /chat/clear
    {
        "session_id": "user-123"
    }

    最终效果：
    调用 rag_agent_service.clear_session(...) 删除 MemorySaver 中该 session 的历史。
    下一次同一个 session_id 再对话时，就不会带上之前上下文。

    Args:
        request: 清空请求

    Returns:
        操作结果
    """
    try:
        # request.session_id 对应 rag_agent_service 里的 thread_id
        success = rag_agent_service.clear_session(request.session_id)
        logger.info(f"清空会话: {request.session_id}, 结果: {success}")

        return ApiResponse(
            status="success" if success else "error",
            message="会话已清空" if success else "清空会话失败",
            data=None,
        )

    except Exception as e:
        logger.error(f"清空会话错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(limit: int = 50) -> ChatSessionListResponse:
    try:
        safe_limit = max(1, min(limit, 100))
        sessions = session_persistence_manager.list_chat_sessions(limit=safe_limit)
        return ChatSessionListResponse(total=len(sessions), sessions=sessions)
    except Exception as e:
        logger.error(f"获取会话列表错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/chat/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str) -> SessionInfoResponse:
    """查询会话历史.

    请求示例：
    GET /chat/session/user-123

    返回示例：
    {
        "session_id": "user-123",
        "message_count": 2,
        "history": [
            {"role": "user", "content": "CPU 飙高怎么排查？", "timestamp": "..."},
            {"role": "assistant", "content": "可以先使用 top...", "timestamp": "..."}
        ]
    }

    Args:
        session_id: 会话 ID

    Returns:
        会话信息
    """
    try:
        # 从 RAG Agent 的 MemorySaver checkpointer 中读取会话历史
        history = await rag_agent_service.get_session_history_async(session_id)

        return SessionInfoResponse(
            session_id=session_id, message_count=len(history), history=history
        )

    except Exception as e:
        logger.error(f"获取会话信息错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
