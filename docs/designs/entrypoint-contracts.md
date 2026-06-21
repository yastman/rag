# Entrypoint Contracts

## Overview

The assistant system has exactly two entrypoints:

1. **Direct core entrypoint**: `run_assistant_request()` — for Python/SDK callers
2. **Telegram adapter entrypoint**: `_supervisor_run_core()` → `run_core_text_request()` — for Telegram bot

This document defines what each entrypoint accepts, returns, and which adapters use which path.

## Direct Core Entrypoint: `run_assistant_request()`

### Location
- **Module**: `src.core.assistant`
- **Export**: Public via `src.core.__init__.py`

### Signature
```python
async def run_assistant_request(
    query: str,
    *,
    collection: str,
    user_context: UserContext | None = None,
    request_id: str | None = None,
    dependencies: CoreDependencies | None = None,
) -> AssistantResult:
```

### Contract
- **Input**:
  - `query`: Natural language user question
  - `collection`: Qdrant collection name for retrieval
  - `user_context`: Optional context (user_id, session_id, role, filters, language)
  - `request_id`: Optional request ID; auto-generated if not provided
  - `dependencies`: Optional `CoreDependencies` bundle; if not provided, executes in skeleton mode

- **Output**: `AssistantResult` containing:
  - `response_text`: Generated answer
  - `route`: Classification route (e.g., "answer", "error")
  - `request_type`: Query classification type
  - `request_id`: Request ID for tracing
  - `error_type` / `error_message`: Error info if route is "error"
  - `latency_ms`: Request latency
  - `cache_hit`: Whether response came from semantic cache
  - `rerank_applied`: Whether reranking was applied
  - `documents_count`: Number of documents retrieved
  - `retrieved_sources`: List of source documents with metadata

- **Behavior**:
  - Skeleton mode (no dependencies): Returns error result without touching live services
  - Live mode (dependencies provided): Executes full pipeline through `run_assistant_pipeline()`
  - Always emits product events (telemetry) at start and completion
  - Catches all exceptions and returns error result with traceback

### Callers
- Direct SDK tests (e.g., `tests/unit/core/test_assistant_entrypoint.py`)
- E2E core tests (e.g., `tests/e2e/test_core_live_ingest_answer.py`)
- `AssistantApp.run_text()` (which is called by adapters)

## Telegram Adapter Entrypoint Chain

### Location
- **Bot handler**: `PropertyBot._handle_query_supervisor()` in `telegram_bot/_bot_query_pipeline.py`
- **Core call**: `_supervisor_run_core()` → `run_core_text_request()` in `telegram_bot/_bot_query_pipeline.py`
- **Adapter helper**: `telegram_bot/assistant_core_adapter.py`

### Call Chain
```
PropertyBot.handle_query()
  ↓
_handle_query_supervisor()  (Supervisor agent orchestration)
  ↓
_supervisor_run_core()  (Telegram entry into core pipeline)
  ↓
run_core_text_request()  (Telegram adapter for run_assistant_request)
  ↓
AssistantApp.run_text()
  ↓
run_assistant_request()  (Direct core entrypoint)
```

### Input Transformation
- **Telegram message** → extracted to:
  - `user_text`: message content
  - `user_id`: chat user ID
  - `session_id`: Telegram session ID
  - `role`: user role (e.g., "client")
  - `extracted_filters`: pre-agent filter extraction results
  - `language`: user language preference

- **User context built**: `build_user_context()`
- **Dependencies provided**: `CoreDependencies` from bot's runtime clients

### Output Handling
- Core returns `AssistantResult`
- Telegram adapter extracts `response_text`
- Sends via `bot.send_message()` to Telegram chat

## Relationship

Both entrypoints **call the same function**: `run_assistant_request()`.

- **Direct SDK path**: Caller → `run_assistant_request()` (direct call)
- **Telegram path**: Telegram bot → Telegram adapter → `AssistantApp` → `run_assistant_request()` (wrapped call)

The difference is:
- **SDK path**: Direct, for testing and embedding
- **Telegram path**: Wrapped through `AssistantApp`, with transport-specific context extraction and response rendering

## Invariants

1. **One core logic**: Both paths execute identical core pipeline; differences are in transport (Telegram vs. SDK) and context extraction (filters, language, role).
2. **No direct runtime access from Telegram**: Telegram adapter never imports `src.runtime` directly; all runtime access goes through the `CoreDependencies` object passed to the core.
3. **Skeleton mode is testable**: Both paths can run in skeleton mode (no dependencies) for fast unit tests.
4. **Telemetry is consistent**: Both paths emit identical product events at start and completion.

## Guarded by

- `tests/contract/test_entrypoint_contract.py` — asserts structure and prevents regression
