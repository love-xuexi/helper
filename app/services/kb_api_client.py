"""知识库 API 客户端

封装内网知识库平台的全部接口调用，供 RAG 检索、文档上传、知识库管理等使用。

接口列表（来源：接口测试文档.docx）：
1. 文档检索        POST {retrieval_base}/v1/doc/retrieval/
2. 上传文档        POST {retrieval_base}/v1/doc/retrieval/  (multipart)
3. 列出知识库      GET  {management_base}/api/v1/kbs/listkbs
4. 文档列表查看    GET  {management_base}/api/v1/kbs/{kb_id}/docs
5. 检索特定知识库  POST {management_base}/api/v1/retrieval_by_ids
6. 问答库检索      POST {faq_base}/v1/faq/retrieval

所有接口使用统一的 Bearer Token 鉴权。
"""

from __future__ import annotations

import json as json_module
from dataclasses import dataclass, field
from typing import Any

import httpx
from loguru import logger

from app.config import config


@dataclass
class RetrievedChunk:
    """单条检索结果片段"""

    content: str = ""
    chunk_id: str = ""
    document_id: str = ""
    document_name: str = ""
    dataset_id: str = ""
    similarity: float = 0.0
    term_similarity: float = 0.0
    vector_similarity: float = 0.0
    highlight: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RetrievedChunk":
        """从 API 返回的原始字典构建实例。"""
        return cls(
            content=data.get("content", ""),
            chunk_id=data.get("id", ""),
            document_id=data.get("document_id", ""),
            document_name=data.get("document_keyword", data.get("doc_name", "")),
            dataset_id=data.get("dataset_id", ""),
            similarity=float(data.get("similarity", 0.0)),
            term_similarity=float(data.get("term_similarity", 0.0)),
            vector_similarity=float(data.get("vector_similarity", 0.0)),
            highlight=data.get("highlight", ""),
            raw=data,
        )

    @property
    def content_preview(self) -> str:
        """内容预览（前 200 字符）。"""
        text = self.content.replace("\n", " ").strip()
        return text[:200] + ("..." if len(text) > 200 else "")


@dataclass
class RetrievalResult:
    """检索结果集合"""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    doc_aggs: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RetrievalResult":
        """从 API 返回的 data 字段构建。"""
        chunks_data = data.get("chunks", [])
        chunks = [RetrievedChunk.from_api(c) for c in chunks_data]
        return cls(
            chunks=chunks,
            doc_aggs=data.get("doc_aggs", []),
            total=data.get("total", len(chunks)),
            raw=data,
        )


@dataclass
class KnowledgeBase:
    """知识库信息"""

    id: str = ""
    name: str = ""


@dataclass
class DocumentInfo:
    """文档信息"""

    id: str = ""
    kb_id: str = ""
    name: str = ""
    create_date: str = ""
    update_date: str = ""


