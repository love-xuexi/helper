import asyncio

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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


def test_get_session_history_async_reads_async_checkpoint_dict():
    service = RagAgentService.__new__(RagAgentService)
    service.checkpointer = FakeAsyncCheckpointer()

    history = asyncio.run(service.get_session_history_async("session-2"))

    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "服务重启后还有记忆吗？"
    assert history[1]["content"] == "有，当前会话状态来自 PostgreSQL checkpoint。"


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
