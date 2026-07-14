"""管理后台时间线接口测试

验证 GET /api/admin/timeline 能正确合并 Bug + 反馈并按时间倒序返回。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import router
from app.services.bug_service import bug_service
from app.services.feedback_service import feedback_service


def _make_bug(bug_id, created_at, title="测试Bug", category="检索问题"):
    return {
        "id": bug_id,
        "reporter": "tester",
        "category": category,
        "title": title,
        "content": "Bug 描述",
        "session_id": "",
        "query": "",
        "answer": "",
        "status": "待处理",
        "attachment_path": "",
        "created_at": created_at,
        "updated_at": created_at,
        "user_id": "",
    }


def _make_feedback(fb_id, created_at, rating="like", question="测试问题"):
    return {
        "id": fb_id,
        "session_id": "session-x",
        "message_id": f"msg-{fb_id}",
        "question": question,
        "answer": "AI 回答",
        "rating": rating,
        "feedback_tags": [],
        "feedback_description": "",
        "chunk_ids": [],
        "created_at": created_at,
        "updated_at": created_at,
        "user_id": "",
    }


def test_timeline_merges_bugs_and_feedbacks_by_time(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    bugs = [
        _make_bug(1, "2026-07-01T10:00:00", title="较早的Bug"),
        _make_bug(2, "2026-07-03T10:00:00", title="较晚的Bug"),
    ]
    feedbacks = [
        _make_feedback(10, "2026-07-02T10:00:00", rating="dislike"),
    ]

    monkeypatch.setattr(
        bug_service, "list_bugs", lambda limit=50, offset=0, status=None, category=None, user_id=None: bugs
    )
    monkeypatch.setattr(
        feedback_service,
        "list_feedback",
        lambda limit=50, offset=0, rating=None, user_id=None: feedbacks,
    )

    response = client.get("/api/admin/timeline?limit=10")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 3
    items = data["items"]
    # 按时间倒序：较晚的Bug -> 反馈 -> 较早的Bug
    assert items[0]["type"] == "bug"
    assert items[0]["id"] == 2
    assert items[1]["type"] == "feedback"
    assert items[1]["id"] == 10
    assert items[2]["type"] == "bug"
    assert items[2]["id"] == 1


def test_timeline_pagination(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    bugs = [_make_bug(i, f"2026-07-0{i}T10:00:00") for i in range(1, 6)]
    feedbacks = []

    monkeypatch.setattr(
        bug_service, "list_bugs", lambda limit=50, offset=0, status=None, category=None, user_id=None: bugs
    )
    monkeypatch.setattr(
        feedback_service,
        "list_feedback",
        lambda limit=50, offset=0, rating=None, user_id=None: feedbacks,
    )

    # 第一页 2 条
    resp = client.get("/api/admin/timeline?limit=2&offset=0")
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == 5  # 最晚的

    # 第二页 2 条
    resp = client.get("/api/admin/timeline?limit=2&offset=2")
    data = resp.json()["data"]
    assert len(data["items"]) == 2
    assert data["items"][0]["id"] == 3
