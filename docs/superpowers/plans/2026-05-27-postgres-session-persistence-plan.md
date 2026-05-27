# PostgreSQL Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Persist SuperBizAgent chat and AIOps LangGraph state in PostgreSQL with server-side session history metadata.

**Architecture:** Add an explicit `SESSION_CHECKPOINT_BACKEND=memory|postgres` switch. Memory mode keeps the current `MemorySaver` behavior; postgres mode initializes PostgreSQL checkpoint/session persistence at startup and fails fast if unavailable. A session index table provides frontend history listing while LangGraph checkpoint state remains the authoritative Agent memory.

**Tech Stack:** FastAPI, LangChain/LangGraph, PostgreSQL, `langgraph-checkpoint-postgres`, `psycopg`, native browser JavaScript, pytest.

---

## File Structure

- Modify: `pyproject.toml` — add PostgreSQL checkpoint dependencies.
- Modify: `app/config.py` — add checkpoint backend and PostgreSQL settings.
- Create: `app/core/session_persistence.py` — central persistence lifecycle, checkpointer factory, and PostgreSQL session index store.
- Modify: `app/main.py` — initialize/close persistence during FastAPI lifespan.
- Modify: `app/services/rag_agent_service.py` — use shared checkpointer and upsert/clear session index.
- Modify: `app/services/aiops_service.py` — use shared checkpointer.
- Modify: `app/models/response.py` — add session metadata response models.
- Modify: `app/api/chat.py` — add session listing endpoint and integrate clear/list APIs with session index.
- Modify: `static/app.js` — load server-side sessions on startup and keep localStorage as fallback.
- Create: `tests/test_session_persistence.py` — unit tests for backend selection and session index SQL behavior.
- Create: `tests/test_chat_sessions_api.py` — API-level tests for session listing.
- Modify: `project-docs/*.md` — update project docs with new persistence architecture and verification.

---

### Task 1: Add configuration and dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/config.py`
- Test: `tests/test_session_persistence.py`

- [x] **Step 1: Write failing config tests**

Create `tests/test_session_persistence.py` with tests that instantiate `Settings` directly and assert the default backend is memory and postgres settings can be configured:

```python
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
```

- [x] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_session_persistence.py -q --no-cov`

Expected: FAIL because `session_checkpoint_backend` and `is_postgres_checkpoint_enabled` do not exist yet.

- [x] **Step 3: Add dependencies**

Add these dependencies to `pyproject.toml` inside `[project].dependencies`:

```toml
    "langgraph-checkpoint-postgres>=2.0.0",
    "psycopg[binary,pool]>=3.2.0",
```

- [x] **Step 4: Add settings**

Add these fields to `Settings` in `app/config.py` after the Milvus config block:

```python
    # 会话持久化配置
    session_checkpoint_backend: str = "memory"
    postgres_dsn: str = ""
    postgres_pool_min_size: int = 1
    postgres_pool_max_size: int = 5
    postgres_connect_timeout_seconds: float = 10.0
```

Add this property near other properties:

```python
    @property
    def is_postgres_checkpoint_enabled(self) -> bool:
        return self.session_checkpoint_backend.lower() == "postgres"
```

- [x] **Step 5: Run tests and verify pass**

Run: `python -m pytest tests/test_session_persistence.py -q --no-cov`

Expected: PASS.

---

### Task 2: Implement persistence core and session index

**Files:**
- Create: `app/core/session_persistence.py`
- Modify: `tests/test_session_persistence.py`

- [x] **Step 1: Add failing tests for memory backend and session metadata**

Append these tests to `tests/test_session_persistence.py`:

```python
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
```

- [x] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_session_persistence.py -q --no-cov`

Expected: FAIL because `app.core.session_persistence` does not exist.

- [x] **Step 3: Implement `app/core/session_persistence.py`**

Create the module with:

```python
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
        self._connection = connect(
            self.settings.postgres_dsn,
            autocommit=False,
            connect_timeout=int(self.settings.postgres_connect_timeout_seconds),
        )
        self.checkpointer = PostgresSaver(self._connection)
        self.checkpointer.setup()
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


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


session_persistence_manager = SessionPersistenceManager()
```

- [x] **Step 4: Run tests and verify pass**

Run: `python -m pytest tests/test_session_persistence.py -q --no-cov`

Expected: PASS.

---

### Task 3: Wire persistence into app lifecycle and services

