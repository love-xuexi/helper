from typing import Any

from langchain_core.documents import Document
from loguru import logger

from app.config import config
from app.services.embedding_input_guard import compress_query_for_embedding, estimate_tokens
from app.services.rerank_service import rerank_service


class RagRetrievalService:
    def __init__(
        self,
        vector_store_manager: Any | None = None,
        reranker: Any | None = None,
        candidate_top_k: int | None = None,
        final_top_k: int | None = None,
        rerank_enabled: bool | None = None,
    ):
        self.vector_store_manager = vector_store_manager
        self.reranker = reranker or rerank_service
        self.candidate_top_k = (
            candidate_top_k if candidate_top_k is not None else config.rag_candidate_top_k
        )
        self.final_top_k = final_top_k if final_top_k is not None else config.rag_top_k
        self.rerank_enabled = (
            rerank_enabled if rerank_enabled is not None else config.rerank_enabled
        )

    def retrieve(self, query: str) -> list[Document]:
        vector_store_manager = self.vector_store_manager or self._get_vector_store_manager()
        candidate_top_k = max(self.candidate_top_k, self.final_top_k)
        embedding_token_budget = max(
            1, config.embedding_max_tokens - config.embedding_token_safety_margin
        )
        safe_query = compress_query_for_embedding(query, max_tokens=embedding_token_budget)
        if safe_query != query:
            logger.warning(
                f"RAG 查询已压缩以适配 Embedding token 限制: "
                f"original_tokens={estimate_tokens(query)}, "
                f"safe_tokens={estimate_tokens(safe_query)}, "
                f"max_tokens={embedding_token_budget}"
            )

        vector_store = vector_store_manager.get_vector_store()
        retriever = vector_store.as_retriever(search_kwargs={"k": candidate_top_k})
        candidate_docs = retriever.invoke(safe_query)

        if not candidate_docs:
            logger.warning("RAG 检索未召回候选文档")
            return []

        logger.info(
            f"RAG 向量召回完成: 候选数={len(candidate_docs)}, candidate_top_k={candidate_top_k}"
        )

        if not self.rerank_enabled:
            return candidate_docs[: self.final_top_k]

        reranked_docs = self.reranker.rerank(safe_query, candidate_docs, self.final_top_k)
        logger.info(f"RAG 重排序完成: 最终返回数={len(reranked_docs)}")
        return reranked_docs

    @staticmethod
    def _get_vector_store_manager() -> Any:
        from app.services.vector_store_manager import vector_store_manager

        return vector_store_manager


rag_retrieval_service = RagRetrievalService()
