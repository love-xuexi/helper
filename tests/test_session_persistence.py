import asyncio

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


def test_postgres_backend_initializes_async_checkpointer(monkeypatch):
    settings = Settings(
        _env_file=None,
        session_checkpoint_backend="postgres",
        postgres_dsn="postgresql://superbiz:superbiz_dev@localhost:5432/super_biz_agent",
    )
    manager = SessionPersistenceManager(settings=settings)
    events = []

    class DummyAsyncCheckpointer:
        async def setup(self):
            events.append("checkpoint_setup")

        async def aget_tuple(self, config):
            return None

    dummy_checkpointer = DummyAsyncCheckpointer()

    class DummyAsyncContext:
        async def __aenter__(self):
            events.append("checkpoint_enter")
            return dummy_checkpointer

        async def __aexit__(self, exc_type, exc, tb):
            events.append("checkpoint_exit")

    class DummyAsyncPostgresSaver:
        @classmethod
        def from_conn_string(cls, dsn):
            events.append(("checkpoint_dsn", dsn))
            return DummyAsyncContext()

    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            events.append("session_store_sql")

    class DummyConnection:
        def cursor(self):
            return DummyCursor()

        def commit(self):
            events.append("session_store_commit")

        def close(self):
            events.append("session_store_close")

    def fake_connect(*args, **kwargs):
        events.append(("session_store_dsn", args[0]))
        return DummyConnection()

    import langgraph.checkpoint.postgres.aio as postgres_aio
    import psycopg

    monkeypatch.setattr(postgres_aio, "AsyncPostgresSaver", DummyAsyncPostgresSaver)
    monkeypatch.setattr(psycopg, "connect", fake_connect)

    asyncio.run(manager.initialize_async())

    assert manager.checkpointer is dummy_checkpointer
    assert hasattr(manager.checkpointer, "aget_tuple")
    assert ("checkpoint_dsn", settings.postgres_dsn) in events
    assert ("session_store_dsn", settings.postgres_dsn) in events

    asyncio.run(manager.close_async())

    assert "checkpoint_exit" in events
    assert "session_store_close" in events


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
