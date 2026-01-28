# Zoo Smoke Tests Design

**Date:** 2026-01-28
**Status:** Approved
**Author:** Claude

## Overview

Smoke-тесты для проверки всего "зоопарка" сервисов: Redis, Qdrant, bge-m3, bm42, user-base, langfuse, litellm.

Два варианта запуска:
- **Bash** (`scripts/smoke-zoo.sh`) — быстрый локальный чек, ~30 сек
- **Pytest** (`tests/smoke/test_zoo_smoke.py`) — полный smoke для CI

## GAP Analysis

### Сервисы

| Сервис | Порт | Health Test | Live Test | Gap |
|--------|------|-------------|-----------|-----|
| Redis | 6379 | ✅ | ✅ | - |
| Qdrant | 6333 | ✅ | ✅ | - |
| bge-m3 | 8000 | ✅ | ❌ | нет реального embed теста |
| bm42 | 8002 | ✅ | ❌ | нет реального embed теста |
| **user-base** | 8003 | ❌ | ⚠️ | нет health, embed размерность |
| langfuse | 3001 | ✅ | ✅ | - |
| **litellm** | 4000 | ❌ | ❌ | полностью отсутствует |

### Кэш

| Компонент | Unit Test | Live Test | Gap |
|-----------|-----------|-----------|-----|
| SemanticCache | ✅ | ✅ | - |
| EmbeddingsCache | ✅ | ✅ | - |
| SparseCache | ❌ | ❌ | roundtrip |
| RerankCache | ✅ | ✅ | - |
| "Второй запрос дешевле" | ❌ | ❌ | e2e validation |

## Implementation

### 1. scripts/smoke-zoo.sh

Быстрый bash-скрипт для локальной проверки.

**Проверки (7 штук):**

| # | Проверка | Команда | OK условие |
|---|----------|---------|------------|
| 1 | Redis PING | `redis-cli PING` | PONG |
| 2 | Redis FT._LIST | `redis-cli FT._LIST` | команда существует |
| 3 | Qdrant readyz | `curl -sf localhost:6333/readyz` | HTTP 200 |
| 4 | bge-m3 health | `curl -sf localhost:8000/health` | status=ok |
| 5 | bm42 health | `curl -sf localhost:8002/health` | status=ok |
| 6 | user-base health | `curl -sf localhost:8003/health` | status=ok |
| 7 | litellm health | `curl -sf localhost:4000/health/liveliness` | HTTP 200 |

**Использование:**
```bash
./scripts/smoke-zoo.sh           # Полный вывод
./scripts/smoke-zoo.sh --quiet   # Только exit code
```

**Exit codes:**
- 0: все проверки OK
- 1: хотя бы одна FAIL

### 2. tests/smoke/test_zoo_smoke.py

Pytest-тесты для CI.

```python
class TestZooHealth:
    """Health checks для сервисов без существующих тестов."""

    async def test_user_base_health():
        """user-base :8003/health returns status=ok."""

    async def test_user_base_embed_returns_768_dim():
        """user-base /embed returns 768-dim vector."""

    async def test_litellm_health():
        """litellm :4000/health/liveliness returns 200."""

    async def test_litellm_completion():
        """litellm chat completion works (skip if no keys)."""


class TestZooCache:
    """Cache roundtrip tests."""

    async def test_sparse_cache_roundtrip():
        """Sparse cache store → get works."""

    async def test_semantic_cache_with_user_filter():
        """SemanticCache with user_id filter isolation."""


class TestZooEndToEnd:
    """End-to-end validation."""

    async def test_second_request_cheaper():
        """Second identical request has cache hits."""
```

**Fixtures:**
- Используем существующие: `cache_service`, `voyage_service`, `qdrant_service`
- Новые: `user_base_vectorizer`, `litellm_client`

### 3. Makefile

```makefile
# Быстрый локальный чек (~30 сек)
smoke-fast:
	./scripts/smoke-zoo.sh

# Полный smoke (pytest)
smoke-full:
	pytest tests/smoke/ -v --tb=short

# Только zoo тесты
smoke-zoo:
	pytest tests/smoke/test_zoo_smoke.py -v
```

## Existing Coverage (не дублируем)

Следующие тесты уже существуют:

- **Redis:** `test_preflight.py` (ping, maxmemory, policy, FT._LIST)
- **Qdrant:** `test_preflight.py` (collection, BQ, optimizer)
- **bge-m3/bm42 health:** `test_docker_services.py`
- **Langfuse:** `test_smoke_services.py`, `test_infrastructure.py`
- **SemanticCache:** `test_cache_service.py` (store/check, user isolation)
- **EmbeddingsCache:** `test_cache_service.py` (store/get)
- **RerankCache:** `test_smoke_cache.py` (roundtrip)

## Files to Create

1. `scripts/smoke-zoo.sh` — bash smoke script
2. `tests/smoke/test_zoo_smoke.py` — pytest tests

## Files to Modify

1. `Makefile` — добавить smoke-fast, smoke-full, smoke-zoo targets

## Success Criteria

1. `./scripts/smoke-zoo.sh` выполняется за <30 сек
2. `pytest tests/smoke/test_zoo_smoke.py` проходит при работающих сервисах
3. `make smoke-fast` можно использовать как pre-push hook
4. CI падает если любой smoke тест не прошел
