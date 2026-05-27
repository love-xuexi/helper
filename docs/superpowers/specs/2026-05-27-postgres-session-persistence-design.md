# PostgreSQL Session Persistence Design

## Goal

Use PostgreSQL to persist LangGraph conversation and workflow state so SuperBizAgent can survive service restarts without losing chat memory. The implementation uses explicit backend selection:

- `SESSION_CHECKPOINT_BACKEND=memory`: keep current in-process behavior.
- `SESSION_CHECKPOINT_BACKEND=postgres`: require PostgreSQL; startup fails if PostgreSQL is unavailable or initialization fails.

## Recommended Approach

Implement option B: PostgreSQL checkpointer plus a lightweight server-side session index.

The LangGraph checkpointer remains the authoritative Agent state store. A separate session index stores user-facing metadata for the web UI, such as session id, title, created time, updated time, last message preview, and message count.

## Architecture

### Configuration

Add settings in `app/config.py`:

- `session_checkpoint_backend`
- `postgres_dsn`
- PostgreSQL pool and timeout settings

### Persistence Core

Add a checkpoint/persistence module that:

1. Creates `MemorySaver` in memory mode.
2. Creates and initializes PostgreSQL checkpointer in postgres mode.
3. Exposes lifecycle hooks for startup and shutdown.
4. Fails fast in postgres mode when connection or setup fails.

### Session Index

Add a service-backed PostgreSQL table for frontend history metadata. The table is not the Agent memory source; it is an index for listing and managing sessions.

Fields:

- `session_id`
- `title`
- `created_at`
- `updated_at`
- `last_message_preview`
- `message_count`

### RAG Chat Flow

1. Frontend sends `Id` and `Question`.
2. Backend invokes the RAG Agent with `thread_id=session_id`.
3. LangGraph writes checkpoint state to the selected backend.
4. Backend upserts the session index after successful response generation.
5. Frontend can list sessions from the backend instead of relying only on `localStorage`.

### AIOps Flow

`AIOpsService` uses the same selected checkpointer mechanism, so Plan-Execute-Replan workflow state is also persisted by `thread_id=session_id` in postgres mode.

## API Changes

Keep existing APIs:

- `POST /api/chat`
- `POST /api/chat_stream`
- `POST /api/chat/clear`
- `GET /api/chat/session/{session_id}`

Add:

- `GET /api/chat/sessions`: list server-side sessions sorted by latest update time.

## Frontend Changes

On startup, the frontend loads session metadata from `GET /api/chat/sessions`. Server-side history becomes the preferred source when available. `localStorage` remains a compatibility fallback.

## Error Handling

- In memory mode, behavior remains unchanged.
- In postgres mode, startup fails if PostgreSQL is not reachable or schema initialization fails.
- Per-request persistence errors are logged and returned as API errors where they affect correctness.

## Testing

Add tests for:

- Config parsing and backend selection.
- Memory backend compatibility.
- Session index create/update/list/delete behavior with mocked database calls.
- Chat API session listing and clearing behavior.
- Existing RAG behavior remaining compatible with `thread_id=session_id`.

## Documentation Updates

Update `project-docs/` to record the new PostgreSQL session persistence architecture, configuration, behavior, and verification commands.


## Implementation Status

Implemented on 2026-05-27 and merged into `main`.

The implementation follows option B: LangGraph PostgreSQL checkpointing plus a lightweight `chat_sessions` index table. Documentation was updated in `README.md` and `project-docs/2026-05-27-postgres-session-persistence-summary.md`.
