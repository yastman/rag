# telegram_bot/lifecycle/

Bot startup/teardown, the service factory, and Postgres bootstrap — extracted from
`telegram_bot/bot.py` (#2048, `card_2a71ec058138`) so they can be tested without
instantiating the full bot stack.

## Files

| File | Purpose |
|------|---------|
| [`lifecycle.py`](./lifecycle.py) | Lifecycle helpers `PropertyBot.start` / `.stop` invoke — e.g. `warmup_bge_pool` (warm BGE-M3 pool, #953), `polling_lock_heartbeat_tick` (bounded Redis polling-lock heartbeat) |
| [`services.py`](./services.py) | Service factory: builds the collaborators the bot needs |
| [`postgres_bootstrap.py`](./postgres_bootstrap.py) | Postgres schema/bootstrap on startup |

## Boundaries

- **Narrow import graph:** module-level imports are stdlib-only — no `aiogram` /
  `langgraph` / `qdrant_client` / `fastapi` at module scope. Helpers receive their
  collaborators (embedder, polling-lock holder) as arguments rather than reading `self`.
- Pinned by
  [`../../tests/contract/test_bot_lifecycle_extraction_contract.py`](../../tests/contract/test_bot_lifecycle_extraction_contract.py).

## See Also

- [`../README.md`](../README.md) — Telegram transport overview
- [`../preflight/README.md`](../preflight/README.md) — dependency checks run during startup
