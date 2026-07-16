"""RAG Agent 服务 - 基于知识库 API 的检索增强问答

架构简化说明：
  原 helper 项目自带 Milvus 向量库 + Embedding + Rerank 完整 RAG 链路。
  现知识库平台已提供统一的检索接口（混合语义检索 + 重排），
  因此本服务改为直接调用 KB API 完成检索，再由 LLM 基于检索结果生成带引用的答案。

核心流程：
  1. 用户提问 → 调用 KB API 检索相关片段
  2. 将片段格式化为带编号的「参考资料」上下文
  3. 连同系统提示词（强制引用、禁止编造）交给 LLM
  4. LLM 生成答案，内联标注 [1][2] 引用编号
  5. 返回 answer + citations（来源列表）

上下文管理：
  通过 LangGraph checkpointer 保留最近 3-5 轮对话历史，支持多轮问答。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from textwrap import dedent
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from app.config import config
from app.core.llm_factory import llm_factory
from app.core.session_persistence import session_persistence_manager
from app.services.kb_api_client import RetrievalResult, kb_api_client

# 需要知识库检索的关键词（命中则走 RAG，否则直接回答）
_KB_KEYWORDS = [
    "投保",
    "寿险",
    "保险",
    "规则",
    "体检",
    "核保",
    "理赔",
    "保额",
    "风险",
    "产品",
    "条款",
    "政策",
    "规定",
    "标准",
    "流程",
    "要求",
    "条件",
    "知识库",
    "文档",
    "资料",
    "检索",
    "根据",
    "引用",
    "来源",
    "阳光",
    "升",
    "重疾",
    "身故",
    "残疾",
    "职业",
    "年龄",
]


def _needs_knowledge_retrieval(question: str) -> bool:
    """判断用户问题是否需要检索知识库。

    简单的关键词匹配策略：命中任一关键词即检索。
    对于闲聊、打招呼等无需走 RAG。
    """
    q = question.lower().strip()
    if len(q) < 4:
        return False
    # 闲聊类直接跳过
    greetings = ["你好", "hello", "hi", "谢谢", " thanks", "你是谁", "再见", "拜拜"]
    if any(q.startswith(g) for g in greetings):
        return False
    return True
    # return any(kw in q for kw in _KB_KEYWORDS)


class RagAgentService:
    """基于知识库 API 的 RAG 问答服务"""

    def __init__(self, streaming: bool = True) -> None:
        self.model_name = config.effective_chat_model
        self.streaming = streaming
        self.system_prompt = self._build_system_prompt()
        self.model = llm_factory.create_chat_model(temperature=0.3, streaming=streaming)
        self.checkpointer = session_persistence_manager.checkpointer
        self.agent = None
        self._agent_initialized = False
        logger.info(f"RAG Agent 服务初始化完成, model={self.model_name}, streaming={streaming}")

    def configure_checkpointer(self, checkpointer: Any) -> None:
        self.checkpointer = checkpointer
        self.agent = None
        self._agent_initialized = False

    async def _initialize_agent(self) -> None:
        """初始化 LangGraph Agent（无工具，仅对话 + checkpointer）"""
        if self._agent_initialized:
            return
        self.agent = create_agent(
            self.model,
            tools=[],
            checkpointer=self.checkpointer,
            system_prompt=self.system_prompt,
        )
        self._agent_initialized = True

    def _build_system_prompt(self) -> str:
        """构建系统提示词，强制要求引用来源、禁止编造。"""
        return dedent("""
            你是一个专业的智能问答助手，专注于基于知识库内容为用户解答问题。

            ## 回答规则（必须严格遵守）

            1. **严格基于上下文回答**：你的回答必须严格基于用户消息中提供的「参考资料」，不得使用参考资料之外的知识。如果用户消息中没有提供参考资料，可以基于通用知识进行简要回答。

            2. **标注引用来源**：当回答中引用了参考资料的内容时，在相关语句末尾用 [1]、[2] 等方括号序号标注，序号与「参考资料」的编号一一对应。多条信息合并陈述时，标注所有相关编号如 [1][3]。

            3. **无法回答时**：如果参考资料中没有包含用户问题的答案，请直接回答「抱歉，当前知识库中没有找到相关信息。您可以尝试以下方式：\n1. 换一种关键词重新提问\n2. 通过下方「点踩」或右上方「上报Bug」功能进行反馈」，不要编造答案，不要使用参考资料之外的知识进行补充。

            4. **禁止编造**：严禁编造任何不在参考资料中的信息、数据、规则、政策、条款或数字。宁可说"参考资料中未提及"也不要猜测。

            5. **结构化回答**：回答应条理清晰，对于复杂问题使用分点、列表等格式帮助用户理解。引用来源标注应自然融入正文。

            6. **语言**：使用中文回答，与用户的提问语言保持一致。

            ## 参考资料说明

            参考资料以编号列表形式提供在用户消息中，每条包含：
            - 编号（用于引用标注）
            - 来源文档名称
            - 片段ID
            - 相似度
            - 内容

            请仅使用这些资料中的信息来回答问题，并按上述规则标注引用。
        """).strip()

    # ----------------------------------------------------------------
    # 检索 + 上下文构建
    # ----------------------------------------------------------------
    async def _retrieve_and_build_context(self, question: str) -> tuple[str, list[dict[str, Any]]]:
        """调用 KB API 检索并构建上下文文本 + 引用列表。

        Returns:
            (context_text, citations)
            - context_text: 格式化的参考资料文本，注入用户消息
            - citations: 引用来源列表，返回给前端展示
        """
        try:
            kb_ids = config.kb_default_kb_id_list or None
            result: RetrievalResult = await kb_api_client.retrieve(
                query=question,
                kb_ids=kb_ids,
            )
        except Exception as e:
            logger.error(f"[RAG] 知识库检索失败: {e}")
            return "", []

        # 过滤低相似度片段
        threshold = config.kb_similarity_threshold
        chunks = [c for c in result.chunks if c.similarity >= threshold]

        # 取 top K
        top_k = config.kb_top_k
        chunks = chunks[:top_k]

        if not chunks:
            logger.info("[RAG] 检索结果为空（无符合条件的片段）")
            return "", []

        # 构建上下文文本
        context_parts = []
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
                    "content": chunk.content,
                }
            )

        context_text = "\n\n".join(context_parts)
        logger.info(f"[RAG] 构建上下文完成: {len(chunks)} 条参考资料")
        return context_text, citations

    def _build_user_message(self, question: str, context: str) -> str:
        """构建包含检索上下文的用户消息。"""
        if not context:
            return question
        return f"请基于以下参考资料回答用户的问题。\n\n{context}\n\n---\n用户的问题：{question}"

    # ----------------------------------------------------------------
    # 非流式查询
    # ----------------------------------------------------------------
    async def query(self, question: str, session_id: str) -> dict[str, Any]:
        """非流式查询，返回 answer + citations + message_id。

        Returns:
            {"answer": str, "citations": list, "message_id": str}
        """
        try:
            await self._initialize_agent()
            logger.info(f"[会话 {session_id}] RAG 查询（非流式）: {question}")

            # 1. 检索
            use_kb = _needs_knowledge_retrieval(question)
            context = ""
            citations: list[dict[str, Any]] = []
            if use_kb:
                context, citations = await self._retrieve_and_build_context(question)

            # 2. 构建用户消息（含上下文）
            user_content = self._build_user_message(question, context)
            messages = [HumanMessage(content=user_content)]

            agent_input = {"messages": messages}
            config_dict = {"configurable": {"thread_id": session_id}}

            # 3. 调用 Agent（自动加载历史 + 保存）
            result = await self.agent.ainvoke(input=agent_input, config=config_dict)

            messages_result = result.get("messages", [])
            answer = ""
            if messages_result:
                last_message = messages_result[-1]
                answer = (
                    last_message.content if hasattr(last_message, "content") else str(last_message)
                )

            message_id = f"msg_{session_id}_{int(datetime.now().timestamp() * 1000)}"

            session_persistence_manager.upsert_chat_session(
                session_id=session_id, question=question, answer=answer
            )
            logger.info(f"[会话 {session_id}] RAG 查询完成（非流式）, citations={len(citations)}")

            return {"answer": answer, "citations": citations, "message_id": message_id}

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG 查询失败（非流式）: {e}")
            raise

    # ----------------------------------------------------------------
    # 流式查询
    # ----------------------------------------------------------------
    async def query_stream(
        self, question: str, session_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """流式查询，yield 多种事件。

        事件类型：
        - {"type": "retrieving", "data": null}  正在检索知识库
        - {"type": "search_results", "data": citations}  检索完成，返回引用列表
        - {"type": "content", "data": "文本片段"}  答案流式内容
        - {"type": "done", "data": {"answer": str, "citations": list, "message_id": str}}
        - {"type": "error", "data": "错误信息"}
        """
        try:
            await self._initialize_agent()
            logger.info(f"[会话 {session_id}] RAG 查询（流式）: {question}")

            # 1. 检索
            use_kb = _needs_knowledge_retrieval(question)
            citations: list[dict[str, Any]] = []
            context = ""

            if use_kb:
                yield {"type": "retrieving", "data": None}
                context, citations = await self._retrieve_and_build_context(question)
                # 发送检索结果给前端（用于展示引用来源）
                yield {"type": "search_results", "data": citations}

            # 2. 构建用户消息
            user_content = self._build_user_message(question, context)
            messages = [HumanMessage(content=user_content)]

            agent_input = {"messages": messages}
            config_dict = {"configurable": {"thread_id": session_id}}

            full_response = ""

            # 3. 流式调用 Agent
            async for token, metadata in self.agent.astream(
                input=agent_input, config=config_dict, stream_mode="messages"
            ):
                node_name = (
                    metadata.get("langgraph_node", "unknown")
                    if isinstance(metadata, dict)
                    else "unknown"
                )
                message_type = type(token).__name__

                if message_type in ("AIMessage", "AIMessageChunk"):
                    content_blocks = getattr(token, "content_blocks", None)
                    if content_blocks and isinstance(content_blocks, list):
                        for block in content_blocks:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_content = block.get("text", "")
                                if text_content:
                                    full_response += text_content
                                    yield {
                                        "type": "content",
                                        "data": text_content,
                                        "node": node_name,
                                    }
                    elif isinstance(getattr(token, "content", None), str) and token.content:
                        full_response += token.content
                        yield {"type": "content", "data": token.content, "node": node_name}

            message_id = f"msg_{session_id}_{int(datetime.now().timestamp() * 1000)}"
            session_persistence_manager.upsert_chat_session(
                session_id=session_id, question=question, answer=full_response
            )
            logger.info(f"[会话 {session_id}] RAG 查询完成（流式）, citations={len(citations)}")
            yield {
                "type": "done",
                "data": {"answer": full_response, "citations": citations, "message_id": message_id},
            }

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG 查询失败（流式）: {e}")
            yield {"type": "error", "data": str(e)}

    # ----------------------------------------------------------------
    # 会话历史管理
    # ----------------------------------------------------------------
    async def get_session_history_async(self, session_id: str) -> list[dict[str, str]]:
        """获取会话历史消息（跳过 SystemMessage / ToolMessage）。

        优先从 SQLite 持久化存储读取（重启后仍可用）；
        若 SQLite 无记录（如 postgres 后端或旧会话），回退到 checkpointer。
        """
        try:
            # 优先从 SQLite 读取持久化消息
            persisted = session_persistence_manager.get_session_messages(session_id)
            if persisted:
                logger.info(f"获取会话历史(SQLite): {session_id}, 消息数量: {len(persisted)}")
                return persisted

            # 回退到 checkpointer（postgres 后端或当前运行时的内存会话）
            cfg = {"configurable": {"thread_id": session_id}}
            if hasattr(self.checkpointer, "aget"):
                checkpoint_tuple = await self.checkpointer.aget(cfg)
            else:
                checkpoint_tuple = self.checkpointer.get(cfg)
            history = self._checkpoint_to_history(checkpoint_tuple)
            logger.info(f"获取会话历史(checkpointer): {session_id}, 消息数量: {len(history)}")
            return history
        except Exception as e:
            logger.error(f"获取会话历史失败: {session_id}, 错误: {e}")
            return []

    def _checkpoint_to_history(self, checkpoint_tuple: Any) -> list[dict[str, str]]:
        """将 LangGraph checkpoint 转换为前端可用的历史列表。"""
        if not checkpoint_tuple:
            return []

        if isinstance(checkpoint_tuple, dict):
            checkpoint_data = checkpoint_tuple
        elif hasattr(checkpoint_tuple, "checkpoint"):
            checkpoint_data = checkpoint_tuple.checkpoint
        else:
            checkpoint_data = checkpoint_tuple[0] if checkpoint_tuple else {}

        from langchain_core.messages import ToolMessage

        messages = checkpoint_data.get("channel_values", {}).get("messages", [])
        history: list[dict[str, str]] = []
        for msg in messages:
            if isinstance(msg, (SystemMessage, ToolMessage)):
                continue
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                continue
            if not isinstance(msg, (HumanMessage, AIMessage)):
                continue

            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            content = msg.content if hasattr(msg, "content") else str(msg)
            if not content:
                continue
            # 从完整 user prompt 中提取用户实际问题
            if role == "user":
                content = self._extract_user_question(content)
            timestamp = getattr(msg, "timestamp", None) or datetime.now().isoformat()
            history.append({"role": role, "content": content, "timestamp": timestamp})
        return history

    @staticmethod
    def _extract_user_question(content: str) -> str:
        """从 _build_user_message 生成的完整 prompt 中提取用户实际问题。

        _build_user_message 格式:
            请基于以下参考资料回答用户的问题。

            {context}

            ---
            用户的问题：{question}

        无参考资料时直接返回 question。
        """
        marker = "用户的问题："
        if marker in content:
            return content.split(marker)[-1].strip()
        return content

    def clear_session(self, session_id: str) -> bool:
        """清空会话历史。"""
        try:
            self.checkpointer.delete_thread(session_id)
            session_persistence_manager.delete_chat_session(session_id)
            logger.info(f"已清除会话历史: {session_id}")
            return True
        except Exception as e:
            logger.error(f"清空会话历史失败: {session_id}, 错误: {e}")
            return False

    async def cleanup(self) -> None:
        logger.info("RAG Agent 服务资源已清理")


# 全局单例
rag_agent_service = RagAgentService(streaming=True)
