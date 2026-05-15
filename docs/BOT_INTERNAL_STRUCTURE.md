# PropertyBot Internal Structure

`PropertyBot` in `telegram_bot/bot.py` is the main orchestrator for the Telegram bot. This document provides an internal map for navigation without relying on brittle line ranges.

## Class Overview

```
PropertyBot
├── __init__()              # Initialize all services
├── _register_handlers()    # Register commands, messages, callbacks, routers
├── _setup_dialogs()        # Include aiogram-dialog routers before catch-all text routing
├── _setup_middlewares()    # Configure middleware chain
├── handle_query()          # Main entry point for text queries
├── handle_voice()          # Entry point for voice messages
└── start()                 # Startup preflight, service init, polling
```

## Key Methods

### `__init__()`

Initializes all service dependencies:

```python
self._cache = CacheLayerManager(redis_url=...)
self._hybrid = BGEM3HybridEmbeddings(...)
self._qdrant = QdrantService(...)
self._reranker = None  # server-side Qdrant ColBERT is used when enabled
self._llm = self._graph_config.create_llm()
```

### `handle_query()`

Routes text queries through dual-path architecture:

```
handle_query()
├── _handle_client_direct_pipeline()  # Fast path for simple queries
└── _handle_query_supervisor()        # Full agent for complex queries
```

Find it with:

```bash
rg -n "async def handle_query|_handle_client_direct_pipeline|_handle_query_supervisor" telegram_bot/bot.py
```

### `handle_voice()`

Processes voice messages through LangGraph:

```
1. Download .ogg → bytes
2. make_initial_state(voice_audio=bytes, input_type="voice")
3. build_graph().ainvoke(state)
```

Find it with:

```bash
rg -n "async def handle_voice|voice_audio|make_initial_state|build_graph\\(" telegram_bot/bot.py
```

## Internal Handler Methods

### Menu & Callback Handlers

| Method | Purpose |
|--------|---------|
| `handle_menu_button()` | Routes ReplyKeyboard button presses |
| `handle_service_callback()` | Service card callbacks (`svc:`) |
| `handle_cta_callback()` | CTA action callbacks (`cta:`) |
| `handle_favorite_callback()` | Favorites callbacks (`fav:`) |
| `handle_results_callback()` | Results callbacks (`results:`) |
| `handle_feedback()` | Like/dislike feedback |
| `handle_clearcache_callback()` | Cache clear (`cc:`) |

### Command Handlers

| Command | Handler |
|---------|---------|
| `/start` | `cmd_start()` |
| `/help` | `cmd_help()` |
| `/clear` | `cmd_clear()` |
| `/clearcache` | `cmd_clearcache()` |
| `/stats` | `cmd_stats()` |
| `/metrics` | `cmd_metrics()` |

### FSM Handlers

- `PhoneCollector` — Phone number collection for lead capture
- Uses aiogram FSM for state management

## Query Flow

```
User Message
    ↓
ThrottlingMiddleware (rate limiting)
    ↓
ErrorMiddleware (exception handling)
    ↓
I18nMiddleware (locale detection)
    ↓
PropertyBot.handle_query()
    ├── Client role + simple query → run_client_pipeline()
    │                                   1. classify
    │                                   2. detect_agent_intent
    │                                   3. cache_check
    │                                   4. rag_pipeline
    │                                   5. generate_response
    │                                   6. post-process
    │
    └── Manager role OR complex → create_bot_agent()
                                          1. Build tools list
                                          2. Invoke agent
                                          3. Return response
```

## Service Dependencies (initialized in `__init__`)

| Service | Class | Purpose |
|---------|-------|---------|
| `self._cache` | CacheLayerManager | 5-tier Redis cache |
| `self._hybrid` | BGEM3HybridEmbeddings | Dense + sparse + ColBERT |
| `self._embeddings` | BGEM3HybridEmbeddings | Primary embedding provider |
| `self._sparse` | BGEM3SparseEmbeddings | Sparse embeddings |
| `self._qdrant` | QdrantService | Vector storage |
| `self._reranker` | None by default | Deprecated client-side reranker hook; server-side Qdrant ColBERT path is selected by `RERANK_PROVIDER=colbert` |
| `self._llm` | AsyncOpenAI | LLM client |
| `self._graph` | CompiledStateGraph | Voice LangGraph |
| `self._apartments_service` | ApartmentsService | Structured catalog search |
| `self._user_service` | UserService | User management |

## Middleware Stack

```
Update → ThrottlingMiddleware → ErrorMiddleware → I18nMiddleware → Handler
```

### ThrottlingMiddleware
- TTL cache (10,000 users, 1.5s TTL)
- Admins bypass throttling

### ErrorHandlerMiddleware
- Catches all exceptions
- Logs with `exc_info=True`
- Returns user-friendly message

### I18nMiddleware
- Loads user locale from DB
- Injects `i18n`, `locale`, `property_bot`, `apartments_service`

## Finding Code

Due to file size, use `rg` recipes instead of line-number maps:

```bash
# Find method definition
rg -n "async def handle_query|async def handle_voice|async def start|def _register_handlers" telegram_bot/bot.py

# Find class attribute initialization
rg -n "self\\._cache = |self\\._hybrid = |self\\._qdrant = |self\\._reranker =" telegram_bot/bot.py

# Find handler registration
rg -n "dp\\.message|dp\\.callback_query|include_router|Command\\(" telegram_bot/bot.py
```

## Related Documentation

- [Bot Architecture](BOT_ARCHITECTURE.md)
- [Client Pipeline](CLIENT_PIPELINE.md)
- [Pipeline Overview](PIPELINE_OVERVIEW.md)
