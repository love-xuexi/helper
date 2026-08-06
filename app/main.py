"""FastAPI 应用入口

主应用程序，配置路由、中间件、静态文件等
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api import (
    admin,  # 管理后台聚合接口（Bug + 反馈时间线等）
    aiops,  # AIOps 模块（预留，需 MCP 服务支持）
    bug,
    chat,
    feedback,
    file,
    health,
)
from app.config import config
from app.core.session_persistence import session_persistence_manager
from app.services.bug_service import bug_service
from app.services.feedback_service import feedback_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("=" * 60)
    logger.info(f"[启动] {config.app_name} v{config.app_version} 启动中...")
    logger.info(f"[环境] {'开发' if config.debug else '生产'}")
    logger.info(f"[服务地址] http://{config.host}:{config.port}")
    logger.info(f"[API 文档] http://{config.host}:{config.port}/docs")

    # 初始化会话持久化
    logger.info("[SessionPersistence] 正在初始化会话持久化...")
    await session_persistence_manager.initialize_async()
    chat.rag_agent_service.configure_checkpointer(session_persistence_manager.checkpointer)
    aiops.aiops_service.configure_checkpointer(session_persistence_manager.checkpointer)
    logger.info("[SessionPersistence] 会话持久化初始化完成")

    # 初始化反馈数据库
    logger.info("[Feedback] 正在初始化反馈数据库...")
    feedback_service.initialize()
    logger.info("[Feedback] 反馈数据库初始化完成")

    # 初始化 Bug 数据库
    logger.info("[Bug] 正在初始化 Bug 数据库...")
    bug_service.initialize()
    logger.info("[Bug] Bug 数据库初始化完成")

    logger.info("=" * 60)

    yield

    # 关闭时执行
    logger.info("[SessionPersistence] 正在关闭会话持久化...")
    await session_persistence_manager.close_async()
    logger.info(f"[关闭] {config.app_name} 已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于知识库 API 的知识中台提效助手，支持 RAG 检索、引用标注、反馈评价",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, prefix="/api", tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(file.router, prefix="/api", tags=["文件与知识库管理"])
app.include_router(feedback.router, prefix="/api", tags=["反馈评价"])
app.include_router(bug.router, prefix="/api", tags=["Bug上报"])
app.include_router(admin.router, prefix="/api", tags=["管理后台"])
app.include_router(aiops.router, prefix="/api", tags=["AIOps智能运维"])

# 挂载静态文件
static_dir = "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 挂载 Bug 附件上传目录
uploads_dir = config.bug_upload_dir
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


@app.get("/")
async def root():
    """返回首页"""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs",
    }


@app.get("/admin")
async def admin_page():
    """返回管理后台页面"""
    admin_path = os.path.join(static_dir, "admin.html")
    if os.path.exists(admin_path):
        return FileResponse(admin_path)
    raise HTTPException(status_code=404, detail="管理后台页面不存在")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info",
    )
