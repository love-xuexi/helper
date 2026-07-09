import pytest

from app.config import Settings
from app.services.feedback_service import RATING_DISLIKE, RATING_LIKE, FeedbackService


@pytest.fixture
def service(tmp_path):
    settings = Settings(_env_file=None, feedback_db_path=str(tmp_path / "feedback.db"))
    return FeedbackService(settings=settings)


def test_save_and_list_feedback(service):
    record = service.save_feedback(
        session_id="session-1",
        question="CPU 飙高怎么排查？",
        answer="可以先使用 top...",
        rating=RATING_DISLIKE,
        tags=["回答不准确"],
        comment="第 2 步命令写错了",
        chunk_ids=["chunk-1", "chunk-2"],
    )

    assert record["id"]
    records = service.list_feedback()
    assert len(records) == 1
    assert records[0]["question"] == "CPU 飙高怎么排查？"
    assert records[0]["rating"] == RATING_DISLIKE
    assert records[0]["tags"] == ["回答不准确"]
    assert records[0]["chunk_ids"] == ["chunk-1", "chunk-2"]


def test_list_feedback_filter_by_rating(service):
    service.save_feedback("s1", "q1", "a1", RATING_LIKE)
    service.save_feedback("s2", "q2", "a2", RATING_DISLIKE)

    likes = service.list_feedback(rating=RATING_LIKE)
    assert len(likes) == 1
    assert likes[0]["rating"] == RATING_LIKE


def test_get_stats(service):
    service.save_feedback("s1", "q1", "a1", RATING_LIKE)
    service.save_feedback("s2", "q2", "a2", RATING_LIKE)
    service.save_feedback("s3", "q3", "a3", RATING_DISLIKE)

    stats = service.get_stats()
    assert stats[RATING_LIKE] == 2
    assert stats[RATING_DISLIKE] == 1


def test_invalid_rating_rejected(service):
    with pytest.raises(ValueError):
        service.save_feedback("s1", "q1", "a1", "neutral")
