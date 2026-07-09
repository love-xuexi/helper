"""反馈评价接口 - 精细化反馈与评价系统.

- POST /feedback          提交点赞/不喜欢反馈（不喜欢时携带结构化标签 + 补充描述）
- GET  /feedback/tags     获取结构化负反馈标签选项（前端弹窗使用）
- GET  /feedback/list     查询反馈记录（供后台审核 / 知识修正）
- GET  /feedback/stats    反馈统计
"""

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.models.request import FeedbackRequest
from app.services.feedback_service import FEEDBACK_TAGS, feedback_service

router = APIRouter()


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """提交反馈评价.

    请求示例：
    POST /feedback
    {
        "sessionId": "session-123",
        "question": "CPU 飙高怎么排查？",
        "answer": "可以先使用 top...",
        "rating": "dislike",
        "tags": ["回答不准确"],
        "comment": "第 2 步命令写错了",
        "chunkIds": ["chunk-id-1", "chunk-id-2"]
    }
    """
    try:
        record = feedback_service.save_feedback(
            session_id=request.session_id,
            question=request.question,
            answer=request.answer,
            rating=request.rating,
            message_id=request.message_id,
            tags=request.tags,
            comment=request.comment,
            chunk_ids=request.chunk_ids,
        )
        # 配置了内网反馈入库接口时同步转发（失败不影响本地入库结果）
        await feedback_service.forward_feedback(record)
        return {"code": 200, "message": "success", "data": {"feedback_id": record["id"]}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"提交反馈失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/feedback/tags")
async def get_feedback_tags():
    """获取结构化负反馈标签选项."""
    return {"code": 200, "message": "success", "data": FEEDBACK_TAGS}


@router.get("/feedback/list")
async def list_feedback(
    limit: int = Query(100, ge=1, le=500),
    rating: str | None = Query(None, description="按评价类型过滤: like / dislike"),
):
    """查询反馈记录（供后台审核 / 知识修正使用）."""
    try:
        records = feedback_service.list_feedback(limit=limit, rating=rating)
        return {"code": 200, "message": "success", "data": records}
    except Exception as e:
        logger.error(f"查询反馈失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/feedback/stats")
async def feedback_stats():
    """反馈统计（点赞/不喜欢数量）."""
    try:
        return {"code": 200, "message": "success", "data": feedback_service.get_stats()}
    except Exception as e:
        logger.error(f"反馈统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
