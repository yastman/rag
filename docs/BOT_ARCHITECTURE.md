# PropertyBot Architecture

**File:** `telegram_bot/bot.py` (5013 lines)

Main Telegram bot entry point combining aiogram 3 dispatcher with LangGraph pipeline.

## High-Level Structure

```
PropertyBot class (472+)
    ├── __init__() — bot, dispatcher, services init
    ├── _register_routers() — handler registration
    ├── _setup_dialogs() — aiogram-dialog setup
    ├── _setup_middlewares() — middleware chain
    └── run() — start polling
```

## Key Classes

### `PropertyBot`

Main bot orchestrator. Initializes:
- `Bot` instance with configured token
- `Dispatcher` with FSM storage (Redis or memory)
- All service layers (cache, embeddings, LLM, Qdrant)
- Graph pipeline via `build_graph()`

### Lazy Import Wrappers

| Function | Wraps | Purpose |
|----------|-------|---------|
| `create_bot_agent()` | `agents/agent.py:create_bot_agent` | Agent factory for tests |
| `build_graph()` | `graph/graph.py:build_graph` | Graph builder for tests |
| `classify_query()` | `graph/nodes/classify.py:classify_query` | Query classifier for tests |
| `detect_injection()` | `graph/nodes/guard.py:detect_injection` | Injection detector for tests |

## Key Functions

| Function | Lines | Purpose |
|----------|-------|---------|
| `_stream_agent_to_draft()` | 129–185 | Stream agent output to Telegram drafts |
| `_merge_results()` | 187–206 | Deduplicate search results |
| `_state_apartment_results()` | 207–220 | Extract apartment list from state |
| `_split_telegram_response()` | 235–247 | Split long messages at 4096 char limit |
| `_supervisor_thread_id()` | 248–254 | Build forum thread ID for supervisor |
| `_delete_checkpointer_thread()` | 255–271 | Cleanup stale checkpoint threads |
| `_extract_current_turn()` | 272–287 | Extract last user/assistant turn |
| `_build_trace_metadata()` | 288–329 | Build Langfuse trace metadata |
| `_write_voice_error_scores()` | 330–351 | Score voice errors in Langfuse |
| `_is_post_pipeline_cleanup_error()` | 352–388 | Detect cleanup errors |
| `_is_checkpointer_runtime_error()` | 389–416 | Detect checkpoint errors |
| `_extract_stream_chunk_text()` | 417–443 | Extract text from stream chunks |

## Module Imports

**Core aiogram:**
- `Bot`, `Dispatcher` from aiogram
- `F` filters for routing
- `Command`, `CommandStart`, `StateFilter` filters
- `FSMContext`, `CallbackQuery`, `Message` types

**Business services:**
- `src.retrieval.topic_classifier` — query topic hint
- `telegram_bot.handlers.handoff` — HITL qualification
- `telegram_bot.services.cache_policy` — semantic cache
- `telegram_bot.services.handoff_state` — HandoffData, HandoffState
- `telegram_bot.services.metrics` — PipelineMetrics
- `telegram_bot.scoring` — compute/write scores

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `_CHECKPOINT_NS_VOICE` | `"tg:voice:v1"` | Voice checkpoint namespace |
| `_FEEDBACK_CONFIRMATION_TTL_S` | `5.0` | Feedback confirmation window |
| `_APARTMENT_PAGE_SIZE` | `5` | Apartments per page |
| `_STALE_RESULTS_CALLBACK_TEXT` | Russian | Stale button warning |
| `_TELEGRAM_MESSAGE_LIMIT` | `4096` | Telegram message char limit |
| `_NO_RAG_QUERY_TYPES` | `{"CHITCHAT", "OFF_TOPIC"}` | Queries bypass RAG |
| `_AGENT_DRAFT_INTERVAL` | `0.2` | Seconds between draft updates |

## Handler Registration Order

1. Menu button handlers (`F.text.in_`)
2. FSM handlers
3. Catch-all (`StateFilter(None)`)

## FSM States

Defined in `telegram_bot/handlers/handoff.py`:
- `HandoffStates` — qualification flow states

## Middleware Chain

1. `setup_error_handler` — exception → user-friendly message
2. `setup_throttling_middleware` — rate limiting
3. `FSMCancelMiddleware` — cancel FSM on /cancel
4. `LangfuseContextMiddleware` — trace context injection

## Graph Integration

`PropertyBot` builds the LangGraph pipeline via `build_graph()`:

```
START → classify → guard → cache_check → retrieve → grade
                           ↓                           ↓
                      chitchat/off-topic          rerank/rewrite/generate
                           ↓                           ↓
                         respond ←←←←←←←←← cache_store ←←←←←←
```

## Testing Pattern

Lazy wrappers allow patching without importing heavy dependencies:

```python
from telegram_bot import bot

# Patch for tests
bot.build_graph = mock_build_graph
```
