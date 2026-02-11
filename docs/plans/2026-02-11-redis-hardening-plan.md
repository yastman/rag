# Redis Hardening: Connection Params — Implementation Plan

## Goal

Унифицировать параметры Redis-соединений во всех connection points: поднять таймауты до 5s,
добавить retry с exponential backoff, включить health_check_interval, обновить redis-py до >=7.1.0.

## Issue

https://github.com/yastman/rag/issues/121 | Milestone: Stream-D: Infra-Perf

## Текущее состояние (аудит)

Все точки подключения к Redis:

| # | Файл | Строка | socket_connect_timeout | socket_timeout | retry_on_timeout | retry | health_check_interval | Роль |
|---|------|--------|------------------------|----------------|------------------|-------|-----------------------|------|
| 1 | telegram_bot/integrations/cache.py | L132-138 | 2s | 2s | — | — | — | PRIMARY — бот pipeline |
| 2 | telegram_bot/services/redis_monitor.py | L44-50 | 5s | 5s | — | — | — | Background health monitor |
| 3 | telegram_bot/preflight.py | L71 | — | — | — | — | — | Short-lived diagnostic |
| 4 | telegram_bot/preflight.py | L134 | — | — | — | — | — | Short-lived diagnostic |
| 5 | src/cache/redis_semantic_cache.py | L53 | — | — | — | — | — | Legacy evaluation |

pyproject.toml L33: "redis>=7.0.1"

Docker: redis:8.4.0 (docker-compose.dev.yml L39), maxmemory-policy=volatile-lfu уже настроена.

## Target параметры

    # Единый набор для production connection points (#1, #2)
    redis.from_url(
        url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        retry=Retry(ExponentialBackoff(), 3),
        health_check_interval=30,
    )

    # pyproject.toml
    "redis>=7.1.0"

Импорты:

    from redis.backoff import ExponentialBackoff
    from redis.retry import Retry

## Файлы НЕ затрагиваемые (обоснование)

| Файл | Причина |
|------|---------|
| telegram_bot/preflight.py (L71, L134) | Short-lived diagnostic connections (open -> check -> close). Retry/health_check бессмысленны. Уже имеет tenacity retry на уровне check_dependencies. |
| src/cache/redis_semantic_cache.py | Legacy evaluation code, не используется в production bot pipeline. Находится в src/ и не должен зависеть от telegram_bot/. |
| docker-compose*.yml | Redis server config не меняется (уже на 8.4.0, VPS имеет volatile-lfu). |

---

## Task 1: Bump redis version in pyproject.toml (1 мин)

Файл: pyproject.toml, L33

Заменить:

    "redis>=7.0.1",

На:

    "redis>=7.1.0",

Затем:

    uv lock

Expected: lockfile updated, no conflicts. redisvl>=0.13.2 требует redis>=5.0 — compatible.

---

## Task 2: Harden CacheLayerManager connection params (5 мин)

Файлы:
- Modify: telegram_bot/integrations/cache.py (L28, L132-138)
- Test: tests/unit/integrations/test_cache_layers.py

### Step 1: Write failing test

В tests/unit/integrations/test_cache_layers.py добавить тест:

    @pytest.mark.asyncio
    async def test_initialize_uses_hardened_connection_params(self):
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        with (
            patch("telegram_bot.integrations.cache.redis.from_url", return_value=mock_redis) as mock_from_url,
            patch("telegram_bot.integrations.cache._create_semantic_cache", return_value=None),
        ):
            await mgr.initialize()

        call_kwargs = mock_from_url.call_args[1]
        assert call_kwargs["socket_timeout"] == 5
        assert call_kwargs["socket_connect_timeout"] == 5
        assert call_kwargs["retry_on_timeout"] is True
        assert call_kwargs["health_check_interval"] == 30

        from redis.backoff import ExponentialBackoff
        from redis.retry import Retry
        assert isinstance(call_kwargs["retry"], Retry)

### Step 2: Run test — should FAIL

    uv run pytest tests/unit/integrations/test_cache_layers.py -k "hardened" -v

Expected: FAIL (socket_timeout is 2 not 5, missing retry params)

### Step 3: Update CacheLayerManager.initialize()

В telegram_bot/integrations/cache.py:

Добавить импорты после L28 (import redis.asyncio as redis):

    from redis.backoff import ExponentialBackoff
    from redis.retry import Retry

Заменить L132-138:

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

### Step 4: Run test — should PASS

    uv run pytest tests/unit/integrations/test_cache_layers.py -k "hardened" -v

### Step 5: Run full cache test suite

    uv run pytest tests/unit/integrations/test_cache_layers.py -v

Expected: All 23+ tests PASS

---

## Task 3: Update RedisHealthMonitor for consistency (3 мин)

Файл: telegram_bot/services/redis_monitor.py (L15, L44-50)

### Step 1: Add imports

Добавить после L15 (import redis.asyncio as aioredis):

    from redis.backoff import ExponentialBackoff
    from redis.retry import Retry

### Step 2: Update from_url call

Заменить L44-50:

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

---

## Task 4: Lint + type check (2 мин)

    make check

Expected: No errors. Ruff может потребовать сортировку импортов.

---

## Task 5: Full test suite (3 мин)

    uv run pytest tests/unit/ -n auto --timeout=30

Expected: All tests PASS

---

## Test Strategy

    # Существующие тесты (должны пройти без изменений)
    uv run pytest tests/unit/integrations/test_cache_layers.py -v    # 23 tests
    uv run pytest tests/unit/graph/test_cache_nodes.py -v            # 7 tests
    uv run pytest tests/unit/graph/test_retrieve_node.py -v          # 5 tests

    # Новый тест на hardened params
    uv run pytest tests/unit/integrations/test_cache_layers.py -k "hardened" -v

    # Полный прогон
    uv run pytest tests/unit/ -n auto

    # Lint + types
    make check

## Acceptance Criteria

1. redis>=7.1.0 в pyproject.toml
2. CacheLayerManager.initialize() использует socket_timeout=5, socket_connect_timeout=5, retry_on_timeout=True, retry=Retry(ExponentialBackoff(), 3), health_check_interval=30
3. RedisHealthMonitor.start() использует те же параметры
4. Новый unit-тест на hardened params проходит
5. Все существующие unit-тесты проходят
6. make check (ruff + mypy) проходит

## Effort Estimate

**S** (Small) — 1 час

2 точечных замены from_url + 1 тест + version bump. Никаких архитектурных изменений.

## Риски

- **redis-py 7.1.0 + redisvl**: redisvl>=0.13.2 требует redis>=5.0. redis 7.1.0 compatible.
- **health_check_interval + async**: поддерживается в redis.asyncio с redis-py 4.5+.
- **Retry в preflight**: preflight уже имеет tenacity retry. Redis-level retry дополняет — не конфликтуют.
- **ExponentialBackoff defaults**: base=0.064s, cap=512s. Для 3 retries: ~0.064s, ~0.128s, ~0.256s. Суммарно < 0.5s задержки.
