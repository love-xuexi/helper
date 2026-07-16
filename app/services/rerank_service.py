import re
from collections.abc import Callable
from enum import Enum
from typing import Any, Union

import httpx
from langchain_core.documents import Document
from loguru import logger

from app.config import config

RerankResponse = Union[dict[str, Any], list[dict[str, Any]]]
PostJson = Callable[[str, dict[str, str], dict[str, Any], float], RerankResponse]


class RerankProvider(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    NVIDIA = "nvidia"


class LocalKeywordReranker:
    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        if not documents or top_k <= 0:
            return []

        query_terms = self._tokenize(query)
        scored_docs = []
        for index, document in enumerate(documents):
            content_terms = self._tokenize(document.page_content)
            overlap = len(query_terms & content_terms)
            substring_bonus = sum(
                1 for term in query_terms if term and term in document.page_content
            )
            score = overlap * 2 + substring_bonus
            scored_docs.append((score, -index, document))

        scored_docs.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [document for _, _, document in scored_docs[:top_k]]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        normalized = text.lower()
        ascii_terms = set(re.findall(r"[a-z0-9_\-]+", normalized))
        chinese_terms = set(re.findall(r"[\u4e00-\u9fff]{2,}", normalized))
        short_chinese_terms = set(re.findall(r"[\u4e00-\u9fff]", normalized))
        return ascii_terms | chinese_terms | short_chinese_terms


class RerankService:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: RerankProvider | str | None = None,
        timeout_seconds: float | None = None,
        post_json: PostJson | None = None,
        fallback_reranker: LocalKeywordReranker | None = None,
    ):
        self.api_key = api_key if api_key is not None else config.effective_rerank_api_key
        self.base_url = base_url if base_url is not None else config.effective_rerank_base_url
        self.model = model or config.rerank_model
        provider_value = provider if provider is not None else config.effective_rerank_provider
        self.provider = RerankProvider(provider_value)
        self.timeout_seconds = timeout_seconds or config.rerank_timeout_seconds
        self.post_json = post_json or self._post_json
        self.fallback_reranker = fallback_reranker or LocalKeywordReranker()

    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        if not documents or top_k <= 0:
            return []

        if not self.api_key or not self.base_url:
            logger.warning("Rerank 配置缺失，使用本地关键词重排序降级")
            return self.fallback_reranker.rerank(query, documents, top_k)

        try:
            payload = self._build_payload(query, documents, top_k)
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            response_json = self.post_json(
                self._ranking_url(), headers, payload, self.timeout_seconds
            )
            ranked_items = self._extract_ranked_items(response_json)
            reranked = self._map_ranked_items_to_documents(ranked_items, documents)

            if not reranked:
                logger.warning("Rerank 响应为空，使用本地关键词重排序降级")
                return self.fallback_reranker.rerank(query, documents, top_k)

            logger.info(f"Rerank 完成: 候选数={len(documents)}, 返回数={min(len(reranked), top_k)}")
            return reranked[:top_k]
        except Exception as e:
            logger.warning(f"Rerank 失败，使用本地关键词重排序降级: {e}")
            return self.fallback_reranker.rerank(query, documents, top_k)

    def _ranking_url(self) -> str:
        if self.provider == RerankProvider.NVIDIA:
            return self._nvidia_ranking_url()
        return self._openai_compatible_ranking_url()

    def _openai_compatible_ranking_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if (
            base_url.endswith("/ranking")
            or base_url.endswith("/reranking")
            or base_url.endswith("/rerank")
        ):
            return base_url
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return f"{base_url}/rerank"

    def _nvidia_ranking_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/ranking") or base_url.endswith("/reranking"):
            return base_url
        if "/retrieval/" in base_url:
            return base_url

        if "integrate.api.nvidia.com" in base_url or "ai.api.nvidia.com" in base_url:
            hosted_base_url = base_url.replace("integrate.api.nvidia.com", "ai.api.nvidia.com")
            if hosted_base_url.endswith("/v1"):
                hosted_base_url = hosted_base_url[:-3]
            return f"{hosted_base_url}/v1/retrieval/{self._model_path_name()}/reranking"

        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return f"{base_url}/ranking"

    def _model_path_name(self) -> str:
        return self.model.replace(".", "_")

    def _build_payload(self, query: str, documents: list[Document], top_k: int) -> dict[str, Any]:
        if self.provider == RerankProvider.OPENAI_COMPATIBLE:
            return {
                "model": self.model,
                "query": query,
                "documents": [document.page_content for document in documents],
                "top_n": top_k,
            }

        return {
            "model": self.model,
            "query": {"text": query},
            "passages": [{"text": document.page_content} for document in documents],
            "truncate": "END",
        }

    @staticmethod
    def _post_json(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> RerankResponse:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _extract_ranked_items(response_json: RerankResponse) -> list[dict[str, Any]]:
        if isinstance(response_json, list):
            return [item for item in response_json if isinstance(item, dict)]

        for key in ("rankings", "results", "data"):
            value = response_json.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return []

    @staticmethod
    def _map_ranked_items_to_documents(
        ranked_items: list[dict[str, Any]],
        documents: list[Document],
    ) -> list[Document]:
        mapped_items: list[tuple[float, int, Document]] = []
        used_indexes = set()

        for order, item in enumerate(ranked_items):
            index = RerankService._extract_index(item)
            if index is None or index < 0 or index >= len(documents) or index in used_indexes:
                continue
            score = RerankService._extract_score(item)
            mapped_items.append((score, -order, documents[index]))
            used_indexes.add(index)

        mapped_items.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [document for _, _, document in mapped_items]

    @staticmethod
    def _extract_index(item: dict[str, Any]) -> int | None:
        for key in ("index", "passage_index", "document_index"):
            value = item.get(key)
            if isinstance(value, int):
                return value
        return None

    @staticmethod
    def _extract_score(item: dict[str, Any]) -> float:
        for key in ("logit", "score", "relevance_score"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0


class NvidiaRerankService(RerankService):
    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("provider", RerankProvider.NVIDIA)
        super().__init__(*args, **kwargs)


rerank_service = RerankService()
