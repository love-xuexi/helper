from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from app.config import Settings, config


@dataclass(frozen=True)
class ChatSessionMetadata:
    session_id: str
    title: str
    last_message_preview: str
    message_count: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_message(cls, session_id: str, question: str, answer: str) -> "ChatSessionMetadata":
        title = question[:30] + ("..." if len(question) > 30 else "")
        preview = answer[:80] + ("..." if len(answer) > 80 else "")
        return cls(
            session_id=session_id,
            title=title or "新对话",
            last_message_preview=preview,
            message_count=2,
        )


class PostgresSessionStore:
    def __init__(self, connection: Any):
        self.connection = connection

    def setup(self) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_message_preview TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
                ON chat_sessions (updated_at DESC)
                """
            )
        self.connection.commit()

    def upsert_session(self, metadata: ChatSessionMetadata) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_sessions (
                    session_id,
                    title,
                    last_message_preview,
                    message_count
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    title = COALESCE(NULLIF(chat_sessions.title, '新对话'), EXCLUDED.title),
                    updated_at = NOW(),
                    last_message_preview = EXCLUDED.last_message_preview,
                    message_count = GREATEST(chat_sessions.message_count, 0) + EXCLUDED.message_count
                """,
                (
                    metadata.session_id,
                    metadata.title,
                    metadata.last_message_preview,
                    metadata.message_count,
                ),
            )
        self.connection.commit()

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT session_id, title, created_at, updated_at, last_message_preview, message_count
                FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            {
                "session_id": row[0],
                "title": row[1],
                "created_at": _format_datetime(row[2]),
                "updated_at": _format_datetime(row[3]),
                "last_message_preview": row[4],
                "message_count": row[5],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM chat_sessions WHERE session_id = %s", (session_id,))
        self.connection.commit()


class SessionPersistenceManager:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or config
        self.backend = self.settings.session_checkpoint_backend.lower()
        self.checkpointer: Any = MemorySaver()
        self.session_store: PostgresSessionStore | None = None
        self._checkpoint_context: Any = None
        self._connection: Any = None

    def initialize(self) -> None:
        if self.backend == "memory":
            self.checkpointer = MemorySaver()
            self.session_store = None
            logger.info("[SessionPersistence] 使用内存会话 checkpoint")
            return

        if self.backend != "postgres":
            raise ValueError(f"Unsupported SESSION_CHECKPOINT_BACKEND: {self.backend}")

        if not self.settings.postgres_dsn:
            raise ValueError("POSTGRES_DSN must be configured when SESSION_CHECKPOINT_BACKEND=postgres")

        self._initialize_postgres()

    def _initialize_postgres(self) -> None:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import connect

        logger.info("[SessionPersistence] 正在初始化 PostgreSQL 会话持久化")
        self._checkpoint_context = PostgresSaver.from_conn_string(self.settings.postgres_dsn)
        self.checkpointer = self._checkpoint_context.__enter__()
        self.checkpointer.setup()
        self._connection = connect(
            self.settings.postgres_dsn,
            autocommit=False,
            connect_timeout=int(self.settings.postgres_connect_timeout_seconds),
        )
        self.session_store = PostgresSessionStore(self._connection)
        self.session_store.setup()
        logger.info("[SessionPersistence] PostgreSQL 会话持久化初始化完成")

    def upsert_chat_session(self, session_id: str, question: str, answer: str) -> None:
        if self.session_store is None:
            return
        metadata = ChatSessionMetadata.from_message(session_id=session_id, question=question, answer=answer)
        self.session_store.upsert_session(metadata)

    def list_chat_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        if self.session_store is None:
            return []
        return self.session_store.list_sessions(limit=limit)

    def delete_chat_session(self, session_id: str) -> None:
        if self.session_store is not None:
            self.session_store.delete_session(session_id)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._checkpoint_context is not None:
            self._checkpoint_context.__exit__(None, None, None)
            self._checkpoint_context = None


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


session_persistence_manager = SessionPersistenceManager()
