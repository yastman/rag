***REMOVED*** middlewares/

Aiogram middlewares for the Telegram bot: observability, error handling, and rate limiting.

***REMOVED******REMOVED*** Purpose

Wrap every Telegram update in cross-cutting concerns before handlers run.

***REMOVED******REMOVED*** Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Middleware exports |
| [`langfuse_middleware.py`](./langfuse_middleware.py) | Creates a Langfuse trace root for every Telegram update (outer middleware) |
| [`error_handler.py`](./error_handler.py) | Centralized exception handling with user-friendly error messages and Langfuse error reporting |
| [`throttling.py`](./throttling.py) | Rate limiting using TTLCache (1.5s window, admin bypass) |

***REMOVED******REMOVED*** Boundaries

- Middlewares are **transport-layer only**. They must not contain retrieval logic, LLM calls, or business rules.
- `LangfuseContextMiddleware` is installed as **outer middleware** so the trace wraps the full handler lifetime.
- Error handler reports to Langfuse best-effort; failures must not break the user-facing response.

***REMOVED******REMOVED*** Related Runtime Services

- **Langfuse** — trace creation and error span updates
- **Redis** — throttling cache backend

***REMOVED******REMOVED*** Focused Checks

```bash
pytest telegram_bot/middlewares/
make check
```

***REMOVED******REMOVED*** See Also

- [`../bot.py`](../bot.py) — Bot handlers where middlewares are registered
- [`../services/`](../services/) — Bot services called by handlers
