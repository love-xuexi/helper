"""
文件上传接口模块

这个文件定义和“知识库文件导入”相关的 HTTP API。
主要有两个接口：
1. POST /upload：上传单个 .txt/.md 文件，保存到 uploads 目录，并自动为这个文件创建向量索引
2. POST /index_directory：批量索引某个目录下已有的 .txt/.md 文件

上传或索引后的最终效果是：
文件内容会被读取、切分、向量化，然后写入 Milvus，供后续向量检索/RAG 使用。

curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@./uploads/runbook.md"
"""

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.services.vector_index_service import vector_index_service
from loguru import logger

router = APIRouter()

# 文件上传后存储的路径
# 这里是相对路径，运行服务时会在当前工作目录下创建/使用 uploads 文件夹
UPLOAD_DIR = Path("./uploads")
# 支持的文件类型
# 当前只允许上传 txt 和 md，因为下游 document_splitter_service 主要支持这两类文本文件
ALLOWED_EXTENSIONS = ["txt", "md"]
# 单个文件支持最大大小
# 超过 10MB 会直接拒绝上传，避免一次性读入内存过大
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    上传文件并自动创建向量索引

    请求方式：
    POST /upload
    Content-Type: multipart/form-data
    表单字段名：file

    成功响应大概长这样：
    {
        "code": 200,
        "message": "success",
        "data": {
            "filename": "runbook.md",
            "file_path": "uploads/runbook.md",
            "size": 12345
        }
    }

    注意：
    这个接口会先把文件保存到本地 uploads 目录，
    然后调用 vector_index_service.index_single_file(...) 创建向量索引。
    即使向量索引创建失败，当前代码仍然会返回上传成功，只会记录错误日志。

    Args:
        file: 上传的文件

    Returns:
        JSONResponse: 上传结果
    """
    try:
        # 1. 验证文件
        # FastAPI 的 UploadFile.filename 可能为空；为空时无法判断后缀和保存路径
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名不能为空")

        # 2. 规范化文件名（去除空格，处理 Windows 上传的文件）
        # 例如 "my file.md" 会变成 "my_file.md"
        # 例如 "a/b.md" 会变成 "a_b.md"，避免路径穿越或非法文件名
        safe_filename = _sanitize_filename(file.filename)

        # 3. 验证文件扩展名
        # 只允许 txt/md，其它格式比如 pdf/docx/csv 会直接返回 400
        file_extension = _get_file_extension(safe_filename)
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式，仅支持: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        # 4. 创建上传目录
        # parents=True 表示父目录不存在也一起创建
        # exist_ok=True 表示目录已存在时不报错
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        # 5. 保存文件
        file_path = UPLOAD_DIR / safe_filename

        # 如果文件已存在，先删除旧文件（实现覆盖更新）
        # 后面 index_single_file(...) 会先删除 Milvus 中同 source 的旧分片，再重新写入新分片
        if file_path.exists():
            logger.info(f"文件已存在，将覆盖: {file_path}")
            file_path.unlink()

        # 读取并保存文件内容
        # 这里会一次性把上传文件读入内存，所以前面设置了 MAX_FILE_SIZE 限制
        content = await file.read()

        # 验证文件大小
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE} 字节）")

        file_path.write_bytes(content)

        logger.info(f"文件上传成功: {file_path}")

        # 5. 自动创建向量索引
        try:
            logger.info(f"开始为上传文件创建向量索引: {file_path}")
            # 这里是真正进入 RAG 知识库构建链路：
            # 1. 读取刚保存的文件
            # 2. 删除这个文件在 Milvus 里的旧分片
            # 3. 重新切分成 Document
            # 4. 调用 embedding 服务生成向量
            # 5. 写入 Milvus
            vector_index_service.index_single_file(str(file_path))
            logger.info(f"向量索引创建成功: {file_path}")
        except Exception as e:
            logger.error(f"向量索引创建失败: {file_path}, 错误: {e}")
            # 注意：即使索引失败，文件上传仍然成功，只是记录错误日志

        # 6. 返回响应
        # 这个响应只表示“文件保存成功”，不严格保证“向量索引一定成功”
        # 因为上面的索引异常被捕获后没有继续抛出
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "filename": safe_filename,
                    "file_path": str(file_path),
                    "size": len(content),
                },
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {e}")


@router.post("/index_directory")
async def index_directory(directory_path: str = None):
    """
    索引指定目录下的所有文件

    请求方式：
    POST /index_directory

    如果不传 directory_path，默认索引 ./uploads 目录。
    这个接口不会上传新文件，只会扫描目录中已经存在的 .txt/.md 文件，
    然后逐个调用 vector_index_service.index_single_file(...)。

    成功响应大概长这样：
    {
        "code": 200,
        "message": "success",
        "data": {
            "success": true,
            "directory_path": "/abs/path/uploads",
            "total_files": 2,
            "success_count": 2,
            "fail_count": 0,
            "duration_ms": 1234,
            "error_message": "",
            "failed_files": {}
        }
    }

    Args:
        directory_path: 目录路径（可选，默认使用 uploads 目录）

    Returns:
        JSONResponse: 索引结果
    """
    try:
        logger.info(f"开始索引目录: {directory_path or 'uploads'}")

        # 执行索引
        # 返回的是 IndexingResult 对象，里面记录目录索引任务的统计信息
        result = vector_index_service.index_directory(directory_path)

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success" if result.success else "partial_success",
                "data": result.to_dict(),
            },
        )

    except Exception as e:
        logger.error(f"索引目录失败: {e}")
        raise HTTPException(status_code=500, detail=f"索引目录失败: {e}")


def _get_file_extension(filename: str) -> str:
    """
    获取文件扩展名

    示例：
    "runbook.md" -> "md"
    "note.TXT" -> "txt"
    "README" -> ""

    Args:
        filename: 文件名

    Returns:
        str: 扩展名（小写，不含点）
    """
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].lower()
    return ""


def _sanitize_filename(filename: str) -> str:
    """
    规范化文件名，去除空格和特殊字符

    目的：
    1. 避免文件名中包含 / 或 \ 导致路径穿越
    2. 避免 Windows/Linux 不兼容的特殊字符
    3. 避免空格导致后续命令、URL 或展示不方便

    示例：
    "my runbook.md" -> "my_runbook.md"
    "../a/b.md" -> ".._a_b.md"

    Args:
        filename: 原始文件名

    Returns:
        str: 规范化后的文件名
    """
    # 去除空格
    sanitized = filename.replace(" ", "_")
    # 去除其他可能导致问题的字符
    for char in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        sanitized = sanitized.replace(char, "_")
    return sanitized
