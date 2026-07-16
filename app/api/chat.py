"""对话接口

提供基于知识库 API 的 RAG 问答接口，支持引用来源标注和反馈关联。

核心接口：
- POST /chat：非流式问答，一次性返回答案 + 引用来源 + message_id
- POST /chat_stream：流式问答（SSE），包含检索状态、引用来源、流式内容
- POST /chat/clear：清空会话历史
- GET /chat/session/{session_id}：查询会话历史
- GET /chat/sessions：列出所有会话
- PUT /chat/session/{session_id}/rename：重命名会话标题
- GET /chat/suggestions：获取推荐问题（基于用户点赞数据）
"""

import json

from fastapi import APIRouter, HTTPException
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.core.session_persistence import session_persistence_manager
from app.models.request import ChatRequest, ClearRequest, RenameSessionRequest
from app.models.response import (
    ApiResponse,
    ChatResultData,
    ChatSessionListResponse,
    SessionInfoResponse,
)
from app.services.feedback_service import feedback_service
from app.services.rag_agent_service import rag_agent_service

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    """快速对话接口（非流式）

    返回示例：
    {
        "code": 200,
        "message": "success",
        "data": {
            "success": true,
            "answer": "回答内容[1]...",
            "citations": [
                {"index": 1, "id": "xxx", "document": "xxx.xlsx", "similarity": 0.77, "content_preview": "..."}
            ],
            "message_id": "msg_xxx",
            "error_message": null
        }
    }
    """
    try:
        logger.info(f"[会话 {request.id}] 收到快速对话请求: {request.question}")
        result = await rag_agent_service.query(request.question, session_id=request.id)

        return {
            "code": 200,
            "message": "success",
            "data": ChatResultData(
                success=True,
                answer=result["answer"],
                citations=result["citations"],
                message_id=result["message_id"],
                error_message=None,
            ).model_dump(),
        }

    except Exception as e:
        logger.error(f"对话接口错误: {e}")
        return {
            "code": 500,
            "message": "error",
            "data": ChatResultData(
                success=False,
                answer=None,
                citations=[],
                message_id=None,
                error_message=str(e),
            ).model_dump(),
        }


@router.post("/chat_stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口（SSE）

    SSE 事件类型：
    - {"type": "retrieving", "data": null}                    正在检索知识库
    - {"type": "search_results", "data": [...]}               检索完成，返回引用列表
    - {"type": "content", "data": "文本片段"}                 答案流式内容
    - {"type": "done", "data": {"answer":..., "citations":..., "message_id":...}}
    - {"type": "error", "data": "错误信息"}
    """
    logger.info(f"[会话 {request.id}] 收到流式对话请求: {request.question}")

    async def event_generator():
        try:
            async for chunk in rag_agent_service.query_stream(
                request.question, session_id=request.id
            ):
                chunk_type = chunk.get("type", "unknown")
                chunk_data = chunk.get("data", None)

                if chunk_type == "retrieving":
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "retrieving", "data": None}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "search_results":
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "search_results", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "content":
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "content", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "done":
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "done", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "error":
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "error", "data": str(chunk_data)}, ensure_ascii=False
                        ),
                    }

            logger.info(f"[会话 {request.id}] 流式对话完成")

        except Exception as e:
            logger.error(f"流式对话接口错误: {e}")
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/clear", response_model=ApiResponse)
async def clear_session(request: ClearRequest):
    """清空会话历史。"""
    try:
        success = rag_agent_service.clear_session(request.session_id)
        logger.info(f"清空会话: {request.session_id}, 结果: {success}")
        return ApiResponse(
            status="success" if success else "error",
            message="会话已清空" if success else "清空会话失败",
            data=None,
        )
    except Exception as e:
        logger.error(f"清空会话错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    limit: int = 10,
    offset: int = 0,
    user_id: str | None = None,
) -> ChatSessionListResponse:
    try:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        sessions = session_persistence_manager.list_chat_sessions(
            limit=safe_limit, offset=safe_offset, user_id=user_id
        )
        total = session_persistence_manager.count_chat_sessions(user_id=user_id)
        return ChatSessionListResponse(
            total=total, limit=safe_limit, offset=safe_offset, sessions=sessions
        )
    except Exception as e:
        logger.error(f"获取会话列表错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(session_id: str) -> SessionInfoResponse:
    """查询会话历史。"""
    try:
        history = await rag_agent_service.get_session_history_async(session_id)
        return SessionInfoResponse(
            session_id=session_id, message_count=len(history), history=history
        )
    except Exception as e:
        logger.error(f"获取会话信息错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chat/session/{session_id}/rename", response_model=ApiResponse)
async def rename_session(session_id: str, request: RenameSessionRequest) -> ApiResponse:
    """重命名会话标题。"""
    try:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        success = session_persistence_manager.rename_chat_session(session_id, title)
        if not success:
            raise HTTPException(status_code=404, detail="会话不存在")
        logger.info(f"重命名会话: {session_id} -> {title}")
        return ApiResponse(status="success", message="会话标题已更新", data={"title": title})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重命名会话错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/suggestions")
async def get_suggestions(limit: int = 4) -> dict:
    """获取推荐问题（基于用户点赞数据，不足时由前端补充默认问题）。"""
    try:
        safe_limit = max(1, min(limit, 10))
        popular = feedback_service.get_popular_questions(limit=safe_limit)
        return {
            "code": 200,
            "message": "success",
            "data": {"suggestions": popular},
        }
    except Exception as e:
        logger.error(f"获取推荐问题错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
