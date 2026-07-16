"""向量存储管理器 - 封装 Milvus VectorStore 操作"""

from langchain_core.documents import Document
from langchain_milvus import Milvus
from loguru import logger

from app.config import config
from app.core.milvus_client import milvus_manager
from app.services.vector_embedding_service import vector_embedding_service

# 统一使用 biz collection
# 这个 collection 可以理解成 Milvus 里的“表”，所有业务文档分片和向量都会写到这里
COLLECTION_NAME = "biz"


class VectorStoreManager:
    """
    向量存储管理器

    这个类负责把 LangChain Document 写入 Milvus，以及从 Milvus 做相似度检索。
    它本身不负责切分文档，也不直接实现 embedding 模型；
    文档切分来自 document_splitter_service，向量化来自 vector_embedding_service。

    写入 Milvus 后，每个文档分片大概长这样：
    {
        "id": "uuid",
        "content": "真正参与检索的文本片段...",
        "vector": [0.01, -0.02, 0.03, ..., 0.04],
        "metadata": {
            "_source": "/abs/path/uploads/a.md",
            "_extension": ".md",
            "_file_name": "a.md",
            "h1": "一级标题",
            "h2": "二级标题"
        }
    }

    用户查询时，similarity_search(...) 会把 query 也转成向量，
    再去 Milvus 里找 vector 最相近的文档分片，最后返回 List[Document]。
    """

    def __init__(self):
        """初始化向量存储管理器"""
        self.vector_store = None
        self.collection_name = COLLECTION_NAME
        # 初始化时就建立 LangChain Milvus VectorStore，后续增删查都复用这个对象
        self._initialize_vector_store()

    def _initialize_vector_store(self):
        """
        初始化 Milvus VectorStore

        这个方法的最终结果是给 self.vector_store 赋值。
        self.vector_store 是 LangChain 封装的 Milvus 对象，后续会用它：
        - add_documents(...)：写入文档分片和向量
        - similarity_search(...)：根据 query 做相似度检索
        """
        try:
            # 必须在 PyMilvus / langchain_milvus 访问 Collection 之前建立连接，
            # 否则会出现 ConnectionNotExistException: should create connection first.
            # （模块导入时就会执行此处，早于 FastAPI lifespan 中的 milvus_manager.connect）
            _ = milvus_manager.connect()

            connection_args = {
                "host": config.milvus_host,
                "port": config.milvus_port,
            }

            # 创建 LangChain Milvus VectorStore
            # 使用 biz collection，字段映射：text_field -> content, vector_field -> vector
            # embedding_function=vector_embedding_service 表示：
            # - 写入文档时，LangChain 会调用 embed_documents(...) 把 Document.page_content 转成向量
            # - 查询检索时，LangChain 会调用 embed_query(...) 把用户 query 转成向量
            self.vector_store = Milvus(
                embedding_function=vector_embedding_service,
                collection_name=self.collection_name,
                connection_args=connection_args,
                auto_id=False,  # 使用自定义 id
                drop_old=False,
                text_field="content",  # 文本内容存储到 content 字段
                vector_field="vector",  # 向量存储到 vector 字段
                primary_field="id",  # 主键字段
                metadata_field="metadata",  # 元数据字段
            )

            logger.info(
                f"VectorStore 初始化成功: {config.milvus_host}:{config.milvus_port}, "
                f"collection: {self.collection_name}"
            )

        except Exception as e:
            logger.error(f"VectorStore 初始化失败: {e}")
            raise

    def add_documents(self, documents: list[Document]) -> list[str]:
        """
        批量添加文档到向量存储（自动批量向量化）

        输入是 document_splitter_service 返回的 List[Document]，例如：
        [
            Document(
                page_content="CPU 过高时先看 top 和日志...",
                metadata={
                    "_source": "/abs/path/runbook.md",
                    "_extension": ".md",
                    "_file_name": "runbook.md",
                    "h1": "故障处理",
                    "h2": "CPU 过高"
                }
            )
        ]

        这个方法会返回写入 Milvus 的 id 列表，例如：
        [
            "b3a8f2d1-7a3a-4e2c-a67a-xxxx",
            "3c9d4e1f-9b2a-42d1-b8cc-yyyy"
        ]

        同时 Milvus 中会新增对应记录：
        {
            "id": "b3a8f2d1-7a3a-4e2c-a67a-xxxx",
            "content": "CPU 过高时先看 top 和日志...",
            "vector": [0.01, -0.02, ...],
            "metadata": {...}
        }

        Args:
            documents: 文档列表

        Returns:
            List[str]: 文档 ID 列表
        """
        try:
            import time
            import uuid

            start_time = time.time()

            # 为每个文档生成唯一 id（因为 auto_id=False）
            # documents 有几个分片，这里就生成几个 uuid
            ids = [str(uuid.uuid4()) for _ in documents]

            # LangChain Milvus 的 add_documents 会自动调用 embedding_function
            # 并进行批量处理，性能更好
            # 内部大致流程：
            # 1. 提取每个 Document.page_content
            # 2. 调用 vector_embedding_service.embed_documents(...) 得到 List[List[float]]
            # 3. 把 id、content、vector、metadata 一起插入 Milvus collection=biz
            result_ids = self.vector_store.add_documents(documents, ids=ids)

            elapsed = time.time() - start_time
            logger.info(
                f"批量添加 {len(documents)} 个文档到 VectorStore 完成, "
                f"耗时: {elapsed:.2f}秒, 平均: {elapsed / len(documents):.2f}秒/个"
            )
            return result_ids
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            raise

    def delete_by_source(self, file_path: str) -> int:
        """
        删除指定文件的所有文档

        这个方法通常在重新索引单个文件前调用。
        因为同一个文件内容可能更新过，所以要先删除 Milvus 里旧的分片，
        再写入新的分片，避免检索时同时命中新旧版本。

        输入：
        "/abs/path/uploads/runbook.md"

        删除条件：
        metadata["_source"] == "/abs/path/uploads/runbook.md"

        返回：
        被删除的分片数量，例如 5；如果首次索引或删除失败，则返回 0。

        Args:
            file_path: 文件路径

        Returns:
            int: 删除的文档数量
        """
        try:
            # 使用 milvus_manager 获取已连接的 collection
            collection = milvus_manager.get_collection()

            # metadata 是 JSON 字段，使用 JSON 路径查询语法
            # _source 是文档的来源文件路径
            # 这会删除所有来自同一个源文件的 chunk
            expr = f'metadata["_source"] == "{file_path}"'

            result = collection.delete(expr)
            deleted_count = result.delete_count if hasattr(result, "delete_count") else 0

            logger.info(f"删除文件旧数据: {file_path}, 删除数量: {deleted_count}")
            return deleted_count

        except Exception as e:
            logger.warning(f"删除旧数据失败 (可能是首次索引): {e}")
            return 0

    def get_vector_store(self) -> Milvus:
        """
        获取 VectorStore 实例

        这个方法只是把底层 LangChain Milvus 对象暴露出去。
        如果其他服务需要直接调用更底层的 Milvus VectorStore 能力，可以通过这里获取。

        Returns:
            Milvus: VectorStore 实例
        """
        return self.vector_store

    def similarity_search(self, query: str, k: int = 3) -> list[Document]:
        """
        相似度搜索

        输入用户问题，例如：
        "CPU 使用率过高怎么排查？"

        内部大致流程：
        1. LangChain 调用 vector_embedding_service.embed_query(query)，把 query 转成向量
        2. Milvus 用 query 向量和 biz collection 里的 vector 字段做相似度比较
        3. 返回最相似的 k 个文档分片

        返回示例：
        [
            Document(
                page_content="CPU 过高时先使用 top 查看进程...",
                metadata={
                    "_source": "/abs/path/runbook.md",
                    "_extension": ".md",
                    "_file_name": "runbook.md",
                    "h1": "故障处理",
                    "h2": "CPU 过高"
                }
            ),
            Document(...)
        ]

        注意：这里返回的是 Document，不直接返回 Milvus 中的 id/vector。
        对 RAG 来说，后续通常只需要 page_content 和 metadata 来拼 prompt。

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            List[Document]: 相关文档列表
        """
        try:
            # similarity_search 会自动触发 query embedding，不需要手动先调用 embed_query
            docs = self.vector_store.similarity_search(query, k=k)
            logger.debug(f"相似度搜索完成: query='{query}', 结果数={len(docs)}")
            return docs
        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            return []


# 全局单例
vector_store_manager = VectorStoreManager()
