"""文件上传接口（透传内网知识库平台）.

文件的解析（PDF/Word/Excel/图片等多源异构格式）、切分、向量化
全部由知识库平台完成，本接口只负责把文件转发到平台的上传接口。

- POST /upload：上传文件到知识库（可通过 kb_id 表单字段指定目标知识库，
  留空则使用配置的默认知识库或知识库列表第一个）

curl -X POST "http://localhost:9900/api/upload" \
  -F "file=@./runbook.pdf" \
  -F "kb_id=kb-123"
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import config
from app.services.kb_api_service import kb_api_service

router = APIRouter()

# 知识库平台支持多源异构解析，允许常见文档/表格/图片格式
ALLOWED_EXTENSIONS = [
    "txt",
    "md",
    "markdown",
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "csv",
    "ppt",
    "pptx",
    "png",
    "jpg",
    "jpeg",
]
# 单个文件支持最大大小（一次性读入内存转发，限制 50MB）
MAX_FILE_SIZE = 50 * 1024 * 1024


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), kb_id: str = Form("")):
    """上传文件到知识库平台.

    成功响应示例： {     "code": 200,     "message": "success",     "data": {         "filename":
    "runbook.pdf",         "kb_id": "kb-123",         "size": 12345     } }
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        file_extension = _get_file_extension(file.filename)
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE} 字节）")

        target_kb_id = kb_id or config.kb_upload_kb_id
        if not target_kb_id:
            # 未指定目标知识库时，取知识库列表第一个
            kbs = await kb_api_service.list_kbs()
            if not kbs:
                raise HTTPException(status_code=502, detail="无法获取知识库列表，请指定 kb_id 或检查知识库平台配置")
            target_kb_id = kbs[0].get("id", "")

        await kb_api_service.upload_document(
            kb_id=target_kb_id,
            filename=file.filename,
            content=content,
            content_type=file.content_type,
        )

        logger.info(f"文件已转发到知识库平台: {file.filename} -> kb {target_kb_id}")
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "filename": file.filename,
                    "kb_id": target_kb_id,
                    "size": len(content),
                },
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=502, detail=f"文件上传到知识库平台失败: {e}") from e


def _get_file_extension(filename: str) -> str:
    """获取文件扩展名（小写，不含点）."""
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].lower()
    return ""
