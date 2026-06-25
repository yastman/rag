# middlewares/

Aiogram middlewares for the Telegram bot: observability, error handling, and rate limiting.

## Purpose

Wrap every Telegram update in cross-cutting concerns before handlers run.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Middleware exports |
| [`error_handler.py`](./error_handler.py) | Centralized exception handling with user-friendly error messages |
| [`throttling.py`](./throttling.py) | Rate limiting using TTLCache (1.5s window, admin bypass) |

## Boundaries

- Middlewares are **transport-layer only**. They must not contain retrieval logic, LLM calls, or business rules.

## Related Runtime Services

- **Redis** — throttling cache backend

## Focused Checks

```bash
pytest telegram_bot/middlewares/
make check
```

## See Also

- [`../bot.py`](../bot.py) — Bot handlers where middlewares are registered
- [`../services/`](../services/) — Bot services called by handlers
