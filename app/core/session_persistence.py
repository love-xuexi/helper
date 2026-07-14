from __future__ import annotations

import threading
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
    # 用户隔离钩子：当前开发阶段为空字符串，后续接入用户体系后由调用方传入
    user_id: str = ""

    @classmethod
    def from_message(
        cls,
        session_id: str,
        question: str,
        answer: str,
        user_id: str = "",
    ) -> "ChatSessionMetadata":
        title = question[:30] + ("..." if len(question) > 30 else "")
        preview = answer[:80] + ("..." if len(answer) > 80 else "")
        return cls(
            session_id=session_id,
            title=title or "新对话",
            last_message_preview=preview,
            message_count=2,
            user_id=user_id,
        )


class InMemorySessionStore:
    """内存会话元数据存储（memory 后端使用）。

    进程重启后数据丢失，仅供开发/单机使用。生产环境应切到 postgres 后端。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def upsert_session(self, metadata: ChatSessionMetadata) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            existing = self._sessions.get(metadata.session_id)
            if existing is None:
                self._sessions[metadata.session_id] = {
                    "session_id": metadata.session_id,
                    "title": metadata.title or "新对话",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "last_message_preview": metadata.last_message_preview,
                    "message_count": metadata.message_count,
                    "user_id": metadata.user_id,
                }
            else:
                # 保留首轮标题；只在原标题为空/「新对话」时才用新标题覆盖
                title = existing["title"]
                if title in ("", "新对话") and metadata.title:
                    title = metadata.title
                self._sessions[metadata.session_id] = {
                    "session_id": metadata.session_id,
                    "title": title,
                    "created_at": existing.get("created_at", now_iso),
                    "updated_at": now_iso,
                    "last_message_preview": metadata.last_message_preview,
                    "message_count": existing["message_count"] + metadata.message_count,
                    "user_id": metadata.user_id or existing.get("user_id", ""),
                }

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._sessions.values())
        if user_id is not None:
            items = [s for s in items if s.get("user_id", "") == user_id]
        items.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        if limit > 0:
            return items[offset : offset + limit]
        return items[offset:]

    def count_sessions(self, user_id: str | None = None) -> int:
        with self._lock:
            items = list(self._sessions.values())
        if user_id is not None:
            items = [s for s in items if s.get("user_id", "") == user_id]
        return len(items)

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


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
                    message_count INTEGER NOT NULL DEFAULT 0,
                    user_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            # 兼容已存在的旧表：补 user_id 列
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'chat_sessions' AND column_name = 'user_id'
                """
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    "ALTER TABLE chat_sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT ''"
                )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at
                ON chat_sessions (updated_at DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id
                ON chat_sessions (user_id)
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
                    message_count,
                    user_id
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (session_id) DO UPDATE SET
                    title = COALESCE(NULLIF(chat_sessions.title, '新对话'), EXCLUDED.title),
                    updated_at = NOW(),
                    last_message_preview = EXCLUDED.last_message_preview,
                    message_count = GREATEST(chat_sessions.message_count, 0) + EXCLUDED.message_count,
                    user_id = COALESCE(NULLIF(EXCLUDED.user_id, ''), chat_sessions.user_id)
                """,
                (
                    metadata.session_id,
                    metadata.title,
                    metadata.last_message_preview,
                    metadata.message_count,
                    metadata.user_id,
                ),
            )
        self.connection.commit()

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT session_id, title, created_at, updated_at, last_message_preview, message_count
            FROM chat_sessions
        """
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = %s"
            params.append(user_id)
        query += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
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

    def count_sessions(self, user_id: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM chat_sessions"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = %s"
            params.append(user_id)
        with self.connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()[0]

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
        self.in_memory_store: InMemorySessionStore | None = None
        self._checkpoint_context: Any = None
        self._connection: Any = None

    def initialize(self) -> None:
        if self.backend == "memory":
            self.checkpointer = MemorySaver()
            self.in_memory_store = InMemorySessionStore()
            self.session_store = None
            logger.info("[SessionPersistence] 使用内存会话 checkpoint")
            return

        if self.backend != "postgres":
            raise ValueError(f"Unsupported SESSION_CHECKPOINT_BACKEND: {self.backend}")

        if not self.settings.postgres_dsn:
            raise ValueError("POSTGRES_DSN must be configured when SESSION_CHECKPOINT_BACKEND=postgres")

        self._initialize_postgres()

    async def initialize_async(self) -> None:
        if self.backend == "memory":
            self.checkpointer = MemorySaver()
            self.in_memory_store = InMemorySessionStore()
            self.session_store = None
            logger.info("[SessionPersistence] 使用内存会话 checkpoint")
            return

        if self.backend != "postgres":
            raise ValueError(f"Unsupported SESSION_CHECKPOINT_BACKEND: {self.backend}")

        if not self.settings.postgres_dsn:
            raise ValueError("POSTGRES_DSN must be configured when SESSION_CHECKPOINT_BACKEND=postgres")

        await self._initialize_postgres_async()

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

    async def _initialize_postgres_async(self) -> None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import connect

        logger.info("[SessionPersistence] 正在初始化 PostgreSQL 会话持久化")
        self._checkpoint_context = AsyncPostgresSaver.from_conn_string(self.settings.postgres_dsn)
        self.checkpointer = await self._checkpoint_context.__aenter__()
        await self.checkpointer.setup()
        self._connection = connect(
            self.settings.postgres_dsn,
            autocommit=False,
            connect_timeout=int(self.settings.postgres_connect_timeout_seconds),
        )
        self.session_store = PostgresSessionStore(self._connection)
        self.session_store.setup()
        logger.info("[SessionPersistence] PostgreSQL 会话持久化初始化完成")

    def upsert_chat_session(
        self,
        session_id: str,
        question: str,
        answer: str,
        user_id: str = "",
    ) -> None:
        metadata = ChatSessionMetadata.from_message(
            session_id=session_id, question=question, answer=answer, user_id=user_id
        )
        if self.session_store is not None:
            self.session_store.upsert_session(metadata)
            return
        if self.in_memory_store is not None:
            self.in_memory_store.upsert_session(metadata)

    def list_chat_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.session_store is not None:
            return self.session_store.list_sessions(limit=limit, offset=offset, user_id=user_id)
        if self.in_memory_store is not None:
            return self.in_memory_store.list_sessions(limit=limit, offset=offset, user_id=user_id)
        return []

    def count_chat_sessions(self, user_id: str | None = None) -> int:
        if self.session_store is not None:
            return self.session_store.count_sessions(user_id=user_id)
        if self.in_memory_store is not None:
            return self.in_memory_store.count_sessions(user_id=user_id)
        return 0

    def delete_chat_session(self, session_id: str) -> None:
        if self.session_store is not None:
            self.session_store.delete_session(session_id)
        if self.in_memory_store is not None:
            self.in_memory_store.delete_session(session_id)

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._checkpoint_context is not None and hasattr(self._checkpoint_context, "__exit__"):
            self._checkpoint_context.__exit__(None, None, None)
            self._checkpoint_context = None

    async def close_async(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._checkpoint_context is not None:
            if hasattr(self._checkpoint_context, "__aexit__"):
                await self._checkpoint_context.__aexit__(None, None, None)
            elif hasattr(self._checkpoint_context, "__exit__"):
                self._checkpoint_context.__exit__(None, None, None)
            self._checkpoint_context = None


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


session_persistence_manager = SessionPersistenceManager()
