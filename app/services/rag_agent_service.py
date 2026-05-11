"""RAG Agent 服务 - 基于 LangGraph 的智能代理

使用 langchain_qwq 的 ChatQwen 原生集成，
支持真正的流式输出和更好的模型适配。

这个文件是整个 RAG 问答链路的“Agent 编排层”：
1. 接收用户问题
2. 把问题交给 ChatQwen 大模型
3. 大模型根据需要自动选择工具，比如知识库检索 retrieve_knowledge 或获取当前时间 get_current_time
4. 工具返回结果后，大模型再组织成最终回答
5. 支持两种返回方式：
   - query(...)：一次性返回完整字符串答案
   - query_stream(...)：像打字机一样逐块 yield 内容片段
"""

from typing import Annotated, Any, AsyncGenerator, Dict, Sequence

from langchain.agents import create_agent
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from loguru import logger
from typing_extensions import TypedDict

from app.config import config
from app.core.llm_factory import llm_factory
from app.tools import get_current_time, retrieve_knowledge
from app.agent.mcp_client import get_mcp_client_with_retry

# 阿里千问大模型和langchain集成参考： https://docs.langchain.com/oss/python/integrations/chat/qwen
# 注意：需要配置环境变量 DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 否则默认访问的是新加坡站点
# 同时也需要配置环境变量 DASHSCOPE_API_KEY=your_api_key


