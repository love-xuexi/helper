"""管理后台聚合 API

接口列表：
  GET /api/admin/timeline  合并 Bug + 反馈，按时间倒序，统一结构，支持分页
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.bug_service import bug_service
from app.services.feedback_service import feedback_service

router = APIRouter()


def _parse_time(time_str: str) -> float:
    """将 ISO 时间字符串解析为时间戳，解析失败返回 0。"""
    if not time_str:
        return 0.0
    try:
        return datetime.fromisoformat(time_str).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _bug_to_timeline_item(bug: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "bug",
        "id": bug["id"],
        "created_at": bug["created_at"],
        "title": bug["title"],
        "summary": bug["category"],
        "status": bug["status"],
        "reporter": bug["reporter"],
        "detail": bug["content"],
        "session_id": bug.get("session_id", ""),
    }


def _feedback_to_timeline_item(fb: dict[str, Any]) -> dict[str, Any]:
    rating_label = "点赞" if fb["rating"] == "like" else "点踩"
    tags = fb.get("feedback_tags") or []
    summary_parts = [rating_label]
    if tags:
        summary_parts.append("、".join(tags))
    return {
        "type": "feedback",
        "id": fb["id"],
        "created_at": fb["created_at"],
        "title": fb.get("question", "")[:80] or "（无问题）",
        "summary": " · ".join(summary_parts),
        "rating": fb["rating"],
        "detail": fb.get("answer", ""),
        "session_id": fb.get("session_id", ""),
        "message_id": fb.get("message_id", ""),
    }


@router.get("/admin/timeline")
async def get_admin_timeline(
    limit: int = Query(10, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    user_id: str | None = Query(None, description="按用户 ID 过滤（用户隔离钩子，当前可空）"),
) -> JSONResponse:
    """合并 Bug + 反馈，按 created_at 倒序返回统一结构列表。

    每条记录包含 type 字段（'bug' 或 'feedback'），便于前端区分渲染。
    """
    try:
        # 拉取足够多的记录用于合并排序（最多拉 offset+limit 条，保证分页正确）
        fetch_limit = offset + limit

        bugs = bug_service.list_bugs(limit=fetch_limit, offset=0, user_id=user_id)
        feedbacks = feedback_service.list_feedback(
            limit=fetch_limit, offset=0, user_id=user_id
        )

        items = [_bug_to_timeline_item(b) for b in bugs]
        items.extend(_feedback_to_timeline_item(f) for f in feedbacks)

        # 按 created_at 倒序
        items.sort(key=lambda x: _parse_time(x["created_at"]), reverse=True)

        total = len(items)
        page = items[offset : offset + limit]

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": page,
                },
            },
        )
    except Exception as e:
        logger.error(f"[Admin] 获取时间线失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取时间线失败: {e}")
