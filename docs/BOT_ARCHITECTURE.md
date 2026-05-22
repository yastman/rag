# PropertyBot Architecture

**File:** `telegram_bot/bot.py`

Main Telegram bot entry point combining aiogram 3 dispatcher with LangGraph pipeline.

## High-Level Structure

```
PropertyBot
    ├── __init__() — bot, dispatcher, services init
    ├── _register_handlers() — command/message/callback handler registration
    ├── _setup_dialogs() — aiogram-dialog setup
    ├── _setup_middlewares() — middleware chain
    └── start() — dependency preflight, service startup, and polling
```

## Key Classes

### `PropertyBot`

Main bot orchestrator. Initializes:
- `Bot` instance with configured token
- `Dispatcher` with FSM storage (Redis or memory)
- All service layers (cache, embeddings, LLM, Qdrant)
- Graph pipeline via `build_graph()`

Navigation:

```bash
rg -n "class PropertyBot|def _register_handlers|async def start|async def handle_query|async def handle_voice" telegram_bot/bot.py
rg -n "build_graph\\(|setup_.*middleware|include_router|callback_query|Command\\(" telegram_bot/bot.py
```

### Lazy Import Wrappers

| Function | Wraps | Purpose |
|----------|-------|---------|
| `create_bot_agent()` | `agents/agent.py:create_bot_agent` | Agent factory for tests |
| `build_graph()` | `graph/graph.py:build_graph` | Graph builder for tests |
| `classify_query()` | `graph/nodes/classify.py:classify_query` | Query classifier for tests |
| `detect_injection()` | `graph/nodes/guard.py:detect_injection` | Injection detector for tests |

## Helper Areas

`telegram_bot/bot.py` is large and helper names move over time. Prefer lookup recipes over line tables:

```bash
rg -n "def _stream|def _merge|def _split|trace_metadata|voice_error|checkpointer" telegram_bot/bot.py
rg -n "handle_.*callback|cmd_|StateFilter|F\\.data|FeedbackCB|FavoriteCB" telegram_bot/bot.py
```

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

## Handler Registration

`_register_handlers()` wires command handlers, voice handling, menu button handlers, callback handlers, and feature routers. The catch-all text handler is registered on a dedicated router that is included after dialog routers, so aiogram-dialog message inputs can match before general text processing.

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
START → transcribe? → classify
                    ↓
       CHITCHAT/OFF_TOPIC → respond
                    ↓
                  guard? → cache_check → retrieve → grade
                                               ↓
                                      rerank / rewrite / generate
                                               ↓
                                         cache_store → respond
```

## Testing Pattern

Lazy wrappers allow patching without importing heavy dependencies:

```python
from telegram_bot import bot

# Patch for tests
bot.build_graph = mock_build_graph
```
