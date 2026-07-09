"""知识库管理接口（透传内网知识库平台）.

- GET  /kb/list             知识库列表
- GET  /kb/{kb_id}/docs     指定知识库的文档列表
- POST /kb/faq              FAQ 问答库检索
"""

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from app.services.kb_api_service import kb_api_service

router = APIRouter()


class FaqRequest(BaseModel):
    """FAQ 检索请求."""

    query: str = Field(..., description="查询内容")
    channel: str = Field("", description="渠道（留空使用默认配置）")


@router.get("/kb/list")
async def list_kbs():
    """获取知识库列表."""
    try:
        kbs = await kb_api_service.list_kbs()
        return {"code": 200, "message": "success", "data": kbs}
    except Exception as e:
        logger.error(f"获取知识库列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/kb/{kb_id}/docs")
async def list_kb_docs(kb_id: str):
    """获取指定知识库的文档列表."""
    try:
        docs = await kb_api_service.list_docs(kb_id)
        return {"code": 200, "message": "success", "data": docs}
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/kb/faq")
async def faq_retrieve(request: FaqRequest):
    """FAQ 问答库检索."""
    try:
        results = await kb_api_service.faq_retrieve(request.query, channel=request.channel or None)
        return {"code": 200, "message": "success", "data": results}
    except Exception as e:
        logger.error(f"FAQ 检索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
