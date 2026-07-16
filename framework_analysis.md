## Overview
The reference project at `C:\Users\86176\Desktop\阳光实习\helper` is a FastAPI + vanilla-JS RAG Q&A assistant ("智能问答助手"). It has a chat UI, knowledge-base management, feedback/bug systems, and an admin backend. The "近期对话" (recent conversations) feature is a full multi-session chat-history system with **dual storage** (browser localStorage + server SQLite) and an admin viewer.

## Full Directory Structure (key parts)
```
helper/
├── app/                          # Backend (FastAPI)
│   ├── main.py                   # App entry, route registration, lifespan (inits session_persistence)
│   ├── run_server.py, config.py, __init__.py
│   ├── api/                      # Route files
│   │   ├── chat.py               # ★ Chat + session-history endpoints
│   │   ├── admin.py              # Admin timeline (Bug+Feedback merge)
│   │   ├── feedback.py, bug.py, file.py, aiops.py, health.py
│   ├── core/
│   │   ├── session_persistence.py# ★★ DB models + session stores (the core of conversation storage)
│   │   ├── llm_factory.py, milvus_client.py, windows_event_loop.py
│   ├── models/
│   │   ├── request.py            # ChatRequest, ClearRequest, RenameSessionRequest ...
│   │   ├── response.py           # SessionInfoResponse, ChatSessionListResponse, ChatSessionSummary ...
│   │   ├── aiops.py, document.py
│   ├── services/
│   │   ├── rag_agent_service.py  # ★ RAG query + get_session_history_async + upsert calls
│   │   ├── feedback_service.py, bug_service.py, + vector/RAG services
│   ├── agent/, tools/, utils/
├── static/                       # Frontend
│   ├── index.html                # ★ Main chat UI (sidebar "近期对话")
│   ├── app.js                    # ★★ SmartQAApp - all conversation JS
│   ├── admin.html                # ★★ Admin backend (会话列表 tab + feedback context viewer)
│   └── styles.css
├── data/
│   ├── chat_sessions.db          # ★ SQLite: chat_sessions + chat_messages tables
│   ├── bug.db, feedback.db
├── tests/
│   ├── test_session_persistence.py, test_chat_sessions_api.py, test_rag_session_history.py, test_admin_timeline.py
```

## 1. Frontend — "近期对话" (static/index.html + static/app.js)
`index.html` sidebar contains `#newChatBtn` ("新建对话") and `#chatHistoryList` under a "近期对话" header. `app.js` defines class `SmartQAApp`.

**Session ID per window:** generated client-side, so each browser tab/window is its own session:
```js
generateSessionId() { return 'session_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now(); }
```

**Dual storage (localStorage + server):**
- `loadChatHistories()` / `saveChatHistories()` → `localStorage['chatHistories']` (max 50 entries).
- `loadServerChatHistories()` → on init fetches `GET /api/chat/sessions`, merges server data with local (preserving local `messages`/`citations`/`messageId`), sorts by `updatedAt` desc, re-renders.

**Saving a conversation** (`saveCurrentChat`): title = first user message truncated to 30 chars; stores `{id, title, messages, createdAt, updatedAt}`. `updateCurrentChatHistory()` updates an existing entry.

**Rendering sidebar** (`renderChatHistory`): each item has rename (pencil) + delete (X) buttons and click-to-load. Rename → `PUT /api/chat/session/{id}/rename`. Delete → `POST /api/chat/clear` `{sessionId}`.

**Loading a session** (`loadChatHistory`): prefers local `messages` (keeps citations/messageId); if local empty, fetches `GET /api/chat/session/{id}` and maps `role==='user'`→type user. Sets `isCurrentChatFromHistory=true`, re-renders messages via `addMessage`.

**Streaming send** (`sendStreamMessage`): POSTs `{Id: sessionId, Question: message}` to `/api/chat_stream`, parses SSE events `retrieving`/`search_results`/`content`/`done`/`error`. On `done`, `handleStreamComplete` pushes the assistant message (with `messageId` + `citations`) into `currentChatHistory` and saves.

## 2. Backend Chat/Session API (app/api/chat.py)
Endpoints (all prefixed `/api`):
- `POST /chat` — non-streaming RAG answer
- `POST /chat_stream` — SSE streaming (EventSourceResponse)
- `POST /chat/clear` — delete a session (`ClearRequest.sessionId`)
- `GET /chat/sessions?limit=&offset=&user_id=` → `ChatSessionListResponse` (lists recent sessions, paginated)
- `GET /chat/session/{session_id}` → `SessionInfoResponse` (full message history)
- `PUT /chat/session/{session_id}/rename` → `ApiResponse` (`RenameSessionRequest.title`)
- `GET /chat/suggestions` — popular questions from feedback likes

## 3. Database Models & Schema (app/core/session_persistence.py) — THE KEY FILE
Three interchangeable stores behind `SessionPersistenceManager`, chosen by `SESSION_CHECKPOINT_BACKEND` config. **Default ("memory" backend) uses SQLite** for session metadata+messages, plus a LangGraph `MemorySaver` checkpointer for live agent state.

