from app.config import Settings


def test_session_checkpoint_backend_defaults_to_memory():
    settings = Settings(_env_file=None)

    assert settings.session_checkpoint_backend == "memory"
    assert settings.is_postgres_checkpoint_enabled is False


def test_postgres_checkpoint_backend_is_explicit():
    settings = Settings(
        _env_file=None,
        session_checkpoint_backend="postgres",
        postgres_dsn="postgresql://user:pass@localhost:5432/super_biz_agent",
    )

    assert settings.session_checkpoint_backend == "postgres"
    assert settings.postgres_dsn == "postgresql://user:pass@localhost:5432/super_biz_agent"
    assert settings.is_postgres_checkpoint_enabled is True


import pytest

from app.core.session_persistence import (
    ChatSessionMetadata,
    SessionPersistenceManager,
)


def test_memory_backend_returns_memory_saver():
    settings = Settings(_env_file=None, session_checkpoint_backend="memory")
    manager = SessionPersistenceManager(settings=settings)

    assert manager.backend == "memory"
    assert manager.checkpointer is not None
    assert manager.session_store is None


def test_postgres_backend_requires_dsn():
    settings = Settings(_env_file=None, session_checkpoint_backend="postgres", postgres_dsn="")
    manager = SessionPersistenceManager(settings=settings)

    with pytest.raises(ValueError, match="POSTGRES_DSN"):
        manager.initialize()


def test_chat_session_metadata_title_from_question():
    metadata = ChatSessionMetadata.from_message(
        session_id="session-1",
        question="CPU 飙高时怎么排查，需要看哪些指标？",
        answer="可以先看 CPU 使用率和进程占用。",
    )

    assert metadata.session_id == "session-1"
    assert metadata.title == "CPU 飙高时怎么排查，需要看哪些指标？"
    assert metadata.message_count == 2
    assert metadata.last_message_preview == "可以先看 CPU 使用率和进程占用。"
