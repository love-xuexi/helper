"""健康检查接口."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import config

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口.

    检查服务状态和知识库平台配置状态。
    注意：知识库平台为内网服务，这里只检查配置是否就绪，不做网络探测。

    Returns:
        JSONResponse: 健康检查结果
    """
    health_data: dict[str, Any] = {
        "service": config.app_name,
        "version": config.app_version,
        "status": "healthy",
        "kb_platform": {
            "doc_base_url": config.kb_doc_base_url,
            "mgmt_base_url": config.kb_mgmt_base_url,
            "token_configured": bool(config.kb_api_token),
        },
    }

    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "服务运行正常",
            "data": health_data,
        },
    )