`SqliteSessionStore` (DB at `data/chat_sessions.db`) creates two tables:
```sql
CREATE TABLE chat_sessions (
    session_id TEXT PRIMARY KEY, title TEXT DEFAULT '新对话',
    created_at TEXT, updated_at TEXT,
    last_message_preview TEXT DEFAULT '', message_count INTEGER DEFAULT 0, user_id TEXT DEFAULT '')
CREATE TABLE chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT,
    content TEXT, created_at TEXT)
-- indexes: idx_chat_messages_session, idx_chat_sessions_updated_at(DESC), idx_chat_sessions_user_id
```
- `upsert_session(metadata)`: upserts `chat_sessions` (preserves first-round title; only overwrites if title empty/"新对话"; increments `message_count`), then **appends two rows** to `chat_messages` (role `user` = question, role `assistant` = answer).
- `get_messages(session_id)`: `SELECT role, content, created_at ... ORDER BY id ASC` → `{role, content, timestamp}`.
- `list_sessions`: `ORDER BY updated_at DESC LIMIT ? OFFSET ?`, optional `user_id` filter.
- `rename_session` / `delete_session` (deletes from both tables).
- `PostgresSessionStore` mirrors this for production (note: Postgres store does NOT persist per-message rows — only session metadata; messages come from the checkpointer there).
- `InMemorySessionStore`: dict-based, metadata only, lost on restart.

`SessionPersistenceManager` (singleton `session_persistence_manager`) facade methods: `upsert_chat_session`, `list_chat_sessions`, `count_chat_sessions`, `get_session_messages` (SQLite only), `delete_chat_session`, `rename_chat_session`. Initialized in `main.py` lifespan via `initialize_async()`; the checkpointer is injected into `rag_agent_service.configure_checkpointer(...)`.

## 4. How conversations are stored per session/window
1. Client generates `sessionId` per window, sends it as `Id` in every `/chat_stream` call.
2. `rag_agent_service.query_stream()` runs the LangGraph RAG agent (checkpointer keyed by `thread_id=session_id` gives multi-turn memory), then after the answer completes calls:
   ```python
   session_persistence_manager.upsert_chat_session(session_id=session_id, question=question, answer=full_response)
   ```
   This writes the human-readable session row + the two message rows to SQLite. `message_id = f"msg_{session_id}_{timestamp_ms}"` is returned to the frontend for feedback linking.

## 5. How conversation history is retrieved
`rag_agent_service.get_session_history_async(session_id)` (chat.py `GET /chat/session/{id}` calls this):
1. **First tries SQLite** via `session_persistence_manager.get_session_messages(session_id)` — survives restarts.
2. **Falls back to the LangGraph checkpointer** (for postgres backend / in-memory runtime sessions) via `_checkpoint_to_history()`, which skips `SystemMessage`/`ToolMessage` and AIMessages with tool_calls, extracts the real user question out of the prompt template (`_extract_user_question` splits on "用户的问题："), returns `{role, content, timestamp}`.

## 6. Admin backend displaying conversation history (static/admin.html, served at `/admin`)
The admin page has tabs; conversation history is shown in two places, **both reusing the same `/api/chat/sessions` and `/api/chat/session/{id}` endpoints** (no separate admin chat endpoints):

- **"💬 会话列表" tab** — `loadSessions()` calls `GET /api/chat/sessions?limit=PAGE_SIZE&offset=`, renders a table (会话ID, 标题, 消息数, 最后消息预览, 创建时间, "查看历史" button). `viewSessionDetail(sessionId)` calls `GET /api/chat/session/{id}` and renders the full 👤用户/🤖助手 conversation in modal `#sessionDetailModal`. `loadSessionsMore()` paginates.
- **反馈 context viewer** — `viewFeedbackContext(idx)` fetches `GET /api/chat/session/{sessionId}` for a feedback item's session, tries to match the feedback's `question` to locate the turn, and shows the conversation from round 1 → the matched turn (with a warning if no exact match), in modal `#feedbackContextModal`.
- **"全部" timeline** — `GET /api/admin/timeline` (admin.py) merges Bug + Feedback records sorted by `created_at` desc; feedback timeline items carry `session_id` and `message_id` so admins can jump to the related conversation. `admin.py` only defines `/admin/timeline` — the actual conversation listing/detail in admin uses the chat router's endpoints.

## Data Models (app/models/request.py, response.py)
- `ChatRequest`: `id` (alias `Id`), `question` (alias `Question`)
- `ClearRequest`: `session_id` (alias `sessionId`)
- `RenameSessionRequest`: `title` (1–100 chars)
- `SessionInfoResponse`: `session_id`, `message_count`, `history: List[{role,content,timestamp}]`
- `ChatSessionSummary`: `session_id, title, created_at, updated_at, last_message_preview, message_count`
- `ChatSessionListResponse`: `total, limit, offset, sessions`

## Key takeaway for replication
To replicate "近期对话": (a) generate a per-window session ID client-side; (b) persist sessions in SQLite with a `chat_sessions` (metadata) + `chat_messages` (per-message) schema; (c) expose `GET /sessions` (list, paginated, ordered by updated_at desc) and `GET /session/{id}` (full messages) plus rename/clear endpoints; (d) on the frontend keep a localStorage mirror merged with server data, preferring local messages to retain citations/messageId; (e) for the admin, reuse the same list/detail endpoints in a sessions tab and link feedback/bug timeline items back via `session_id`.