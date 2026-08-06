from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
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
    # 原始问答内容，供 SQLite 消息表持久化使用
    question: str = ""
    answer: str = ""

    @classmethod
    def from_message(
        cls,
        session_id: str,
        question: str,
        answer: str,
        user_id: str = "",
    ) -> ChatSessionMetadata:
        title = question[:30] + ("..." if len(question) > 30 else "")
        preview = answer[:80] + ("..." if len(answer) > 80 else "")
        return cls(
            session_id=session_id,
            title=title or "新对话",
            last_message_preview=preview,
            message_count=2,
            user_id=user_id,
            question=question,
            answer=answer,
        )

    @classmethod
    def from_agent_session(
        cls,
        session_id: str,
        task: str,
        flow_json: str,
        report: str,
        user_id: str = "",
    ) -> ChatSessionMetadata:
        """Agent 模式的元数据构造。

        与 from_message 的区别：
        - title 从 task 截取（与普通问答一致）
        - last_message_preview 从 report 截取（而非 flow_json，避免 JSON 出现在预览中）
        - answer 存的是 flow_json（结构化 JSON），前端解析后渲染执行流程
        """
        title = task[:30] + ("..." if len(task) > 30 else "")
        preview = report[:80] + ("..." if len(report) > 80 else "")
        return cls(
            session_id=session_id,
            title=title or "Agent 任务",
            last_message_preview=preview,
            message_count=2,
            user_id=user_id,
            question=task,
            answer=flow_json,
        )


