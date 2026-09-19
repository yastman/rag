# integrations/

## Purpose

The Telegram adapter uses shared integrations directly from `src.runtime.integrations`: Redis caching, embedding providers, prompt management and polling locks.

## Entrypoints

| File | Role |
|------|------|
| [`src/runtime/integrations/cache.py`](../../src/runtime/integrations/cache.py) | `src.runtime.integrations.cache.CacheLayerManager` (5-tier Redis cache; #3010) |
| [`src/runtime/integrations/embeddings.py`](../../src/runtime/integrations/embeddings.py) | Embedding providers |
| [`src/runtime/integrations/prompt_manager.py`](../../src/runtime/integrations/prompt_manager.py) | Prompt registry / template loading |
| [`src/runtime/integrations/polling_lock.py`](../../src/runtime/integrations/polling_lock.py) | Telegram polling lock to prevent duplicate workers |

## Boundaries

- Adapters only: business logic lives in [`../services/`](../services/).
- Does not own Qdrant search algorithms; see [`../../src/retrieval/`](../../src/retrieval/).
- Redis connection config is owned by [`../config.py`](../config.py).

## Focused Checks

```bash
uv run pytest tests/unit/ -k "cache|embeddings|prompt" -q
```

## See Also

- [`../README.md`](../README.md) — Telegram transport layer
- [`../services/README.md`](../services/README.md) — Business logic services
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup
