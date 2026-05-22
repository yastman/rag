# integrations/

## Purpose

External service wrappers and adapters for the Telegram bot. Provides focused adapters between the bot and external services: Redis caching, embedding providers, prompt management, conversation memory, polling locks, and event streaming. Keeps integration concerns separate from business logic in [`../services/`](../services/).

## Entrypoints

| File | Role |
|------|------|
| [`cache.py`](./cache.py) `CacheLayerManager` | 5-tier Redis cache (semantic, embeddings, sparse, search, rerank) |
| [`embeddings.py`](./embeddings.py) | Embedding provider wrappers |
| [`prompt_manager.py`](./prompt_manager.py) | Prompt registry and template loading |
| [`prompt_templates.py`](./prompt_templates.py) | Static prompt template definitions |
| [`memory.py`](./memory.py) | Conversation memory adapter |
| [`polling_lock.py`](./polling_lock.py) | Telegram polling lock to prevent duplicate workers |
| [`event_stream.py`](./event_stream.py) | Event streaming adapter |

## Boundaries

- Adapters only: business logic lives in [`../services/`](../services/).
- Does not own Qdrant search algorithms; see [`../../src/retrieval/`](../../src/retrieval/).
- Redis connection config is owned by [`../config.py`](../config.py) and [`../../src/config/`](../../src/config/).

## Focused Checks

```bash
uv run pytest tests/unit/ -k "cache|embeddings|prompt" -q
```

## See Also

- [`../README.md`](../README.md) — Telegram transport layer
- [`../services/README.md`](../services/README.md) — Business logic services
- [`../../src/config/`](../../src/config/) — Shared settings
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup
