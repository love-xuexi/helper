"""文件与知识库管理接口

通过知识库平台 API 实现文档上传和知识库管理：
- POST /upload：上传文档到指定知识库（调用 KB API）
- GET  /knowledge-bases：列出所有知识库
- GET  /knowledge-bases/{kb_id}/docs：列出指定知识库下的文档
- POST /kb/retrieve：手动检索知识库（调试用）
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.kb_api_client import KbApiError, kb_api_client

router = APIRouter()

# 支持的文件类型（知识库平台支持多种格式：PDF/Word/Excel/图片等）
ALLOWED_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "txt",
    "md",
    "markdown",
    "csv",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "bmp",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    kb_id: str = Form(..., description="目标知识库 ID"),
    auto_parse: bool = Form(True, description="是否自动解析"),
):
    """上传文档到知识库平台

    请求方式：POST /upload (multipart/form-data)
    表单字段：file, kb_id, auto_parse

    成功响应：
    {
        "code": 200,
        "message": "success",
        "data": {"filename": "xxx.pdf", "size": 12345, "kb_id": "xxx", "results": [...]}
    }
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        # 验证文件扩展名
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式 .{ext}，支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        # 读取文件内容
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）",
            )

        logger.info(f"[File] 上传文件: {file.filename}, size={len(content)}, kb_id={kb_id}")

        # 调用 KB API 上传
        try:
            results = await kb_api_client.upload_document(
                kb_id=kb_id,
                file_content=content,
                filename=file.filename,
                auto_parse=auto_parse,
            )
        except KbApiError as e:
            logger.error(f"[File] KB API 上传失败: {e}")
            raise HTTPException(status_code=502, detail=f"知识库上传失败: {e}")

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "filename": file.filename,
                    "size": len(content),
                    "kb_id": kb_id,
                    "results": results,
                },
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")


@router.get("/knowledge-bases")
async def list_knowledge_bases():
    """列出所有知识库。"""
    try:
        kbs = await kb_api_client.list_knowledge_bases()
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": [{"id": kb.id, "name": kb.name} for kb in kbs],
            },
        )
    except KbApiError as e:
        logger.error(f"列出知识库失败: {e}")
        raise HTTPException(status_code=502, detail=f"获取知识库列表失败: {e}")
    except Exception as e:
        logger.error(f"列出知识库失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {e}")


@router.get("/knowledge-bases/{kb_id}/docs")
async def list_documents(kb_id: str):
    """列出指定知识库下的文档。"""
    try:
        docs = await kb_api_client.list_documents(kb_id)
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": [
                    {
                        "id": doc.id,
                        "kb_id": doc.kb_id,
                        "name": doc.name,
                        "create_date": doc.create_date,
                        "update_date": doc.update_date,
                    }
                    for doc in docs
                ],
            },
        )
    except KbApiError as e:
        logger.error(f"列出文档失败: {e}")
        raise HTTPException(status_code=502, detail=f"获取文档列表失败: {e}")
    except Exception as e:
        logger.error(f"列出文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {e}")


@router.post("/kb/retrieve")
async def retrieve_knowledge(
    query: str = Form(..., description="检索查询"),
    kb_ids: str = Form("", description="知识库 ID 列表（逗号分隔，留空用默认）"),
):
    """手动检索知识库（调试/测试用）。"""
    try:
        kb_id_list = [s.strip() for s in kb_ids.split(",") if s.strip()] if kb_ids else None
        result = await kb_api_client.retrieve(query=query, kb_ids=kb_id_list)
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "total": result.total,
                    "chunks": [
                        {
                            "id": c.chunk_id,
                            "content": c.content,
                            "document": c.document_name,
                            "similarity": c.similarity,
                        }
                        for c in result.chunks
                    ],
                },
            },
        )
    except KbApiError as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=502, detail=f"检索失败: {e}")
    except Exception as e:
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")
