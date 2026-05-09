"""向量检索服务模块"""

from typing import Any, Dict, List

from loguru import logger
from pymilvus import Collection

from app.core.milvus_client import milvus_manager
from app.services.vector_embedding_service import vector_embedding_service


class SearchResult:
    """
    搜索结果类

    这个类用于包装 Milvus 返回的一条命中文档。
    search_similar_documents(...) 最终返回的是 List[SearchResult]。

    单条结果调用 to_dict() 后大概长这样：
    {
        "id": "b3a8f2d1-7a3a-4e2c-a67a-xxxx",
        "content": "CPU 过高时先使用 top 查看进程...",
        "score": 0.2345,
        "metadata": {
            "_source": "/abs/path/runbook.md",
            "_extension": ".md",
            "_file_name": "runbook.md",
            "h1": "故障处理",
            "h2": "CPU 过高"
        }
    }

    注意：这里的 score 是 L2 距离，不是百分制分数。
    在 L2 距离下，score 越小表示 query 向量和文档向量越接近，也就是语义越相似。
    """

    def __init__(
        self,
        id: str,
        content: str,
        score: float,
        metadata: Dict[str, Any],
    ):
        self.id = id
        self.content = content
        self.score = score
        self.metadata = metadata

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        常用于 API 返回 JSON，因为 SearchResult 是 Python 对象，
        直接返回给前端不方便，所以会转成 dict。
        """
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
        }


class VectorSearchService:
    """
    向量检索服务 - 负责从 Milvus 中搜索相似向量

    这个服务是 RAG 检索链路中的“召回”部分：
    1. 用户输入自然语言 query
    2. 使用 vector_embedding_service.embed_query(...) 把 query 转成向量
    3. 在 Milvus 的 vector 字段中搜索距离最近的 top_k 个文档分片
    4. 返回这些分片的 id、content、score、metadata

    它和 vector_store_manager.similarity_search(...) 的区别是：
    - 这里直接使用 PyMilvus Collection.search(...)
    - 返回的是自定义 SearchResult，里面包含 id 和 distance score
    - vector_store_manager.similarity_search(...) 使用 LangChain 封装，通常返回 Document
    """

    def __init__(self):
        """初始化向量检索服务"""
        logger.info("向量检索服务初始化完成")

    def search_similar_documents(self, query: str, top_k: int = 5) -> List[SearchResult]:
        """
        搜索相似文档

        输入示例：
        query = "服务 CPU 飙高怎么办？"
        top_k = 3

        最终返回示例：
        [
            SearchResult(
                id="uuid-1",
                content="CPU 过高时先使用 top 查看进程...",
                score=0.2345,
                metadata={
                    "_source": "/abs/path/runbook.md",
                    "_extension": ".md",
                    "_file_name": "runbook.md",
                    "h1": "故障处理",
                    "h2": "CPU 过高"
                }
            ),
            SearchResult(...)
        ]

        如果再调用每个结果的 to_dict()，就会变成可以 JSON 序列化的字典列表。

        Args:
            query: 查询文本
            top_k: 返回最相似的K个结果

        Returns:
            List[SearchResult]: 搜索结果列表

        Raises:
            RuntimeError: 搜索失败时抛出
        """
        try:
            logger.info(f"开始搜索相似文档, 查询: {query}, topK: {top_k}")

            # 1. 将查询文本向量化
            # 例如 "服务 CPU 飙高怎么办？" 会变成一个 1024 维 float 向量：
            # [0.02, -0.01, 0.08, ..., -0.03]
            query_vector = vector_embedding_service.embed_query(query)
            logger.debug(f"查询向量生成成功, 维度: {len(query_vector)}")

            # 2. 获取 collection
            # collection 对应 Milvus 里的 biz collection，里面存着文档分片：
            # id / content / vector / metadata
            collection: Collection = milvus_manager.get_collection()

            # 3. 构建搜索参数
            # metric_type="L2" 表示用欧氏距离比较向量相似度
            # nprobe 是 Milvus IVF 类索引的搜索范围参数，越大召回可能越好，但查询越慢
            search_params = {
                "metric_type": "L2",  # 欧氏距离
                "params": {"nprobe": 10},
            }

            # 4. 执行搜索
            # data=[query_vector]：Milvus 支持批量搜索，所以这里传的是“查询向量列表”
            # anns_field="vector"：在 Milvus 的 vector 字段上做近似最近邻搜索
            # limit=top_k：只返回最相近的 top_k 条
            # output_fields：除了距离分数外，还额外取回 id/content/metadata 字段
            results = collection.search(
                data=[query_vector],
                anns_field="vector",
                param=search_params,
                limit=top_k,
                output_fields=["id", "content", "metadata"],
            )

            # 5. 解析搜索结果
            # results 的结构是二维的：
            # - 外层对应每个 query 向量；这里因为只搜一个 query，所以通常只有一组 hits
            # - 内层 hits 是这个 query 命中的 top_k 个文档分片
            search_results = []
            for hits in results:
                for hit in hits:
                    # hit.distance 就是当前 query 向量和文档向量的 L2 距离
                    # hit.entity.get(...) 可以取回 output_fields 中声明的字段
                    result = SearchResult(
                        id=hit.entity.get("id"),
                        content=hit.entity.get("content"),
                        score=hit.distance,  # L2 距离，越小越相似
                        metadata=hit.entity.get("metadata", {}),
                    )
                    search_results.append(result)

            logger.info(f"搜索完成, 找到 {len(search_results)} 个相似文档")
            return search_results

        except Exception as e:
            logger.error(f"搜索相似文档失败: {e}")
            raise RuntimeError(f"搜索失败: {e}") from e


# 全局单例
vector_search_service = VectorSearchService()
