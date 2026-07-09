import asyncio

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.services.rag_agent_service import RagAgentService


class FakeCheckpointer:
    def get(self, config):
        return {
            "channel_values": {
                "messages": [
                    HumanMessage(content="CPU 飙高怎么排查？"),
                    AIMessage(content="可以先看 top 和进程占用。"),
                ]
            }
        }


def test_get_session_history_reads_checkpoint_dict():
    service = RagAgentService.__new__(RagAgentService)
    service.checkpointer = FakeCheckpointer()

    history = service.get_session_history("session-1")

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "CPU 飙高怎么排查？"
    assert history[1]["content"] == "可以先看 top 和进程占用。"


class FakeAsyncCheckpointer:
    async def aget(self, config):
        return {
            "channel_values": {
                "messages": [
                    HumanMessage(content="服务重启后还有记忆吗？"),
                    AIMessage(content="有，当前会话状态来自 PostgreSQL checkpoint。"),
                ]
            }
        }


class FakeCheckpointerWithInternalMessages:
    def get(self, config):
        return {
            "channel_values": {
                "messages": [
                    HumanMessage(content="查一下 CPU"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "query_cpu_metrics",
                                "args": {"service_name": "api"},
                                "id": "call-1",
                            }
                        ],
                    ),
                    ToolMessage(content='{"cpu": 95}', tool_call_id="call-1"),
                    AIMessage(content="CPU 当前较高，建议先查看高占用进程。"),
                ]
            }
        }


class FakeDirectAgent:
    def __init__(self):
        self.called = False
        self.input = None
        self.config = None

    async def ainvoke(self, input, config):
        self.called = True
        self.input = input
        self.config = config
        return {"messages": [AIMessage(content="我是一个中文助手。")]}

    async def astream(self, input, config, stream_mode):
        self.called = True
        self.input = input
        self.config = config
        yield AIMessageChunk(content="我是一个中文助手。"), {}


class ExplodingAgent:
    async def ainvoke(self, input, config):
        raise AssertionError("tool agent should not be called")

    async def astream(self, input, config, stream_mode):
        raise AssertionError("tool agent should not be called")
        yield


def test_get_session_history_async_reads_async_checkpoint_dict():
    service = RagAgentService.__new__(RagAgentService)
    service.checkpointer = FakeAsyncCheckpointer()

    history = asyncio.run(service.get_session_history_async("session-2"))

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "服务重启后还有记忆吗？"
    assert history[1]["content"] == "有，当前会话状态来自 PostgreSQL checkpoint。"


def test_plain_chat_query_uses_direct_agent_and_persists_answer(monkeypatch):
    import app.services.rag_agent_service as rag_module

    direct_agent = FakeDirectAgent()
    persisted = []
    service = RagAgentService.__new__(RagAgentService)
    service.agent = ExplodingAgent()
    service.direct_agent = direct_agent
    service._direct_agent_initialized = True
    service.system_prompt = "system"
    monkeypatch.setattr(
        rag_module.session_persistence_manager,
        "upsert_chat_session",
        lambda **kwargs: persisted.append(kwargs),
    )

    result = asyncio.run(service.query("你是谁？", "session-direct"))

    assert result == {"answer": "我是一个中文助手。", "sources": []}
    assert direct_agent.called is True
    assert direct_agent.input == {"messages": [HumanMessage(content="你是谁？")]}
    assert direct_agent.config == {"configurable": {"thread_id": "session-direct"}}
    assert persisted == [
        {
            "session_id": "session-direct",
            "question": "你是谁？",
            "answer": "我是一个中文助手。",
        }
    ]


def test_plain_chat_stream_uses_direct_agent_and_persists_answer(monkeypatch):
    import app.services.rag_agent_service as rag_module

    direct_agent = FakeDirectAgent()
    persisted = []
    service = RagAgentService.__new__(RagAgentService)
    service.agent = ExplodingAgent()
    service._agent_initialized = True
    service.direct_agent = direct_agent
    service._direct_agent_initialized = True
    service.system_prompt = "system"
    monkeypatch.setattr(
        rag_module.session_persistence_manager,
        "upsert_chat_session",
        lambda **kwargs: persisted.append(kwargs),
    )

    async def collect():
        return [chunk async for chunk in service.query_stream("你是谁？", "session-stream")]

    chunks = asyncio.run(collect())

    assert chunks == [
        {"type": "content", "data": "我是一个中文助手。", "node": "unknown"},
        {"type": "complete"},
    ]
    assert direct_agent.called is True
    assert direct_agent.input == {"messages": [HumanMessage(content="你是谁？")]}
    assert direct_agent.config == {"configurable": {"thread_id": "session-stream"}}
    assert persisted == [
        {
            "session_id": "session-stream",
            "question": "你是谁？",
            "answer": "我是一个中文助手。",
        }
    ]


def test_rag_agent_tool_routing_detects_tool_questions():
    service = RagAgentService.__new__(RagAgentService)

    # 寒暄/闲聊短句走无工具直连模式
    assert service._should_use_agent_tools("你好") is False
    assert service._should_use_agent_tools("你是谁？") is False
    assert service._should_use_agent_tools("谢谢") is False
    # 其余问题默认走带工具 Agent（知识库检索由模型按需触发）
    assert service._should_use_agent_tools("服务重启后还有记忆吗？") is True
    assert service._should_use_agent_tools("现在几点？") is True
    assert service._should_use_agent_tools("查询 order-api 的 CPU 指标") is True
    assert service._should_use_agent_tools("根据知识库回答 PostgreSQL 会话保存") is True


def test_get_session_history_ignores_internal_agent_messages():
    service = RagAgentService.__new__(RagAgentService)
    service.checkpointer = FakeCheckpointerWithInternalMessages()

    history = service.get_session_history("session-3")

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert [item["content"] for item in history] == [
        "查一下 CPU",
        "CPU 当前较高，建议先查看高占用进程。",
    ]


def test_checkpoint_to_history_ignores_internal_agent_messages():
    service = RagAgentService.__new__(RagAgentService)
    checkpoint = {
        "channel_values": {
            "messages": [
                SystemMessage(content="system prompt"),
                HumanMessage(content="查一下 CPU"),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "query_cpu_metrics",
                            "args": {"service_name": "api"},
                            "id": "call-1",
                        }
                    ],
                ),
                ToolMessage(content='{"cpu": 95}', tool_call_id="call-1"),
                AIMessage(content="CPU 当前较高，建议先查看高占用进程。"),
            ]
        }
    }

    history = service._checkpoint_to_history(checkpoint)

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert [item["content"] for item in history] == [
        "查一下 CPU",
        "CPU 当前较高，建议先查看高占用进程。",
    ]
