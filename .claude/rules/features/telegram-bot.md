---
paths: "telegram_bot/*.py, telegram_bot/middlewares/**"
---

# Telegram Bot

PropertyBot handlers, middlewares, and message processing.

## Purpose

Telegram interface for Bulgarian property search with streaming responses and rate limiting.

## Architecture

```
User Message → ThrottlingMiddleware → ErrorMiddleware
            → PropertyBot.handle_query()
            → [Routing → Cache → Search → LLM]
            → Markdown Response
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `telegram_bot/bot.py` | 35 | PropertyBot class |
| `telegram_bot/main.py` | - | Entry point |
| `telegram_bot/config.py` | - | BotConfig dataclass |
| `telegram_bot/middlewares/throttling.py` | 17 | ThrottlingMiddleware |
| `telegram_bot/middlewares/error_handler.py` | 16 | ErrorHandlerMiddleware |

## Bot Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | on_start | Welcome message |
| `/help` | on_help | Usage instructions |
| `/clear` | on_clear | Clear conversation |
| `/stats` | on_stats | Cache statistics |

## Middlewares

### ThrottlingMiddleware

Rate limiting with TTL cache:

```python
ThrottlingMiddleware(
    rate_limit=1.5,      # Seconds between requests
    admin_ids=[123456],  # Exempt from throttling
)
```

- Uses `cachetools.TTLCache(maxsize=10_000, ttl=rate_limit)`
- Admins bypass throttling
- Returns "⏱ Слишком частые запросы" on throttle

### ErrorHandlerMiddleware

Centralized error handling:

```python
# Catches all exceptions
# Logs with exc_info=True
# Returns user-friendly message
"❌ Произошла ошибка при обработке запроса."
```

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | - | Bot token from @BotFather |
| `rate_limit` | 1.5s | Throttling window |
| `user_context_ttl` | 30 days | CESC context lifetime |
| `cesc_extraction_frequency` | 3 | Extract prefs every N queries |

## Service Dependencies

```python
# Initialized in PropertyBot.__init__
self.cache_service = CacheService(redis_url)
self.voyage_service = VoyageService(api_key)
self.qdrant_service = QdrantService(url, collection)
self.llm_service = LLMService(api_key, base_url)
self.query_analyzer = QueryAnalyzer(api_key, base_url)
self.user_context_service = UserContextService(cache, llm)
self.cesc_personalizer = CESCPersonalizer(llm)
```

## Message Flow

1. **Receive message** → Middlewares (throttle, error)
2. **Classify query** → CHITCHAT/SIMPLE/COMPLEX
3. **Check cache** → Return cached if hit
4. **Preprocess** → Translit, weights
5. **Analyze** → Extract filters
6. **Search** → Qdrant hybrid RRF
7. **Rerank** → ColBERT rerank on VPS / Voyage rerank in dev (if COMPLEX)
8. **Generate** → LLM answer
9. **Cache** → Store response
10. **Reply** → Markdown formatted

## Response Formatting

```python
# Bot uses Markdown parse_mode
await message.answer(response, parse_mode="Markdown")
```

Supported:
- `**bold**` for emphasis
- `• item` for lists
- Prices in euros, distances in meters

## Dependencies

- Container: `dev-bot` / `vps-bot`, 512MB RAM
- Requires: redis, qdrant, litellm, bge-m3, user-base (VPS) | redis, qdrant, litellm, bm42, user-base (dev)

## Testing

```bash
pytest tests/unit/test_bot.py -v
pytest tests/unit/test_middlewares.py -v
make e2e-test  # Full E2E with real Telegram
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Bot not responding | Check `docker logs dev-bot` |
| `TELEGRAM_BOT_TOKEN` invalid | Get new token from @BotFather |
| Services unhealthy | Check depends_on containers |

## Development Guide

### Adding new command

1. Add handler method to `PropertyBot`:
```python
async def on_newcmd(self, message: Message):
    await message.answer("Response")
```

2. Register in `_register_handlers()`:
```python
self.dp.message.register(self.on_newcmd, Command("newcmd"))
```

3. Add test in `tests/unit/test_bot.py`

### Adding new middleware

1. Create class in `telegram_bot/middlewares/`
2. Inherit from `BaseMiddleware`
3. Implement `__call__` method
4. Register in `bot.py._setup_middlewares()`