class InMemorySessionStore:
    """内存会话元数据存储（memory 后端使用）。

    进程重启后数据丢失，仅供开发/单机使用。生产环境应切到 postgres 后端。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def upsert_session(self, metadata: ChatSessionMetadata) -> None:
        now_iso = datetime.now(UTC).isoformat()
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

    def rename_session(self, session_id: str, title: str) -> bool:
        """重命名会话标题。返回是否成功（会话是否存在）。"""
        title = title.strip()
        if not title:
            return False
        with self._lock:
            existing = self._sessions.get(session_id)
            if existing is None:
                return False
            existing["title"] = title
            existing["updated_at"] = datetime.now(UTC).isoformat()
            return True

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


class SqliteSessionStore:
    """SQLite 会话存储（元数据 + 消息记录）。

    持久化会话元数据和逐条消息，进程重启后数据保留。
    与 BugStore/FeedbackStore 的 SQLite 模式保持一致。
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        """创建数据库表（幂等）。"""
        if self._initialized:
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '新对话',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_message_preview TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    user_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id)"
            )
        self._initialized = True
        logger.info(f"[SqliteSessionStore] 数据库初始化完成: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_session(self, metadata: ChatSessionMetadata) -> None:
        """Upsert 会话元数据，并追加本轮 user/assistant 两条消息。"""
        now = datetime.now().isoformat()
        with self._lock, self._get_conn() as conn:
            existing = conn.execute(
                "SELECT title, message_count FROM chat_sessions WHERE session_id = ?",
                (metadata.session_id,),
            ).fetchone()

            if existing is None:
                title = metadata.title or "新对话"
                message_count = metadata.message_count
                conn.execute(
                    """
                    INSERT INTO chat_sessions (
                        session_id, title, created_at, updated_at,
                        last_message_preview, message_count, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        metadata.session_id,
                        title,
                        now,
                        now,
                        metadata.last_message_preview,
                        message_count,
                        metadata.user_id,
                    ),
                )
            else:
                # 保留首轮标题；只在原标题为空/「新对话」时才用新标题覆盖
                title = existing["title"]
                if title in ("", "新对话") and metadata.title:
                    title = metadata.title
                message_count = existing["message_count"] + metadata.message_count
                conn.execute(
                    """
                    UPDATE chat_sessions SET
                        title = ?, updated_at = ?,
                        last_message_preview = ?, message_count = ?, user_id = ?
                    WHERE session_id = ?
                    """,
                    (
                        title,
                        now,
                        metadata.last_message_preview,
                        message_count,
                        metadata.user_id or "",
                        metadata.session_id,
                    ),
                )

            # 追加本轮消息记录
            if metadata.question:
                conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (metadata.session_id, "user", metadata.question, now),
                )
            if metadata.answer:
                conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (metadata.session_id, "assistant", metadata.answer, now),
                )
            conn.commit()

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM chat_sessions"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._session_row_to_dict(row) for row in rows]

    def count_sessions(self, user_id: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM chat_sessions"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id = ?"
            params.append(user_id)
        with self._get_conn() as conn:
            return conn.execute(query, params).fetchone()[0]

    def get_messages(self, session_id: str) -> list[dict[str, str]]:
        """获取会话的全部消息记录（按时间正序）。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [
            {"role": row["role"], "content": row["content"], "timestamp": row["created_at"]}
            for row in rows
        ]

    def delete_session(self, session_id: str) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
            conn.commit()

    def rename_session(self, session_id: str, title: str) -> bool:
        """重命名会话标题。返回是否成功（会话是否存在）。"""
        title = title.strip()
        if not title:
            return False
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (title, datetime.now().isoformat(), session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _session_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_message_preview": row["last_message_preview"],
            "message_count": row["message_count"],
            "user_id": row["user_id"],
        }


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

    def rename_session(self, session_id: str, title: str) -> bool:
        """重命名会话标题。返回是否成功（会话是否存在）。"""
        title = title.strip()
        if not title:
            return False
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE chat_sessions SET title = %s, updated_at = NOW() WHERE session_id = %s",
                (title, session_id),
            )
            rowcount = cursor.rowcount
        self.connection.commit()
        return rowcount > 0


class SessionPersistenceManager:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or config
        self.backend = self.settings.session_checkpoint_backend.lower()
        self.checkpointer: Any = MemorySaver()
        self.session_store: PostgresSessionStore | None = None
        self.in_memory_store: InMemorySessionStore | None = None
        self.sqlite_store: SqliteSessionStore | None = None
        self._checkpoint_context: Any = None
        self._connection: Any = None

    def initialize(self) -> None:
        if self.backend == "memory":
            self.checkpointer = MemorySaver()
            self.in_memory_store = None
            self.sqlite_store = SqliteSessionStore(self.settings.session_db_path)
            self.sqlite_store.initialize()
            self.session_store = None
            logger.info("[SessionPersistence] 使用内存 checkpoint + SQLite 会话存储")
            return

        if self.backend != "postgres":
            raise ValueError(f"Unsupported SESSION_CHECKPOINT_BACKEND: {self.backend}")

        if not self.settings.postgres_dsn:
            raise ValueError(
                "POSTGRES_DSN must be configured when SESSION_CHECKPOINT_BACKEND=postgres"
            )

        self._initialize_postgres()

    async def initialize_async(self) -> None:
        if self.backend == "memory":
            self.checkpointer = MemorySaver()
            self.in_memory_store = None
            self.sqlite_store = SqliteSessionStore(self.settings.session_db_path)
            self.sqlite_store.initialize()
            self.session_store = None
            logger.info("[SessionPersistence] 使用内存 checkpoint + SQLite 会话存储")
            return

        if self.backend != "postgres":
            raise ValueError(f"Unsupported SESSION_CHECKPOINT_BACKEND: {self.backend}")

        if not self.settings.postgres_dsn:
            raise ValueError(
                "POSTGRES_DSN must be configured when SESSION_CHECKPOINT_BACKEND=postgres"
            )

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
        if self.sqlite_store is not None:
            self.sqlite_store.upsert_session(metadata)
            return
        if self.session_store is not None:
            self.session_store.upsert_session(metadata)
            return
        if self.in_memory_store is not None:
            self.in_memory_store.upsert_session(metadata)

    def upsert_agent_session(
        self,
        session_id: str,
        task: str,
        plan: list[str],
        steps: list[dict[str, str]],
        report: str,
        user_id: str = "",
    ) -> None:
        """持久化 Agent 模式（AIOps Plan-Execute-Replan）的完整执行记录。

        存储格式：
        - chat_sessions 表：title=task[:30]，preview=report[:80]（与 Chat 模式一致）
        - chat_messages 表：
          - role='user'，content=task
          - role='assistant'，content=JSON({"type":"agent","plan":[...],"steps":[...],"report":"..."})

        前端加载历史时检测 assistant content 是否为 agent JSON，是则渲染执行流程可视化，否则按普通文本处理。
        """
        import json

        flow_data = {
            "type": "agent",
            "plan": plan,
            "steps": steps,
            "report": report,
        }
        flow_json = json.dumps(flow_data, ensure_ascii=False)
        metadata = ChatSessionMetadata.from_agent_session(
            session_id=session_id,
            task=task,
            flow_json=flow_json,
            report=report,
            user_id=user_id,
        )
        if self.sqlite_store is not None:
            self.sqlite_store.upsert_session(metadata)
            return
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
        if self.sqlite_store is not None:
            return self.sqlite_store.list_sessions(limit=limit, offset=offset, user_id=user_id)
        if self.session_store is not None:
            return self.session_store.list_sessions(limit=limit, offset=offset, user_id=user_id)
        if self.in_memory_store is not None:
            return self.in_memory_store.list_sessions(limit=limit, offset=offset, user_id=user_id)
        return []

    def count_chat_sessions(self, user_id: str | None = None) -> int:
        if self.sqlite_store is not None:
            return self.sqlite_store.count_sessions(user_id=user_id)
        if self.session_store is not None:
            return self.session_store.count_sessions(user_id=user_id)
        if self.in_memory_store is not None:
            return self.in_memory_store.count_sessions(user_id=user_id)
        return 0

    def get_session_messages(self, session_id: str) -> list[dict[str, str]]:
        """获取会话的持久化消息记录（仅 SQLite 后端可用）。"""
        if self.sqlite_store is not None:
            return self.sqlite_store.get_messages(session_id)
        return []

    def delete_chat_session(self, session_id: str) -> None:
        if self.sqlite_store is not None:
            self.sqlite_store.delete_session(session_id)
        if self.session_store is not None:
            self.session_store.delete_session(session_id)
        if self.in_memory_store is not None:
            self.in_memory_store.delete_session(session_id)

    def rename_chat_session(self, session_id: str, title: str) -> bool:
        """重命名会话标题，返回是否成功。"""
        if self.sqlite_store is not None:
            return self.sqlite_store.rename_session(session_id, title)
        if self.session_store is not None:
            return self.session_store.rename_session(session_id, title)
        if self.in_memory_store is not None:
            return self.in_memory_store.rename_session(session_id, title)
        return False

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
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


session_persistence_manager = SessionPersistenceManager()
