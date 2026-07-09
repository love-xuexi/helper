"""知识检索工具 - 通过知识库 API 检索相关信息

此工具封装了知识库平台的检索接口，可作为 LangChain Tool 使用。
当前 RAG 服务采用直接检索流程（非 Agent 工具调用），此工具保留供未来扩展使用。
"""

from typing import Any, List, Tuple

from langchain_core.tools import tool
from loguru import logger

from app.services.kb_api_client import kb_api_client


@tool
async def retrieve_knowledge(query: str) -> Tuple[str, List[dict[str, Any]]]:
    """从知识库中检索相关信息来回答问题。

    当用户的问题涉及专业知识、文档内容或需要参考资料时，使用此工具。
    检索由知识库平台完成（混合语义检索 + 重排序），返回最相关的片段。

    Args:
        query: 用户的问题或查询

    Returns:
        Tuple[str, List[dict]]: (格式化的上下文文本, 引用来源列表)
    """
    try:
        logger.info(f"知识检索工具被调用: query='{query}'")
        result = await kb_api_client.retrieve(query=query)
        chunks = result.chunks

        if not chunks:
            logger.warning("未检索到相关文档")
            return "没有找到相关信息。", []

        context, citations = _format_chunks(chunks)
        logger.info(f"检索到 {len(chunks)} 个相关文档")
        return context, citations

    except Exception as e:
        logger.error(f"知识检索工具调用失败: {e}")
        return f"检索知识时发生错误: {str(e)}", []


def _format_chunks(chunks: List[Any]) -> Tuple[str, List[dict[str, Any]]]:
    """格式化检索结果为上下文文本 + 引用列表。"""
    context_parts: list[str] = []
    citations: list[dict[str, Any]] = []

    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"【参考资料 {i}】\n"
            f"来源文档：{chunk.document_name or '未知'}\n"
            f"片段ID：{chunk.chunk_id}\n"
            f"相似度：{chunk.similarity:.4f}\n"
            f"内容：\n{chunk.content}"
        )
        citations.append(
            {
                "index": i,
                "id": chunk.chunk_id,
                "document": chunk.document_name,
                "similarity": round(chunk.similarity, 4),
                "content_preview": chunk.content_preview,
            }
        )

    return "\n\n".join(context_parts), citations
