# Redis Hardening: Connection Params Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden Redis SDK connection parameters — increase timeouts, enable retry-on-timeout with exponential backoff, add health_check_interval, bump redis-py to 7.1.0.

**Architecture:** Single-point change in `CacheLayerManager.initialize()` (primary connection pool used by bot pipeline) + consistency update in `RedisHealthMonitor`. Preflight connections are short-lived diagnostic — no changes needed. Uses redis-py `Retry` with `ExponentialBackoff` for robust retry policy.

**Tech Stack:** redis-py >= 7.1.0, redis.asyncio, redis.backoff.ExponentialBackoff, redis.retry.Retry

**Issue:** [#121](https://github.com/yastman/rag/issues/121) | **Milestone:** Stream-D: Infra-Perf

---

## Текущее состояние (аудит)

### Connection points

| File | Line | socket_timeout | socket_connect_timeout | retry_on_timeout | health_check | Роль |
|------|------|---------------|----------------------|-----------------|-------------|------|
| `telegram_bot/integrations/cache.py` | 132-138 | **2s** | **2s** | ❌ | ❌ | PRIMARY — бот pipeline |
| `telegram_bot/services/redis_monitor.py` | 44-50 | 5s | 5s | ❌ | ❌ | Background health monitor |
| `telegram_bot/preflight.py` | 71, 134 | ❌ | ❌ | ❌ | ❌ | Short-lived diagnostic |
| `src/cache/redis_semantic_cache.py` | 53 | ❌ | ❌ | ❌ | ❌ | Legacy evaluation |
| `scripts/setup_redis_indexes.py` | 213-217 | 10s | 5s | ❌ | ❌ | One-off script |

### pyproject.toml

```
"redis>=7.0.1"   # line 33
```

### Docker

Все среды: `redis:8.4.0`. VPS уже имеет `--maxmemory-policy volatile-lfu`.

---

## Target параметры

| Параметр | Было | Станет | Обоснование |
|----------|------|--------|-------------|
| `socket_timeout` | 2s | 5s | 2s слишком агрессивно для pipeline ops |
| `socket_connect_timeout` | 2s | 5s | Согласованность с socket_timeout |
| `retry_on_timeout` | not set | `True` | Автоматический retry при timeout |
| `retry` | not set | `Retry(ExponentialBackoff(), 3)` | Exponential backoff вместо simple retry |
| `health_check_interval` | not set | 30 | PING каждые 30с на idle connections |
| `redis>=` | 7.0.1 | 7.1.0 | Минимальная версия для стабильного retry API |

---

## Task 1: Bump redis version in pyproject.toml

**Files:**
- Modify: `pyproject.toml:33`

**Step 1: Update version constraint**

В `pyproject.toml` строка 33, заменить:

```python
# Было:
"redis>=7.0.1",
# Станет:
"redis>=7.1.0",
```

**Step 2: Run uv lock**

Run: `uv lock`
Expected: lockfile updated, no conflicts

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build(deps): bump redis minimum to >=7.1.0 for stable retry API"
```

---

## Task 2: Harden CacheLayerManager connection params

**Files:**
- Modify: `telegram_bot/integrations/cache.py:28,132-138`
- Test: `tests/unit/integrations/test_cache_layers.py`

**Step 1: Write the failing test**

В `tests/unit/integrations/test_cache_layers.py`, добавить в класс `TestCacheLayerManagerInitialize`:

```python
@pytest.mark.asyncio
async def test_initialize_uses_hardened_connection_params(self):
    """Verify Redis from_url is called with timeout, retry, and health_check params."""
    mgr = CacheLayerManager(redis_url="redis://localhost:6379")

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with (
        patch("telegram_bot.integrations.cache.redis.from_url", return_value=mock_redis) as mock_from_url,
        patch("telegram_bot.integrations.cache._create_semantic_cache", return_value=None),
    ):
        await mgr.initialize()

    mock_from_url.assert_called_once()
    call_kwargs = mock_from_url.call_args[1]

    # Timeout params
    assert call_kwargs["socket_timeout"] == 5
    assert call_kwargs["socket_connect_timeout"] == 5

    # Retry params
    assert call_kwargs["retry_on_timeout"] is True
    assert call_kwargs["health_check_interval"] == 30

    # Retry object with ExponentialBackoff
    retry_obj = call_kwargs["retry"]
    from redis.backoff import ExponentialBackoff
    from redis.retry import Retry

    assert isinstance(retry_obj, Retry)
    assert isinstance(retry_obj._backoff, ExponentialBackoff)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/integrations/test_cache_layers.py::TestCacheLayerManagerInitialize::test_initialize_uses_hardened_connection_params -v`
Expected: FAIL — `socket_timeout` is 2 not 5, missing retry params

**Step 3: Update CacheLayerManager.initialize()**

В `telegram_bot/integrations/cache.py`, добавить импорты (после строки 28):

```python
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
```

Заменить блок `from_url` (строки 132-138):

```python
# Было:
self.redis = redis.from_url(
    self.redis_url,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

# Станет:
self.redis = redis.from_url(
    self.redis_url,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    retry=Retry(ExponentialBackoff(), 3),
    health_check_interval=30,
)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/integrations/test_cache_layers.py::TestCacheLayerManagerInitialize::test_initialize_uses_hardened_connection_params -v`
Expected: PASS

**Step 5: Run full cache test suite**

Run: `uv run pytest tests/unit/integrations/test_cache_layers.py -v`
Expected: All 23+ tests PASS

**Step 6: Commit**

```bash
git add telegram_bot/integrations/cache.py tests/unit/integrations/test_cache_layers.py
git commit -m "fix(redis): harden CacheLayerManager connection — 5s timeout, retry, health_check

- socket_timeout: 2s → 5s
- socket_connect_timeout: 2s → 5s
- retry_on_timeout: True
- retry: ExponentialBackoff with 3 attempts
- health_check_interval: 30s

Closes #121"
```

---

## Task 3: Update RedisHealthMonitor for consistency

**Files:**
- Modify: `telegram_bot/services/redis_monitor.py:15,44-50`

**Step 1: Update RedisHealthMonitor.start()**

В `telegram_bot/services/redis_monitor.py`, добавить импорты:

```python
from redis.backoff import ExponentialBackoff
from redis.retry import Retry
```

Обновить `from_url` вызов (строки 44-50):

```python
# Было:
self._redis = aioredis.from_url(
    self.redis_url,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)

# Станет:
self._redis = aioredis.from_url(
    self.redis_url,
    encoding="utf-8",
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True,
    retry=Retry(ExponentialBackoff(), 3),
    health_check_interval=30,
)
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/unit/ -k "redis_monitor or health_monitor" -v`
Expected: PASS (or no tests — monitor не имеет unit-тестов)

**Step 3: Run full unit suite to check no regressions**

Run: `uv run pytest tests/unit/ -n auto --timeout=30`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add telegram_bot/services/redis_monitor.py
git commit -m "fix(redis): harden RedisHealthMonitor connection params for consistency"
```

---

## Task 4: Lint + type check

**Step 1: Run ruff + mypy**

Run: `make check`
Expected: No errors

**Step 2: Fix any issues (if any)**

Ruff может потребовать сортировку импортов. MyPy может потребовать type ignore для Retry._backoff.

---

## Файлы НЕ затрагиваемые (обоснование)

| Файл | Причина |
|------|---------|
| `telegram_bot/preflight.py` | Short-lived diagnostic connections (open → check → close). Retry/health_check бессмысленны. |
| `src/cache/redis_semantic_cache.py` | Legacy evaluation code, не используется в production bot pipeline. |
| `scripts/setup_redis_indexes.py` | One-off script, уже имеет разумные timeouts. |
| `docker-compose*.yml` | Redis server config не меняется (уже на 8.4.0, VPS имеет volatile-lfu). |
| `tests/chaos/test_redis_failures.py` | Тестирует legacy `CacheService`, не `CacheLayerManager`. |