class AgentState(TypedDict):
    """
    Agent 状态

    LangGraph 会把一次会话中的消息都放在 state["messages"] 里。
    messages 里面通常包含：
    - SystemMessage：系统提示词，告诉模型应该如何工作
    - HumanMessage：用户输入
    - AIMessage：模型回复，可能包含工具调用请求
    - ToolMessage：工具执行结果

    add_messages 表示当图运行产生新消息时，不是覆盖旧消息，而是追加到 messages 中。
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]


def trim_messages_middleware(state: AgentState) -> dict[str, Any] | None:
    """
    修剪消息历史，只保留最近的几条消息以适应上下文窗口

    策略：
    - 保留第一条系统消息（System Message）
    - 保留最近的 6 条消息（3 轮对话）
    - 当消息少于等于 7 条时，不做修剪

    Args:
        state: Agent 状态

    Returns:
        包含修剪后消息的字典，如果无需修剪则返回 None
    """
    # state["messages"] 是当前会话累计的全部消息。
    # 如果一直不裁剪，多轮对话后 prompt 会越来越长，可能超过模型上下文窗口。
    messages = state["messages"]

    # 如果消息数量较少，无需修剪
    if len(messages) <= 7:
        return None

    # 提取第一条系统消息
    # 系统消息通常包含 Agent 的角色、工具使用原则、回答要求，不能丢
    first_msg = messages[0]

    # 保留最近的 6 条消息（确保包含完整的对话轮次）
    recent_messages = messages[-6:] if len(messages) % 2 == 0 else messages[-7:]

    # 构建新的消息列表
    # 最终只保留：系统消息 + 最近几轮对话
    new_messages = [first_msg] + list(recent_messages)

    logger.debug(f"修剪消息历史: {len(messages)} -> {len(new_messages)} 条")

    return {
        "messages": [
            # RemoveMessage(id=REMOVE_ALL_MESSAGES) 表示先清空 LangGraph 里的旧消息
            # 后面的 *new_messages 再把裁剪后的消息重新写回去
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *new_messages
        ]
    }


class RagAgentService:
    """
    RAG Agent 服务 - 使用 LangGraph + ChatQwen 原生集成

    这个类对外提供核心能力：
    - query(...)：普通问答，一次性返回完整答案 str
    - query_stream(...)：流式问答，持续 yield {"type": "content", "data": "..."}
    - get_session_history(...)：读取某个 session 的历史消息
    - clear_session(...)：清空某个 session 的历史消息

    这里的 RAG 不是简单地“先检索再回答”，而是 Agent 模式：
    模型会根据问题决定是否调用 retrieve_knowledge 工具。
    如果问题不需要知识库，也可以直接回答或调用其它工具。
    """

    def __init__(self, streaming: bool = True):
        """初始化 RAG Agent 服务

        Args:
            streaming: 是否启用流式输出，默认为 True
        """
        self.model_name = config.effective_chat_model
        self.streaming = streaming
        self.system_prompt = self._build_system_prompt()


        # 创建 ChatQwen 大模型对象。
        # 这个对象负责真正调用千问模型，后续 create_agent 会把它作为 Agent 的推理核心。
        self.model = llm_factory.create_chat_model(
            temperature=0.7,
            streaming=streaming,
        )

        # 定义基础工具
        # retrieve_knowledge：通常用于从 Milvus/RAG 知识库检索相关文档
        # get_current_time：用于回答当前时间等实时信息
        self.tools = [retrieve_knowledge, get_current_time]

        # MCP 客户端（延迟初始化，使用全局管理）
        # MCP 工具不是构造函数里立即加载，而是在第一次 query/query_stream 时异步加载
        self.mcp_tools: list = []

        # 创建内存检查点（用于会话管理）
        # MemorySaver 会按 thread_id 保存消息历史，使同一个 session_id 能保留上下文
        # 注意：这是内存级保存，服务重启后通常会丢失
        self.checkpointer = MemorySaver()

        # Agent 初始化（会在异步方法中完成）
        self.agent = None
        self._agent_initialized = False

        logger.info(f"RAG Agent 服务初始化完成 (OpenAI compatible), model={self.model_name}, streaming={streaming}")

    async def _initialize_agent(self):
        """
        异步初始化 Agent（包括 MCP 工具）

        这个方法最终会给 self.agent 赋值。
        self.agent 是 LangChain/LangGraph 创建出来的 Agent 执行器，
        后续 query(...) 会调用 self.agent.ainvoke(...)，
        query_stream(...) 会调用 self.agent.astream(...)。
        """
        if self._agent_initialized:
            return

        # 使用全局 MCP 客户端管理器（带重试拦截器）
        # MCP 可以理解成一批外部工具服务，比如浏览器、数据库、第三方 API 等
        mcp_client = await get_mcp_client_with_retry()

        # 获取 MCP 工具
        mcp_tools = await mcp_client.get_tools()
        logger.info(f"成功加载 {len(mcp_tools)} 个 MCP 工具")

        # 将 MCP 工具添加到实例变量中
        self.mcp_tools = mcp_tools

        # 合并所有工具
        # Agent 最终能看到的工具 = 本地基础工具 + MCP 动态加载的工具
        all_tools = self.tools + self.mcp_tools

        # create_agent 会创建一个能自动选择工具的 Agent。
        # 大模型会看到工具 schema，并在需要时生成 tool_call；
        # LangGraph 执行工具后，再把工具结果交回模型生成最终回答。
        self.agent = create_agent(
            self.model,
            tools=all_tools,
            checkpointer=self.checkpointer,
        )

        self._agent_initialized = True


        if all_tools:
            tool_names = [tool.name if hasattr(tool, "name") else str(tool) for tool in all_tools]
            logger.info(f"可用工具列表: {', '.join(tool_names)}")

    def _build_system_prompt(self) -> str:
        """
        构建系统提示词

        注意：LangChain 框架会自动将工具信息传递给 LLM，
        因此系统提示词中无需列举具体的工具列表。

        Returns:
            str: 系统提示词
        """
        from textwrap import dedent

        # 这段提示词会作为 SystemMessage 放进每次请求的 messages 中。
        # 它定义了模型的工作方式：该用工具时用工具，不知道就说明不确定。
        return dedent("""
            你是一个专业的AI助手，能够使用多种工具来帮助用户解决问题。

            工作原则:
            1. 理解用户需求，选择合适的工具来完成任务
            2. 当需要获取实时信息或专业知识时，主动使用相关工具
            3. 基于工具返回的结果提供准确、专业的回答
            4. 如果工具无法提供足够信息，请诚实地告知用户

            回答要求:
            - 保持友好、专业的语气
            - 回答简洁明了，重点突出
            - 基于事实，不编造信息
            - 如有不确定的地方，明确说明

            请根据用户的问题，灵活使用可用工具，提供高质量的帮助。
        """).strip()

    async def query(
        self,
        question: str,
        session_id: str,
    ) -> str:
        """
        非流式处理用户问题（一次性返回完整答案）

        输入示例：
        question = "CPU 飙高怎么排查？"
        session_id = "user-123"

        返回示例：
        "CPU 飙高可以先从以下几个方向排查：1. 使用 top 查看高占用进程..."

        内部如果模型判断需要查知识库，可能会自动调用 retrieve_knowledge 工具。
        但这个方法最终只返回最后一条 AIMessage 的 content，也就是完整答案字符串。

        Args:
            question: 用户问题
            session_id: 会话ID（作为 thread_id）

        Returns:
            str: 完整答案
        """
        try:
            # 第一次调用时会创建 Agent，并加载本地工具 + MCP 工具。
            # 后续同一个服务实例再次调用时，_initialize_agent() 会直接返回，不重复初始化。
            await self._initialize_agent()

            logger.info(f"[会话 {session_id}] RAG Agent 收到查询（非流式）: {question}")

            # 构建消息列表（系统提示 + 用户问题）
            # 这一轮真正送给 Agent 的输入大概是：
            # {
            #     "messages": [
            #         SystemMessage(content="你是一个专业的AI助手..."),
            #         HumanMessage(content="CPU 飙高怎么排查？")
            #     ]
            # }
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=question)
            ]

            # 构建 Agent 输入
            agent_input = {"messages": messages}

            # 配置 thread_id（用于会话持久化）
            config_dict = {
                "configurable": {
                    "thread_id": session_id
                }
            }

            # 非流式执行 Agent。
            # 返回 result 通常是一个 dict，里面包含完整的 messages 列表。
            # messages 中可能包括：用户消息、模型工具调用消息、工具结果消息、最终回答消息。
            result = await self.agent.ainvoke(
                input=agent_input,
                config=config_dict,
            )

            # 提取最终答案
            # Agent 执行完后，最后一条消息一般就是模型给用户的最终回答
            messages_result = result.get("messages", [])
            if messages_result:
                last_message = messages_result[-1]
                answer = last_message.content if hasattr(last_message, 'content') else str(last_message)

                # 记录工具调用
                if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                    tool_names = [tc.get("name", "unknown") for tc in last_message.tool_calls]
                    logger.info(f"[会话 {session_id}] Agent 调用了工具: {tool_names}")

                logger.info(f"[会话 {session_id}] RAG Agent 查询完成（非流式）")
                return answer

            logger.warning(f"[会话 {session_id}] Agent 返回结果为空")
            return ""

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（非流式）: {e}")
            raise

    async def query_stream(
        self,
        question: str,
        session_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式处理用户问题（逐步返回答案片段）

        输入示例：
        question = "CPU 飙高怎么排查？"
        session_id = "user-123"

        yield 的结果示例：
        {"type": "content", "data": "CPU", "node": "model"}
        {"type": "content", "data": " 飙高", "node": "model"}
        {"type": "content", "data": " 可以先查看 top...", "node": "model"}
        {"type": "complete"}

        如果出错，则 yield：
        {"type": "error", "data": "具体错误信息"}

        这个方法适合 SSE/WebSocket 等接口，把模型回答实时推给前端。

        Args:
            question: 用户问题
            session_id: 会话ID（作为 thread_id）

        Yields:
            Dict[str, Any]: 包含流式数据的字典
                - type: "content" | "tool_call" | "complete" | "error"
                - data: 具体内容
        """
        try:
            # 第一次调用时会创建 Agent，并加载本地工具 + MCP 工具。
            # 流式和非流式共用同一个 self.agent。
            await self._initialize_agent()

            logger.info(f"[会话 {session_id}] RAG Agent 收到查询（流式）: {question}")

            # 构建消息列表（系统提示 + 用户问题）
            # 和 query(...) 一样，这里也会把系统提示词和本轮用户问题一起交给 Agent。
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=question)
            ]

            # 构建 Agent 输入
            agent_input = {"messages": messages}

            # 配置 thread_id（用于会话持久化）
            config_dict = {
                "configurable": {
                    "thread_id": session_id
                }
            }

            # 流式执行 Agent。
            # stream_mode="messages" 表示每当模型或工具产生新消息片段时，就异步吐出来。
            async for token, metadata in self.agent.astream(
                input=agent_input,
                config=config_dict,
                stream_mode="messages",
            ):
                # metadata 里通常会包含当前 token 来自 LangGraph 的哪个节点，例如模型节点或工具节点
                node_name = metadata.get('langgraph_node', 'unknown') if isinstance(metadata, dict) else 'unknown'
                message_type = type(token).__name__

                # 这里只把 AIMessage/AIMessageChunk 中的文本内容返回给前端。
                # 工具调用过程本身没有显式 yield 出去，所以前端主要看到的是最终回答文本流。
                if message_type in ("AIMessage", "AIMessageChunk"):
                    content_blocks = getattr(token, 'content_blocks', None)

                    # ChatQwen 流式返回的内容可能是 content_blocks 结构：
                    # [{"type": "text", "text": "一小段回答"}]
                    if content_blocks and isinstance(content_blocks, list):
                        for block in content_blocks:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                text_content = block.get('text', '')
                                if text_content:
                                    yield {
                                        "type": "content",
                                        "data": text_content,
                                        "node": node_name
                                    }
                    elif isinstance(getattr(token, "content", None), str) and token.content:
                        yield {
                            "type": "content",
                            "data": token.content,
                            "node": node_name
                        }

            logger.info(f"[会话 {session_id}] RAG Agent 查询完成（流式）")
            # 告诉前端：本次流式回答已经结束
            yield {"type": "complete"}

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（流式）: {e}")
            yield {
                "type": "error",
                "data": str(e)
            }
            raise

    def get_session_history(self, session_id: str) -> list:
        """
        获取会话历史（从 MemorySaver checkpointer 中读取）

        输入：
        session_id = "user-123"

        返回示例：
        [
            {
                "role": "user",
                "content": "CPU 飙高怎么排查？",
                "timestamp": "2026-05-08T16:50:00"
            },
            {
                "role": "assistant",
                "content": "可以先使用 top 查看进程...",
                "timestamp": "2026-05-08T16:50:02"
            }
        ]

        注意：
        这里会跳过 SystemMessage，只返回用户和助手消息，方便前端展示聊天记录。

        Args:
            session_id: 会话ID（即 thread_id）

        Returns:
            list: 消息历史列表 [{"role": "user|assistant", "content": "...", "timestamp": "..."}]
        """
        try:
            # 使用 checkpointer 的 get 方法获取最新的检查点
            # thread_id 必须和 query/query_stream 里传入的 session_id 一致
            config = {"configurable": {"thread_id": session_id}}
            
            # 获取该 thread 的最新检查点
            checkpoint_tuple = self.checkpointer.get(config)
            
            if not checkpoint_tuple:
                logger.info(f"获取会话历史: {session_id}, 消息数量: 0")
                return []
            
            # checkpoint_tuple 可能是命名元组或普通元组，安全地提取 checkpoint
            # 通常第一个元素是 checkpoint 数据
            if hasattr(checkpoint_tuple, 'checkpoint'):
                checkpoint_data = checkpoint_tuple.checkpoint  # type: ignore
            else:
                # 如果是普通元组，第一个元素是 checkpoint
                checkpoint_data = checkpoint_tuple[0] if checkpoint_tuple else {}
            
            # 从检查点中提取消息
            # LangGraph checkpoint 的内部结构比较深，messages 存在 channel_values 里
            messages = checkpoint_data.get("channel_values", {}).get("messages", [])
            
            # 转换为前端需要的格式
            history = []
            for msg in messages:
                # 跳过系统消息
                if isinstance(msg, SystemMessage):
                    continue
                    
                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                content = msg.content if hasattr(msg, 'content') else str(msg)
                
                # 提取时间戳（如果有的话）
                timestamp = getattr(msg, 'timestamp', None)
                if timestamp:
                    history.append({
                        "role": role,
                        "content": content,
                        "timestamp": timestamp
                    })
                else:
                    from datetime import datetime
                    history.append({
                        "role": role,
                        "content": content,
                        "timestamp": datetime.now().isoformat()
                    })
            
            logger.info(f"获取会话历史: {session_id}, 消息数量: {len(history)}")
            return history
            
        except Exception as e:
            logger.error(f"获取会话历史失败: {session_id}, 错误: {e}")
            return []

    def clear_session(self, session_id: str) -> bool:
        """
        清空会话历史（从 MemorySaver checkpointer 中删除）

        输入：
        session_id = "user-123"

        返回：
        True：删除成功
        False：删除失败

        清空后，同一个 session_id 再提问时，就不会带上之前的对话上下文。

        Args:
            session_id: 会话ID（即 thread_id）

        Returns:
            bool: 是否成功
        """
        try:
            # 使用 checkpointer 的 delete_thread 方法删除该 thread 的所有检查点
            self.checkpointer.delete_thread(session_id)
            
            logger.info(f"已清除会话历史: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"清空会话历史失败: {session_id}, 错误: {e}")
            return False

    async def cleanup(self):
        """
        清理资源

        当前实现中 MCP 客户端由全局管理器统一管理，所以这里没有显式关闭连接。
        如果未来这个类自己持有数据库连接、HTTP client 或 MCP session，可以在这里释放。
        """
        try:
            logger.info("清理 RAG Agent 服务资源...")
            # MCP 客户端由全局管理器统一管理，无需手动清理
            logger.info("RAG Agent 服务资源已清理")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")


# 全局单例 - 启用流式输出
# 其他 API 层通常会直接 import rag_agent_service，然后调用 query/query_stream。
rag_agent_service = RagAgentService(streaming=True)
