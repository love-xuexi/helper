"""向量索引服务模块"""

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.services.document_splitter_service import document_splitter_service
from app.services.vector_store_manager import vector_store_manager


class IndexingResult:
    """
    索引结果类

    这个类只记录“索引任务执行得怎么样”，不是最终写入 Milvus 的向量数据本身。
    index_directory(...) 最终会返回这个对象，调用 to_dict() 后大概长这样：
    {
        "success": True,
        "directory_path": "/abs/path/uploads",
        "total_files": 2,
        "success_count": 2,
        "fail_count": 0,
        "duration_ms": 1234,
        "error_message": "",
        "failed_files": {}
    }
    """

    def __init__(self):
        self.success = False
        self.directory_path = ""
        self.total_files = 0
        self.success_count = 0
        self.fail_count = 0
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self.error_message = ""
        self.failed_files: dict[str, str] = {}

    def increment_success_count(self):
        """增加成功计数"""
        self.success_count += 1

    def increment_fail_count(self):
        """增加失败计数"""
        self.fail_count += 1

    def add_failed_file(self, file_path: str, error: str):
        """添加失败文件"""
        self.failed_files[file_path] = error

    def get_duration_ms(self) -> int:
        """获取耗时（毫秒）"""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() * 1000)
        return 0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "directory_path": self.directory_path,
            "total_files": self.total_files,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "duration_ms": self.get_duration_ms(),
            "error_message": self.error_message,
            "failed_files": self.failed_files,
        }


class VectorIndexService:
    """向量索引服务 - 负责读取文件、生成向量、存储到 Milvus"""

    def __init__(self):
        """初始化向量索引服务"""
        self.upload_path = "./uploads"
        logger.info("向量索引服务初始化完成")

    def index_directory(self, directory_path: str | None = None) -> IndexingResult:
        """
        索引指定目录下的所有文件

        Args:
            directory_path: 目录路径（可选，默认使用配置的上传目录）

        Returns:
            IndexingResult: 索引结果
        """
        result = IndexingResult()
        result.start_time = datetime.now()

        try:
            # 使用指定目录或默认上传目录
            target_path = directory_path if directory_path else self.upload_path
            dir_path = Path(target_path).resolve()

            if not dir_path.exists() or not dir_path.is_dir():
                raise ValueError(f"目录不存在或不是有效目录: {target_path}")

            result.directory_path = str(dir_path)

            # 获取所有支持的文件：当前只会处理目录第一层的 .txt 和 .md 文件，不会递归子目录
            files = list(dir_path.glob("*.txt")) + list(dir_path.glob("*.md"))

            if not files:
                logger.warning(f"目录中没有找到支持的文件: {target_path}")
                result.total_files = 0
                result.success = True
                result.end_time = datetime.now()
                return result

            result.total_files = len(files)
            logger.info(f"开始索引目录: {target_path}, 找到 {len(files)} 个文件")

            # 遍历并索引每个文件
            # index_single_file(...) 负责真正写入 Milvus；这里负责统计成功/失败数量
            for file_path in files:
                try:
                    self.index_single_file(str(file_path))
                    result.increment_success_count()
                    logger.info(f"✓ 文件索引成功: {file_path.name}")
                except Exception as e:
                    result.increment_fail_count()
                    result.add_failed_file(str(file_path), str(e))
                    logger.error(f"✗ 文件索引失败: {file_path.name}, 错误: {e}")

            # 只要有任意一个文件失败，整个目录索引任务就算失败
            # 但已经成功的文件不会回滚，它们的分片已经写入 Milvus
            result.success = result.fail_count == 0
            result.end_time = datetime.now()

            logger.info(
                f"目录索引完成: 总数={result.total_files}, "
                f"成功={result.success_count}, 失败={result.fail_count}"
            )

            return result

        except Exception as e:
            logger.error(f"索引目录失败: {e}")
            result.success = False
            result.error_message = str(e)
            result.end_time = datetime.now()
            return result

    def index_single_file(self, file_path: str):
        """
        索引单个文件 (使用新的 LangChain 分割器)

        这个方法没有 return 值；它的“最终结果”是副作用：
        1. 先删除 Milvus 中 metadata["_source"] 等于当前文件路径的旧分片
        2. 再把当前文件重新切成多个 LangChain Document
        3. 调用 vector_store_manager.add_documents(...) 写入 Milvus

        写入 Milvus 的每个分片大概长这样：
        Document(
            page_content="文件中的一段文本内容...",
            metadata={
                "_source": "/abs/path/uploads/example.md",
                "_extension": ".md",
                "_file_name": "example.md",
                "h1": "Markdown 一级标题",
                "h2": "Markdown 二级标题"
            }
        )

        vector_store_manager.add_documents(...) 会进一步为每个 Document 生成 uuid，
        并调用 embedding 服务把 page_content 转成向量，最终写进 Milvus 的 biz collection：
        {
            "id": "uuid",
            "content": "文件中的一段文本内容...",
            "vector": [0.01, -0.03, ...],
            "metadata": {...上面的 metadata...}
        }

        Args:
            file_path: 文件路径

        Raises:
            ValueError: 文件不存在时抛出
            RuntimeError: 索引失败时抛出
        """
        path = Path(file_path).resolve()

        if not path.exists() or not path.is_file():
            raise ValueError(f"文件不存在: {file_path}")

        logger.info(f"开始索引文件: {path}")

        try:
            # 1. 读取原始文件内容，此时 content 还是一个完整字符串
            content = path.read_text(encoding="utf-8")
            logger.info(f"读取文件: {path}, 内容长度: {len(content)} 字符")

            # 2. 删除该文件的旧数据（如果存在）
            # normalized_path 会作为分片 metadata["_source"]，删除时也用这个路径精确匹配
            # 这样重复索引同一个文件时，不会在 Milvus 里留下旧版本的重复分片
            normalized_path = path.as_posix()
            vector_store_manager.delete_by_source(normalized_path)

            # 3. 使用文档分割器把完整文件拆成多个 Document 分片
            # .md 文件会优先按 Markdown 标题分割，再按长度二次分割，并带上 h1/h2 等标题元数据
            # .txt 文件会直接按字符长度分割
            documents = document_splitter_service.split_document(content, normalized_path)
            logger.info(f"文档分割完成: {file_path} -> {len(documents)} 个分片")

            # 4. 添加文档到向量存储
            # 这里会触发 embedding：把每个 Document.page_content 转为向量
            # 最终写入 Milvus collection=biz，字段包括 id/content/vector/metadata
            if documents:
                vector_store_manager.add_documents(documents)
                logger.info(f"文件索引完成: {file_path}, 共 {len(documents)} 个分片")
            else:
                logger.warning(f"文件内容为空或无法分割: {file_path}")

        except Exception as e:
            logger.error(f"索引文件失败: {file_path}, 错误: {e}")
            raise RuntimeError(f"索引文件失败: {e}") from e


# 全局单例
vector_index_service = VectorIndexService()