**Files:**
- Modify: `app/main.py`
- Modify: `app/services/rag_agent_service.py`
- Modify: `app/services/aiops_service.py`
- Test: existing tests plus import checks

- [x] **Step 1: Update app lifecycle**

In `app/main.py`, import manager:

```python
from app.core.session_persistence import session_persistence_manager
```

In `lifespan`, before connecting Milvus:

```python
    logger.info("[SessionPersistence] 正在初始化会话持久化...")
    session_persistence_manager.initialize()
    logger.info("[SessionPersistence] 会话持久化初始化完成")
```

On shutdown before final close log:

```python
    logger.info("[SessionPersistence] 正在关闭会话持久化...")
    session_persistence_manager.close()
```

- [x] **Step 2: Update `RagAgentService` imports and checkpointer**

Replace `MemorySaver` import/use in `app/services/rag_agent_service.py` with:

```python
from app.core.session_persistence import session_persistence_manager
```

Set:

```python
        self.checkpointer = session_persistence_manager.checkpointer
```

After successful non-stream answer before return:

```python
                session_persistence_manager.upsert_chat_session(
                    session_id=session_id,
                    question=question,
                    answer=answer,
                )
```

In `query_stream`, collect `full_response` while yielding content and upsert after streaming completes:

```python
            full_response = ""
```

Append each yielded text chunk to `full_response`, then before complete:

```python
            session_persistence_manager.upsert_chat_session(
                session_id=session_id,
                question=question,
                answer=full_response,
            )
```

In `clear_session`, after deleting checkpointer thread:

```python
            session_persistence_manager.delete_chat_session(session_id)
```

- [x] **Step 3: Update `AIOpsService` checkpointer**

Replace `MemorySaver` import/use in `app/services/aiops_service.py` with:

```python
from app.core.session_persistence import session_persistence_manager
```

Set:

```python
        self.checkpointer = session_persistence_manager.checkpointer
```

- [x] **Step 4: Run import compile checks**

Run: `python -m py_compile app/config.py app/core/session_persistence.py app/main.py app/services/rag_agent_service.py app/services/aiops_service.py`

Expected: exit code 0.

---

### Task 4: Add sessions API models and endpoint

**Files:**
- Modify: `app/models/response.py`
- Modify: `app/api/chat.py`
- Test: `tests/test_chat_sessions_api.py`

- [x] **Step 1: Write failing API test**

Create `tests/test_chat_sessions_api.py`:

```python
from fastapi.testclient import TestClient

from app.api.chat import router
from app.core.session_persistence import session_persistence_manager
from fastapi import FastAPI


def test_list_chat_sessions_returns_manager_data(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    monkeypatch.setattr(
        session_persistence_manager,
        "list_chat_sessions",
        lambda limit=50: [
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

    response = client.get("/api/chat/sessions")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["sessions"][0]["session_id"] == "session-1"
    assert body["sessions"][0]["title"] == "CPU 排查"
```

- [x] **Step 2: Run test and verify failure**

Run: `python -m pytest tests/test_chat_sessions_api.py -q --no-cov`

Expected: FAIL because `/api/chat/sessions` does not exist.

- [x] **Step 3: Add response models**

Append to `app/models/response.py`:

```python
class ChatSessionSummary(BaseModel):
    """聊天会话摘要"""

    session_id: str = Field(..., description="会话 ID")
    title: str = Field(..., description="会话标题")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    last_message_preview: str = Field("", description="最后消息摘要")
    message_count: int = Field(0, description="消息数量")


class ChatSessionListResponse(BaseModel):
    """聊天会话列表响应"""

    total: int = Field(..., description="会话总数")
    sessions: List[ChatSessionSummary] = Field(default_factory=list, description="会话列表")
```

- [x] **Step 4: Add endpoint**

In `app/api/chat.py`, import `ChatSessionListResponse` and `session_persistence_manager`, then add before `/chat/session/{session_id}`:

```python
@router.get("/chat/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(limit: int = 50) -> ChatSessionListResponse:
    try:
        safe_limit = max(1, min(limit, 100))
        sessions = session_persistence_manager.list_chat_sessions(limit=safe_limit)
        return ChatSessionListResponse(total=len(sessions), sessions=sessions)
    except Exception as e:
        logger.error(f"获取会话列表错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

- [x] **Step 5: Run API test and verify pass**

Run: `python -m pytest tests/test_chat_sessions_api.py -q --no-cov`

Expected: PASS.

---

### Task 5: Update frontend to prefer server sessions

**Files:**
- Modify: `static/app.js`

- [x] **Step 1: Add async server session loading call**

In constructor, after `this.renderChatHistory();`, call:

```javascript
        this.loadServerChatHistories();
