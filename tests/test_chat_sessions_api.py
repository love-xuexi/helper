from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chat import router
from app.core.session_persistence import session_persistence_manager


def test_list_chat_sessions_returns_manager_data(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    monkeypatch.setattr(
        session_persistence_manager,
        "list_chat_sessions",
        lambda limit=10, offset=0, user_id=None: [
            {
                "session_id": "session-1",
                "title": "CPU 排查",
                "created_at": "2026-05-27T12:00:00+00:00",
                "updated_at": "2026-05-27T12:01:00+00:00",
                "last_message_preview": "可以先看 top。",
                "message_count": 2,
            }
        ],
    )
    monkeypatch.setattr(
        session_persistence_manager,
        "count_chat_sessions",
        lambda user_id=None: 1,
    )

    response = client.get("/api/chat/sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert body["sessions"][0]["session_id"] == "session-1"
    assert body["sessions"][0]["title"] == "CPU 排查"


def test_list_chat_sessions_passes_offset_and_user_id(monkeypatch):
    """验证 offset 和 user_id 参数能正确透传到 manager。"""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    captured = {}

    def fake_list(limit=10, offset=0, user_id=None):
        captured["limit"] = limit
        captured["offset"] = offset
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(session_persistence_manager, "list_chat_sessions", fake_list)
    monkeypatch.setattr(
        session_persistence_manager, "count_chat_sessions", lambda user_id=None: 0
    )

    response = client.get("/api/chat/sessions?limit=5&offset=10&user_id=u1")

    assert response.status_code == 200
    assert captured["limit"] == 5
    assert captured["offset"] == 10
    assert captured["user_id"] == "u1"
