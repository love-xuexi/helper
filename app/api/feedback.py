"""反馈评价 API

接口列表：
  POST   /api/feedback          提交反馈（点赞/不喜欢 + 结构化负反馈）
  GET    /api/feedback          列出反馈（支持 rating 过滤、分页）
  GET    /api/feedback/stats    反馈统计
  GET    /api/feedback/tags     获取预设负反馈标签列表
  GET    /api/feedback/{id}     获取单条反馈详情
  GET    /api/feedback/message/{message_id}  根据 message_id 查询反馈状态
  DELETE /api/feedback/{id}     删除反馈
"""

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.models.request import FeedbackRequest
from app.models.response import (
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatsResponse,
    SimpleApiResponse,
)
from app.services.feedback_service import NEGATIVE_FEEDBACK_TAGS, feedback_service

router = APIRouter()


@router.get("/feedback/tags")
async def get_feedback_tags() -> SimpleApiResponse:
    """获取预设的负反馈标签列表（供前端弹窗渲染选项）。"""
    return SimpleApiResponse(
        status="success",
        message="获取负反馈标签成功",
        data={"tags": NEGATIVE_FEEDBACK_TAGS},
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """提交反馈。

    请求示例：
    POST /api/feedback
    {
        "session_id": "session_xxx",
        "message_id": "msg_xxx",
        "rating": "dislike",
        "question": "寿险投保规则是什么？",
        "answer": "根据参考资料...",
        "feedback_tags": ["回答不准确", "逻辑不清晰"],
        "feedback_description": "回答中提到的体检标准和实际不符",
        "chunk_ids": ["859cffd18e948c98", "4e8e15b8c9dd51b2"]
    }
    """
    try:
        # 校验：dislike 时建议填写 tags 或 description，但不强制
        if request.rating == "dislike":
            if not request.feedback_tags and not request.feedback_description:
                logger.info(f"[Feedback] dislike 反馈未填写具体原因, message_id={request.message_id}")

        result = await feedback_service.submit_feedback(
            session_id=request.session_id,
            message_id=request.message_id,
            rating=request.rating,
            question=request.question or "",
            answer=request.answer or "",
            feedback_tags=request.feedback_tags,
            feedback_description=request.feedback_description or "",
            chunk_ids=request.chunk_ids,
            user_id=request.user_id or "",
        )
        logger.info(f"[Feedback] 反馈提交成功: id={result['id']}, rating={request.rating}")
        return FeedbackResponse(
            status="success",
            message="反馈提交成功",
            data=result,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[Feedback] 提交反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"提交反馈失败: {e}")


@router.get("/feedback", response_model=FeedbackListResponse)
async def list_feedback(
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    rating: str | None = Query(None, description="按评分过滤: like / dislike"),
    user_id: str | None = Query(None, description="按用户 ID 过滤（用户隔离钩子，当前可空）"),
    tag: str | None = Query(None, description="按负反馈标签过滤"),
) -> FeedbackListResponse:
    """列出反馈（按时间倒序）。"""
    try:
        if rating and rating not in ("like", "dislike"):
            raise HTTPException(status_code=400, detail="rating 必须是 'like' 或 'dislike'")

        items = feedback_service.list_feedback(
            limit=limit, offset=offset, rating=rating, user_id=user_id, tag=tag
        )
        total = feedback_service.count_feedback(rating=rating, user_id=user_id, tag=tag)
        return FeedbackListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Feedback] 列出反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出反馈失败: {e}")


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats() -> FeedbackStatsResponse:
    """获取反馈统计数据。"""
    try:
        stats = feedback_service.get_stats()
        return FeedbackStatsResponse(
            status="success",
            message="获取统计成功",
            data=stats,
        )
    except Exception as e:
        logger.error(f"[Feedback] 获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {e}")


@router.get("/feedback/timeline", response_model=FeedbackStatsResponse)
async def get_feedback_timeline(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
) -> FeedbackStatsResponse:
    """获取反馈时间序列数据（按天聚合，用于折线图）。"""
    try:
        timeline = feedback_service.get_timeline(days=days)
        return FeedbackStatsResponse(
            status="success",
            message="获取时间序列成功",
            data={"timeline": timeline, "days": days},
        )
    except Exception as e:
        logger.error(f"[Feedback] 获取时间序列失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取时间序列失败: {e}")


@router.get("/feedback/message/{message_id}", response_model=FeedbackResponse)
async def get_feedback_by_message(message_id: str) -> FeedbackResponse:
    """根据 message_id 查询反馈状态（前端用于显示已评价状态）。"""
    try:
        result = feedback_service.get_feedback_by_message_id(message_id)
        if result is None:
            return FeedbackResponse(
                status="success",
                message="暂无反馈",
                data=None,
            )
        return FeedbackResponse(
            status="success",
            message="获取反馈成功",
            data=result,
        )
    except Exception as e:
        logger.error(f"[Feedback] 查询反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询反馈失败: {e}")


@router.get("/feedback/{feedback_id}", response_model=FeedbackResponse)
async def get_feedback(feedback_id: int) -> FeedbackResponse:
    """获取单条反馈详情。"""
    try:
        result = feedback_service.get_feedback(feedback_id)
        if result is None:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return FeedbackResponse(
            status="success",
            message="获取反馈成功",
            data=result,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Feedback] 获取反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取反馈失败: {e}")


@router.delete("/feedback/{feedback_id}", response_model=SimpleApiResponse)
async def delete_feedback(feedback_id: int) -> SimpleApiResponse:
    """删除一条反馈。"""
    try:
        success = feedback_service.store.delete_feedback(feedback_id)
        if not success:
            raise HTTPException(status_code=404, detail="反馈不存在")
        return SimpleApiResponse(
            status="success",
            message="反馈已删除",
            data={"id": feedback_id},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Feedback] 删除反馈失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除反馈失败: {e}")
