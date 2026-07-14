"""Bug 上报 API

接口列表：
  POST  /api/bug/report       上报 Bug（支持附件上传）
  GET   /api/bug/list         列出 Bug（支持 status/category 过滤、分页）
  GET   /api/bug/{bug_id}     获取单条 Bug 详情
  PUT   /api/bug/{bug_id}/status  更新 Bug 状态
  GET   /api/bug/stats        Bug 统计（总数、状态分布、分类分布）
  GET   /api/bug/categories   获取预设分类列表
"""

import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.bug_service import BUG_CATEGORIES, BUG_STATUSES, bug_service

router = APIRouter()

# 附件大小限制 20MB
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "bmp", "webp",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "md", "csv", "log", "zip", "json",
}


@router.get("/bug/categories")
async def get_bug_categories() -> JSONResponse:
    """获取预设的 Bug 分类列表。"""
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": {
                "categories": BUG_CATEGORIES,
                "statuses": BUG_STATUSES,
            },
        },
    )


@router.post("/bug/report")
async def report_bug(
    reporter: str = Form("anonymous", description="上报人"),
    category: str = Form(..., description="分类: 检索问题/生成问题/模型配置问题/其他"),
    title: str = Form(..., description="Bug 标题"),
    content: str = Form(..., description="Bug 详细描述"),
    session_id: str = Form("", description="关联会话 ID"),
    query: str = Form("", description="当时的用户问题"),
    answer: str = Form("", description="当时的 AI 回答"),
    user_id: str = Form("", description="用户 ID（用户隔离钩子，当前可空）"),
    attachment: UploadFile | None = File(None, description="附件（可选）"),
) -> JSONResponse:
    """上报 Bug，支持附件上传。

    请求方式：POST /api/bug/report (multipart/form-data)
    """
    try:
        attachment_path = ""

        if attachment and attachment.filename:
            ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else ""
            if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的附件格式 .{ext}，支持: {', '.join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))}",
                )

            file_content = await attachment.read()
            if len(file_content) > MAX_ATTACHMENT_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"附件大小超过限制（最大 {MAX_ATTACHMENT_SIZE // 1024 // 1024}MB）",
                )

            # 保存附件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{attachment.filename}"
            upload_dir = Path(bug_service.upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / safe_filename
            file_path.write_bytes(file_content)
            attachment_path = str(file_path)
            logger.info(f"[Bug] 附件已保存: {attachment_path}")

        result = bug_service.report_bug(
            reporter=reporter,
            category=category,
            title=title,
            content=content,
            session_id=session_id,
            query=query,
            answer=answer,
            attachment_path=attachment_path,
            user_id=user_id,
        )
        logger.info(f"[Bug] 上报成功: id={result['id']}, category={category}")

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "Bug 上报成功",
                "data": result,
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bug] 上报失败: {e}")
        raise HTTPException(status_code=500, detail=f"Bug 上报失败: {e}")


@router.get("/bug/list")
async def list_bugs(
    status: str | None = Query(None, description="按状态过滤"),
    category: str | None = Query(None, description="按分类过滤"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    user_id: str | None = Query(None, description="按用户 ID 过滤（用户隔离钩子，当前可空）"),
) -> JSONResponse:
    """列出 Bug（按时间倒序）。"""
    try:
        if status and status not in BUG_STATUSES:
            raise HTTPException(status_code=400, detail=f"status 必须是: {', '.join(BUG_STATUSES)}")
        if category and category not in BUG_CATEGORIES:
            raise HTTPException(status_code=400, detail=f"category 必须是: {', '.join(BUG_CATEGORIES)}")

        items = bug_service.list_bugs(
            limit=limit, offset=offset, status=status, category=category, user_id=user_id
        )
        total = bug_service.count_bugs(status=status, category=category, user_id=user_id)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": items,
                },
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bug] 列出 Bug 失败: {e}")
        raise HTTPException(status_code=500, detail=f"列出 Bug 失败: {e}")


@router.get("/bug/stats")
async def get_bug_stats() -> JSONResponse:
    """获取 Bug 统计数据。"""
    try:
        stats = bug_service.get_stats()
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": stats,
            },
        )
    except Exception as e:
        logger.error(f"[Bug] 获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {e}")


@router.get("/bug/timeline")
async def get_bug_timeline(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
) -> JSONResponse:
    """获取 Bug 上报时间序列数据（按天聚合，用于折线图）。"""
    try:
        timeline = bug_service.get_timeline(days=days)
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {"timeline": timeline, "days": days},
            },
        )
    except Exception as e:
        logger.error(f"[Bug] 获取时间序列失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取时间序列失败: {e}")


@router.get("/bug/{bug_id}")
async def get_bug(bug_id: int) -> JSONResponse:
    """获取单条 Bug 详情。"""
    try:
        result = bug_service.get_bug(bug_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Bug 不存在")
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": result,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bug] 获取 Bug 详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 Bug 详情失败: {e}")


@router.put("/bug/{bug_id}/status")
async def update_bug_status(bug_id: int, status: str = Query(..., description="新状态")) -> JSONResponse:
    """更新 Bug 状态。"""
    try:
        if status not in BUG_STATUSES:
            raise HTTPException(status_code=400, detail=f"status 必须是: {', '.join(BUG_STATUSES)}")

        result = bug_service.update_status(bug_id, status)
        if result is None:
            raise HTTPException(status_code=404, detail="Bug 不存在")

        logger.info(f"[Bug] 状态更新成功: id={bug_id}, status={status}")
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "状态更新成功",
                "data": result,
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Bug] 更新状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新状态失败: {e}")
