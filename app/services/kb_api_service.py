"""知识库平台 API 客户端.

知识库的建立、解析、向量化、混合检索、重排均由内网知识库平台完成，
本服务只负责调用其 HTTP 接口并把结果归一化成统一的 chunk 结构：

- POST {doc_base}/v1/doc/retrieval/          文档检索（全库混合检索 + 重排）
- POST {doc_base}/v1/doc/retrieval/ (form)   上传文档（多源异构解析由平台完成）
- GET  {mgmt_base}/api/v1/kbs/listkbs        知识库列表
- GET  {mgmt_base}/api/v1/kbs/{kb_id}/docs   知识库文档列表
- POST {mgmt_base}/api/v1/retrieval_by_ids   检索特定知识库/文档
- POST {faq_base}/v1/faq/retrieval           问答库（FAQ）检索

注意：以上均为内网接口，本机无法直接访问，调用失败时统一返回空结果并记录日志。
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.config import Settings, config


class KnowledgeChunk(dict):
    """归一化后的知识片段（保持 dict 行为，方便 JSON 序列化）.

    字段：
    - id: 片段 ID（反馈入库、引用溯源的关键）
    - content: 片段内容
    - document_id / document_name: 来源文档
    - dataset_id: 所属知识库
    - similarity: 综合相似度
    """


class KbApiService:
    """内网知识库平台 API 封装."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or config

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.kb_api_token}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=self.settings.kb_timeout_seconds,
        )

    @staticmethod
    def _normalize_chunks(chunks: list[dict[str, Any]]) -> list[KnowledgeChunk]:
        normalized: list[KnowledgeChunk] = []
        for chunk in chunks or []:
            normalized.append(
                KnowledgeChunk(
                    id=chunk.get("id", ""),
                    content=chunk.get("content", ""),
                    document_id=chunk.get("document_id", ""),
                    document_name=chunk.get("document_keyword", ""),
                    dataset_id=chunk.get("dataset_id", ""),
                    similarity=chunk.get("similarity", 0.0),
                )
            )
        return normalized

    async def retrieve(
        self,
        query: str,
        extend_params: dict[str, Any] | None = None,
    ) -> list[KnowledgeChunk]:
        """全库文档检索（平台内部完成混合检索 + 重排）."""
        payload: dict[str, Any] = {
            "query": query,
            "botcode": self.settings.kb_botcode,
        }
        if extend_params:
            payload["extendParams"] = extend_params
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.settings.kb_doc_base_url}/v1/doc/retrieval/",
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                chunks = (body.get("data") or {}).get("chunks", [])
                result = self._normalize_chunks(chunks)
                logger.info(f"知识库检索成功: query='{query}', 返回 {len(result)} 个片段")
                return result
        except Exception as e:
            logger.error(f"知识库检索失败: query='{query}', 错误: {e}")
            return []

    async def retrieve_by_ids(
        self,
        query: str,
        kb_ids: list[str],
        doc_ids: list[str] | None = None,
        extend_params: dict[str, Any] | None = None,
    ) -> list[KnowledgeChunk]:
        """检索特定知识库/文档."""
        payload: dict[str, Any] = {
            "query": query,
            "kb_ids": kb_ids,
            "botcode": self.settings.kb_botcode,
        }
        if doc_ids:
            payload["doc_ids"] = doc_ids
        if extend_params:
            payload["extendParams"] = extend_params
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.settings.kb_mgmt_base_url}/api/v1/retrieval_by_ids",
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                chunks = (
                    (body.get("data") or {}).get("chunks", []) if isinstance(body, dict) else []
                )
                result = self._normalize_chunks(chunks)
                logger.info(f"指定知识库检索成功: query='{query}', 返回 {len(result)} 个片段")
                return result
        except Exception as e:
            logger.error(f"指定知识库检索失败: query='{query}', 错误: {e}")
            return []

    async def faq_retrieve(self, query: str, channel: str | None = None) -> list[dict[str, Any]]:
        """问答库（FAQ）检索."""
        payload: dict[str, Any] = {
            "query": query,
            "botcode": self.settings.kb_botcode,
            "channel": channel or self.settings.kb_faq_channel,
        }
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.settings.kb_faq_base_url}/v1/faq/retrieval",
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
                data = body.get("data") if isinstance(body, dict) else None
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"FAQ 检索失败: query='{query}', 错误: {e}")
            return []

    async def list_kbs(self) -> list[dict[str, Any]]:
        """获取知识库列表."""
        try:
            async with self._client() as client:
                response = await client.get(f"{self.settings.kb_mgmt_base_url}/api/v1/kbs/listkbs")
                response.raise_for_status()
                body = response.json()
                return body.get("data") or []
        except Exception as e:
            logger.error(f"获取知识库列表失败: {e}")
            return []

    async def list_docs(self, kb_id: str) -> list[dict[str, Any]]:
        """获取指定知识库的文档列表."""
        try:
            async with self._client() as client:
                response = await client.get(
                    f"{self.settings.kb_mgmt_base_url}/api/v1/kbs/{kb_id}/docs"
                )
                response.raise_for_status()
                body = response.json()
                return body.get("data") or []
        except Exception as e:
            logger.error(f"获取文档列表失败: kb_id={kb_id}, 错误: {e}")
            return []

    async def upload_document(
        self,
        kb_id: str,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        auto_parse: bool = True,
    ) -> dict[str, Any]:
        """上传文档到知识库（PDF/Word/Excel/图片等格式的解析由平台完成）."""
        files = {"file": (filename, content, content_type or "application/octet-stream")}
        data = {"kb_id": kb_id, "auto_parse": "true" if auto_parse else "false"}
        async with self._client() as client:
            response = await client.post(
                f"{self.settings.kb_doc_base_url}/v1/doc/retrieval/",
                data=data,
                files=files,
            )
            response.raise_for_status()
            body = response.json()
            logger.info(f"文档上传成功: {filename} -> kb {kb_id}")
            return body


kb_api_service = KbApiService()
