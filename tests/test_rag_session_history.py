from langchain_core.messages import AIMessage, HumanMessage

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