```

Add method near `loadChatHistories()`:

```javascript
    async loadServerChatHistories() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/chat/sessions`);
            if (!response.ok) {
                return;
            }
            const data = await response.json();
            const sessions = data.sessions || [];
            if (sessions.length === 0) {
                return;
            }
            this.chatHistories = sessions.map(session => ({
                id: session.session_id,
                title: session.title || '新对话',
                messages: [],
                createdAt: session.created_at,
                updatedAt: session.updated_at,
                lastMessagePreview: session.last_message_preview || '',
                messageCount: session.message_count || 0
            }));
            this.saveChatHistories();
            this.renderChatHistory();
        } catch (error) {
            console.warn('加载服务端历史对话失败，继续使用本地缓存:', error);
        }
    }
```

- [x] **Step 2: Refresh server sessions after successful responses**

After quick response adds assistant message, call:

```javascript
                    this.loadServerChatHistories();
```

After stream complete handling in `sendStreamMessage`, call:

```javascript
                        this.loadServerChatHistories();
```

- [x] **Step 3: Run syntax check by compiling JS through Node if available**

Run: `node --check static/app.js`

Expected: exit code 0 if Node is installed. If Node is unavailable, record that JS syntax check was skipped.

---

### Task 6: Update project docs and verify all relevant tests

**Files:**
- Modify: `project-docs/project_overview.md`
- Modify: `project-docs/task_plan.md`
- Modify: `project-docs/findings.md`
- Modify: `project-docs/progress.md`

- [x] **Step 1: Update docs**

Update docs to state:

- RAG and AIOps no longer have to use process-local memory only.
- `SESSION_CHECKPOINT_BACKEND=postgres` enables PostgreSQL checkpoint persistence.
- `SESSION_CHECKPOINT_BACKEND=memory` preserves current behavior.
- PostgreSQL mode fails fast on startup if `POSTGRES_DSN` or DB initialization fails.
- Frontend history list prefers `GET /api/chat/sessions` and keeps localStorage fallback.

- [x] **Step 2: Run focused tests**

Run:

```powershell
python -m pytest tests/test_session_persistence.py tests/test_chat_sessions_api.py -q --no-cov
```

Expected: PASS.

- [x] **Step 3: Run existing relevant tests**

Run:

```powershell
python -m pytest tests/test_openai_compatible_config.py tests/test_rag_retrieval_service.py -q --no-cov
```

Expected: PASS.

- [x] **Step 4: Run compile checks**

Run:

```powershell
python -m py_compile app/config.py app/core/session_persistence.py app/main.py app/api/chat.py app/models/response.py app/services/rag_agent_service.py app/services/aiops_service.py
```

Expected: exit code 0.

- [x] **Step 5: Run diff hygiene**

Run:

```powershell
git diff --check
```

Expected: no whitespace errors.


---

## Implementation Result

Implemented and merged on 2026-05-27.

Key outcomes:

- Added `SESSION_CHECKPOINT_BACKEND=memory|postgres` with default `memory` behavior.
- Added PostgreSQL checkpointer initialization through `app/core/session_persistence.py`.
- Added lightweight `chat_sessions` index table for frontend history listing.
- Integrated the shared checkpointer into RAG Chat and AIOps services during FastAPI lifespan startup.
- Added `GET /api/chat/sessions` and response models for server-side session summaries.
- Updated `static/app.js` to prefer server-side session history with `localStorage` fallback.
- Updated `README.md`, `project-docs/`, and created `project-docs/2026-05-27-postgres-session-persistence-summary.md`.

Verification performed:

```powershell
python -m pytest tests/test_session_persistence.py tests/test_chat_sessions_api.py tests/test_rag_session_history.py tests/test_openai_compatible_config.py tests/test_rag_retrieval_service.py -q --no-cov
python -m py_compile app/config.py app/core/session_persistence.py app/main.py app/api/chat.py app/models/response.py app/services/rag_agent_service.py app/services/aiops_service.py
node --check static/app.js
git diff --check
```

Result: all commands exited with code 0 in the feature worktree before merge.