class KbApiError(Exception):
    """知识库 API 调用异常"""

    def __init__(self, message: str, status_code: int | None = None, response_text: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class KbApiClient:
    """知识库 API 客户端（异步）"""

    def __init__(self) -> None:
        self.retrieval_base = config.kb_retrieval_base_url.rstrip("/")
        self.management_base = config.kb_management_base_url.rstrip("/")
        self.faq_base = config.kb_faq_base_url.rstrip("/")
        self.timeout = config.kb_timeout_seconds

    @property
    def headers(self) -> dict[str, str]:
        return config.kb_auth_header

    def _handle_response(self, response: httpx.Response, action: str) -> dict[str, Any]:
        """统一处理 API 响应，提取 data 字段。"""
        if response.status_code >= 400:
            raise KbApiError(
                f"{action} 失败: HTTP {response.status_code}",
                status_code=response.status_code,
                response_text=response.text[:500],
            )
        try:
            body = response.json()
        except Exception as e:
            raise KbApiError(
                f"{action} 响应解析失败: {e}",
                status_code=response.status_code,
                response_text=response.text[:500],
            ) from e

        code = body.get("code")
        if code is not None and code != 200:
            raise KbApiError(
                f"{action} 业务错误: code={code}, message={body.get('message', '')}",
                status_code=response.status_code,
                response_text=json_module.dumps(body, ensure_ascii=False)[:500],
            )
        return body

    # ----------------------------------------------------------------
    # 1. 文档检索
    # ----------------------------------------------------------------
    async def retrieve(
        self,
        query: str,
        botcode: str | None = None,
        kb_ids: list[str] | None = None,
        metadata_conditions: list[dict[str, Any]] | None = None,
    ) -> RetrievalResult:
        """文档检索（混合语义检索，由知识库平台完成向量+关键词检索+重排）。

        Args:
            query: 用户查询
            botcode: 机器人编码（留空使用配置默认值）
            kb_ids: 指定知识库 ID 列表（留空使用 botcode 关联的默认库）
            metadata_conditions: 元数据过滤条件

        Returns:
            RetrievalResult: 检索结果集合
        """
        action = "文档检索"
        url = f"{self.retrieval_base}/v1/doc/retrieval/"
        payload: dict[str, Any] = {
            "query": query,
            "botcode": botcode or config.kb_botcode,
        }
        if kb_ids:
            payload["kb_ids"] = kb_ids
        if metadata_conditions:
            payload["extendParams"] = {
                "metadata_condition": {
                    "logic": "and",
                    "conditions": metadata_conditions,
                }
            }

        logger.info(f"[KB API] {action}: query='{query[:50]}', url={url}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url, json=payload, headers={**self.headers, "Content-Type": "application/json"}
                )
            body = self._handle_response(response, action)
            data = body.get("data", {})
            result = RetrievalResult.from_api(data)
            logger.info(f"[KB API] {action}成功: 召回 {len(result.chunks)} 条片段")
            return result
        except KbApiError:
            raise
        except Exception as e:
            raise KbApiError(f"{action}异常: {e}") from e

    # ----------------------------------------------------------------
    # 2. 上传文档
    # ----------------------------------------------------------------
    async def upload_document(
        self,
        kb_id: str,
        file_content: bytes,
        filename: str,
        auto_parse: bool = True,
    ) -> list[dict[str, Any]]:
        """上传文档到指定知识库。

        Args:
            kb_id: 目标知识库 ID
            file_content: 文件二进制内容
            filename: 文件名
            auto_parse: 是否自动解析

        Returns:
            list[dict]: 上传结果列表
        """
        action = "上传文档"
        url = f"{self.retrieval_base}/v1/doc/retrieval/"
        files = {"file": (filename, file_content)}
        data = {"kb_id": kb_id, "auto_parse": str(auto_parse).lower()}

        logger.info(f"[KB API] {action}: kb_id={kb_id}, filename={filename}, url={url}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, files=files, data=data, headers=self.headers)
            body = self._handle_response(response, action)
            result = body.get("data", [])
            logger.info(f"[KB API] {action}成功: {body.get('message', '')}")
            return result if isinstance(result, list) else []
        except KbApiError:
            raise
        except Exception as e:
            raise KbApiError(f"{action}异常: {e}") from e

    # ----------------------------------------------------------------
    # 3. 列出知识库
    # ----------------------------------------------------------------
    async def list_knowledge_bases(self) -> list[KnowledgeBase]:
        """获取所有知识库列表。"""
        action = "列出知识库"
        url = f"{self.management_base}/api/v1/kbs/listkbs"

        logger.info(f"[KB API] {action}: url={url}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
            body = self._handle_response(response, action)
            data = body.get("data", [])
            kbs = [KnowledgeBase(id=item.get("id", ""), name=item.get("name", "")) for item in data]
            logger.info(f"[KB API] {action}成功: 获取 {len(kbs)} 个知识库")
            return kbs
        except KbApiError:
            raise
        except Exception as e:
            raise KbApiError(f"{action}异常: {e}") from e

    # ----------------------------------------------------------------
    # 4. 文档列表查看
    # ----------------------------------------------------------------
    async def list_documents(self, kb_id: str) -> list[DocumentInfo]:
        """获取指定知识库下的文档列表。

        Args:
            kb_id: 知识库 ID

        Returns:
            list[DocumentInfo]: 文档信息列表
        """
        action = "文档列表查看"
        url = f"{self.management_base}/api/v1/kbs/{kb_id}/docs"

        logger.info(f"[KB API] {action}: kb_id={kb_id}, url={url}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
            body = self._handle_response(response, action)
            data = body.get("data", [])
            docs = [
                DocumentInfo(
                    id=item.get("id", ""),
                    kb_id=item.get("kb_id", ""),
                    name=item.get("name", ""),
                    create_date=item.get("create_date", ""),
                    update_date=item.get("update_date", ""),
                )
                for item in data
            ]
            logger.info(f"[KB API] {action}成功: 获取 {len(docs)} 个文档")
            return docs
        except KbApiError:
            raise
        except Exception as e:
            raise KbApiError(f"{action}异常: {e}") from e

    # ----------------------------------------------------------------
    # 5. 检索特定知识库
    # ----------------------------------------------------------------
    async def retrieve_by_ids(
        self,
        query: str,
        kb_ids: list[str],
        doc_ids: list[str] | None = None,
        botcode: str | None = None,
        metadata_conditions: list[dict[str, Any]] | None = None,
    ) -> RetrievalResult:
        """在指定的知识库和文档范围内检索。

        Args:
            query: 用户查询
            kb_ids: 知识库 ID 列表
            doc_ids: 文档 ID 列表（可选）
            botcode: 机器人编码
            metadata_conditions: 元数据过滤条件

        Returns:
            RetrievalResult: 检索结果集合
        """
        action = "检索特定知识库"
        url = f"{self.management_base}/api/v1/retrieval_by_ids"
        payload: dict[str, Any] = {
            "query": query,
            "kb_ids": kb_ids,
            "botcode": botcode or config.kb_botcode,
        }
        if doc_ids:
            payload["doc_ids"] = doc_ids
        if metadata_conditions:
            payload["extendParams"] = {
                "metadata_condition": {
                    "logic": "and",
                    "conditions": metadata_conditions,
                }
            }

        logger.info(f"[KB API] {action}: query='{query[:50]}', kb_ids={kb_ids}, url={url}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url, json=payload, headers={**self.headers, "Content-Type": "application/json"}
                )
            body = self._handle_response(response, action)
            data = body.get("data", {})
            # retrieval_by_ids 的返回结构可能和 doc/retrieval 略有不同，做兼容处理
            if isinstance(data, list):
                chunks = [RetrievedChunk.from_api(c) for c in data]
                result = RetrievalResult(chunks=chunks, total=len(chunks), raw={"chunks": data})
            else:
                result = RetrievalResult.from_api(data)
            logger.info(f"[KB API] {action}成功: 召回 {len(result.chunks)} 条片段")
            return result
        except KbApiError:
            raise
        except Exception as e:
            raise KbApiError(f"{action}异常: {e}") from e

    # ----------------------------------------------------------------
    # 6. 问答库检索（FAQ）
    # ----------------------------------------------------------------
    async def faq_retrieve(
        self,
        query: str,
        botcode: str | None = None,
        channel: str | None = None,
    ) -> dict[str, Any]:
        """FAQ 问答库检索。

        Args:
            query: 用户查询
            botcode: FAQ 机器人编码（留空使用配置默认值）
            channel: 渠道号

        Returns:
            dict: FAQ 检索结果
        """
        action = "FAQ检索"
        url = f"{self.faq_base}/v1/faq/retrieval"
        payload = {
            "query": query,
            "botcode": botcode or config.kb_faq_botcode,
            "channel": channel or config.kb_faq_channel,
        }

        logger.info(f"[KB API] {action}: query='{query[:50]}', url={url}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url, json=payload, headers={**self.headers, "Content-Type": "application/json"}
                )
            body = self._handle_response(response, action)
            data = body.get("data", {})
            logger.info(f"[KB API] {action}成功")
            return data if isinstance(data, dict) else {"raw": data}
        except KbApiError:
            raise
        except Exception as e:
            raise KbApiError(f"{action}异常: {e}") from e

    # ----------------------------------------------------------------
    # 健康检查
    # ----------------------------------------------------------------
    async def health_check(self) -> bool:
        """检查知识库 API 是否可用。"""
        try:
            await self.list_knowledge_bases()
            return True
        except Exception as e:
            logger.warning(f"[KB API] 健康检查失败: {e}")
            return False


# 全局单例
kb_api_client = KbApiClient()
