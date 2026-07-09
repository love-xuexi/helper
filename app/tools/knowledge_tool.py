"""知识检索工具 - 调用内网知识库平台接口进行混合检索.

检索（向量 + 关键词混合检索、重排）由知识库平台完成，
本工具只负责调用接口、过滤/截断片段并格式化为带引用编号的上下文。
命中的片段同时写入 retrieval_context，供 API 层随答案返回给前端（引用来源展示、反馈关联）。
"""

from typing import Any

from langchain_core.tools import tool
from loguru import logger

from app.config import config
from app.services import retrieval_context
from app.services.kb_api_service import kb_api_service


@tool(response_format="content_and_artifact")
async def retrieve_knowledge(query: str) -> tuple[str, list[dict[str, Any]]]:
    """从企业知识库中检索相关信息来回答问题.

    当用户的问题涉及专业知识、业务文档、运维手册等需要参考资料的内容时，必须使用此工具。

    Args:
        query: 用户的问题或查询

    Returns:
        tuple[str, list[dict]]: (格式化的上下文文本, 命中的知识片段列表)
    """
    try:
        logger.info(f"知识检索工具被调用: query='{query}'")

        chunks = await kb_api_service.retrieve(query)

        # 相似度过滤 + 截断到最相关的 3-5 个片段
        if config.kb_min_similarity > 0:
            chunks = [c for c in chunks if c.get("similarity", 0.0) >= config.kb_min_similarity]
        chunks = chunks[: config.kb_max_chunks]

        if not chunks:
            logger.warning("未检索到相关知识片段")
            return "知识库中没有找到与该问题相关的信息。", []

        retrieval_context.record(chunks)

        context = format_chunks(chunks)
        logger.info(f"检索到 {len(chunks)} 个相关知识片段")
        return context, chunks

    except Exception as e:
        logger.error(f"知识检索工具调用失败: {e}")
        return f"检索知识时发生错误: {str(e)}", []


def format_chunks(chunks: list[dict[str, Any]]) -> str:
    """把知识片段格式化为带引用编号的上下文文本，供 LLM 引用."""
    formatted_parts = []
    for i, chunk in enumerate(chunks, 1):
        document_name = chunk.get("document_name") or "未知文档"
        similarity = chunk.get("similarity", 0.0)
        formatted_parts.append(
            f"【参考资料 {i}】\n"
            f"来源文档: {document_name}\n"
            f"相关度: {similarity:.2f}\n"
            f"内容:\n{chunk.get('content', '')}\n"
        )
    return "\n".join(formatted_parts)
