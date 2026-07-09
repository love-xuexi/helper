"""健康检查接口"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import config
from app.services.feedback_service import feedback_service
from app.services.kb_api_client import kb_api_client

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查接口

    检查项：
    - 服务基本状态
    - 知识库 API 连通性
    - 反馈数据库可用性
    """
    import asyncio

    health_data: dict[str, Any] = {
        "service": config.app_name,
        "version": config.app_version,
        "status": "healthy",
    }

    # 检查知识库 API
    try:
        kb_healthy = await kb_api_client.health_check()
        health_data["kb_api"] = {
            "status": "connected" if kb_healthy else "disconnected",
            "message": "知识库 API 连接正常" if kb_healthy else "知识库 API 不可达",
        }
    except Exception as e:
        logger.warning(f"知识库 API 健康检查失败: {e}")
        health_data["kb_api"] = {"status": "error", "message": f"知识库 API 检查失败: {str(e)}"}

    # 检查反馈数据库
    try:
        stats = feedback_service.get_stats()
        health_data["feedback_db"] = {
            "status": "ok" if stats is not None else "error",
            "message": f"反馈数据库正常（共 {stats['total']} 条记录）",
        }
    except Exception as e:
        logger.warning(f"反馈数据库健康检查失败: {e}")
        health_data["feedback_db"] = {"status": "error", "message": f"反馈数据库检查失败: {str(e)}"}

    # 判断整体健康状态（知识库 API 不可用不阻断服务，仅降级）
    overall_status = "healthy"
    status_code = 200

    if health_data["feedback_db"]["status"] != "ok":
        overall_status = "degraded"
        health_data["error"] = "反馈数据库不可用"

    if health_data["kb_api"]["status"] != "connected":
        overall_status = "degraded"
        health_data["error"] = "知识库 API 不可达，RAG 检索将不可用"

    health_data["status"] = overall_status

    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "message": "服务运行正常" if overall_status == "healthy" else "服务降级运行",
            "data": health_data,
        },
    )
