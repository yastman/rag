# middlewares/

Aiogram middlewares for Telegram bot: error handling and rate limiting.

## Files

| File | Purpose |
|------|---------|
| [\_\_init\_\_.py](./__init__.py) | Middleware exports |
| [error_handler.py](./error_handler.py) | Centralized exception handling with user-friendly error messages |
| [throttling.py](./throttling.py) | Rate limiting using TTLCache (1.5s window, admin bypass) |

## Related

- [telegram_bot/services/](../services/) — Bot services
- [telegram_bot/bot.py](../bot.py) — Bot handlers
