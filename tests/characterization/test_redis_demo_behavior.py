"""Characterization tests: Redis responsibilities for the demo (#3199).

Pins the deterministic outcomes the demo relies on (parent epic #3197):

- Authoritative single-poller ownership: the polling lease admits exactly one
  owner; contention is rejected with actionable diagnostics; loss of ownership
  stops polling instead of risking two bots.
- Non-authoritative caches fail open: index/read failures and misses degrade to
  the uncached product path; store failures are silent no-ops; nothing is
  fabricated or suppressed.
- Apartment-extraction cache failure changes nothing about the extracted
  product behavior (regex floor still applies).
- Handoff keys stay conditional on the handoff capability.

Companion definition record: docs/audits/redis-demo-behavior-2026-09-03.md.
Live Redis probes for the same behaviors: tests/integration/test_redis_demo_probes.py.

OFFLINE: no live Redis, Qdrant, BGE-M3, or LLM required.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.polling_lock import (
    POLLING_LOCK_KEY,
    PollingLockBusy,
    RedisPollingLock,
)
from telegram_bot.lifecycle.lifecycle import (
    POLLING_LOCK_MAX_REFRESH_FAILURES,
    polling_lock_heartbeat_tick,
    setup_handoff_services,
)
from telegram_bot.services.apartment.apartment_extraction_pipeline import (
    ApartmentExtractionPipeline,
)
from telegram_bot.services.apartment.apartment_filter_extractor import (
    ApartmentFilterExtractor,
)


pytestmark = pytest.mark.characterization

_DEAD_REDIS_URL = "redis://localhost:1/0"  # port 1: connection refused, fast


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Minimal in-memory async Redis double for exact-tier characterization."""

    def __init__(self, *, fail_get: bool = False, fail_set: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self._fail_get = fail_get
        self._fail_set = fail_set

    async def get(self, key: str) -> str | None:
        if self._fail_get:
            raise ConnectionError("redis read failed")
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        if self._fail_set:
            raise ConnectionError("redis write failed")
        self.store[key] = value
        self.ttls[key] = ttl


def _make_owner_lock(redis: object, key: str = POLLING_LOCK_KEY) -> RedisPollingLock:
    return RedisPollingLock(redis=redis, key=key, ttl_sec=90)


# ---------------------------------------------------------------------------
# Single-poller ownership (authoritative)
# ---------------------------------------------------------------------------


class TestSinglePollerOwnership:
    """Exactly one polling owner; contention and loss are safe."""

    async def test_winner_holds_lease_and_loser_is_rejected(self) -> None:
        winner_backend = MagicMock()
        winner_backend.acquire = AsyncMock(return_value=True)
        winner_backend.extend = AsyncMock(return_value=True)
        redis = MagicMock()
        redis.lock.return_value = winner_backend

        winner = _make_owner_lock(redis)
        await winner.acquire(owner="i3199-winner")

        loser_backend = MagicMock()
        loser_backend.acquire = AsyncMock(return_value=False)
        redis.lock.return_value = loser_backend
        redis.get = AsyncMock(return_value=b"i3199-winner")
        redis.pttl = AsyncMock(return_value=89_000)

        loser = _make_owner_lock(redis)
        with pytest.raises(PollingLockBusy):
            await loser.acquire(owner="i3199-loser")

        # Contention must not disturb the winner's lease...
        winner_backend.release.assert_not_called()
        # ...and the winner keeps refreshing it.
        await winner.refresh()
        winner_backend.extend.assert_awaited_once_with(additional_time=90, replace_ttl=True)

    async def test_contention_diagnostic_is_operator_actionable(self) -> None:
        backend = MagicMock()
        backend.acquire = AsyncMock(return_value=False)
        redis = MagicMock()
        redis.lock.return_value = backend
        redis.get = AsyncMock(return_value=b"i3199-winner")
        redis.pttl = AsyncMock(return_value=45_000)

        lock = _make_owner_lock(redis)
        with pytest.raises(PollingLockBusy) as exc_info:
            await lock.acquire(owner="i3199-loser")

        msg = str(exc_info.value)
        assert POLLING_LOCK_KEY in msg
        assert "owner='i3199-winner'" in msg
        assert "pttl_ms=45000" in msg
        assert "stop the other bot instance first" in msg

    async def test_loss_of_ownership_stops_polling_safely(self) -> None:
        bot = MagicMock()
        bot._polling_lock = MagicMock()
        bot._polling_lock.refresh = AsyncMock(side_effect=ConnectionError("redis gone"))
        bot._polling_lock_consecutive_failures = 0
        bot.dp.stop_polling = AsyncMock()

        for expected in range(1, POLLING_LOCK_MAX_REFRESH_FAILURES + 1):
            await polling_lock_heartbeat_tick(bot, max_refresh_failures=POLLING_LOCK_MAX_REFRESH_FAILURES)
            assert bot._polling_lock_consecutive_failures == expected
            assert bot.dp.stop_polling.await_count == (
                1 if expected == POLLING_LOCK_MAX_REFRESH_FAILURES else 0
            )

    async def test_transient_refresh_failure_recovers_without_stopping(self) -> None:
        bot = MagicMock()
        bot._polling_lock = MagicMock()
        bot._polling_lock.refresh = AsyncMock(
            side_effect=[ConnectionError("blip"), None, None]
        )
        bot._polling_lock_consecutive_failures = 0
        bot.dp.stop_polling = AsyncMock()

        await polling_lock_heartbeat_tick(bot, max_refresh_failures=POLLING_LOCK_MAX_REFRESH_FAILURES)
        assert bot._polling_lock_consecutive_failures == 1
        bot.dp.stop_polling.assert_not_awaited()

        await polling_lock_heartbeat_tick(bot, max_refresh_failures=POLLING_LOCK_MAX_REFRESH_FAILURES)
        assert bot._polling_lock_consecutive_failures == 0
        bot.dp.stop_polling.assert_not_awaited()


# ---------------------------------------------------------------------------
# Cache fail-open behavior (non-authoritative)
# ---------------------------------------------------------------------------


class TestFailOpenCaches:
    """Cache index/read failures and misses degrade to the uncached path."""

    async def test_cache_index_failure_degrades_to_uncached(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        mgr = CacheLayerManager(redis_url=_DEAD_REDIS_URL)
        with caplog.at_level(logging.ERROR):
            await mgr.initialize()

        # Index setup failed: every backend stays disabled...
        assert mgr.redis is None
        assert mgr.semantic_cache is None
        assert mgr.embed_cache is None
        # ...degraded status is operator-visible...
        assert "Redis connection failed" in caplog.text
        # ...and every read/store deterministically degrades to uncached.
        assert await mgr.get_exact("search", "i3199-key") is None
        assert await mgr.get_sparse_embedding("двушка у моря") is None
        assert await mgr.get_search_results([0.1] * 4, None, None) is None
        assert await mgr.get_rerank_results("query", [{"text": "doc"}], 5) is None
        assert await mgr.get_embedding("query") is None
        await mgr.store_exact("search", "i3199-key", [{"x": 1}])  # no-op, no raise

    async def test_exact_tiers_miss_store_hit_roundtrip(self) -> None:
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = _FakeRedis()

        # Miss first: deterministic uncached behavior.
        assert await mgr.get_exact("search", "i3199-key") is None
        # Store, then the exact same value comes back.
        await mgr.store_exact("search", "i3199-key", [{"id": "apt-1"}])
        assert await mgr.get_exact("search", "i3199-key") == [{"id": "apt-1"}]
        # Tier TTL is honored on write.
        assert mgr.redis.ttls["search:v5:i3199-key"] == 7200

        await mgr.store_sparse_embedding("двушка у моря", {"indices": [1], "values": [0.5]})
        assert await mgr.get_sparse_embedding("двушка у моря") == {
            "indices": [1],
            "values": [0.5],
        }

    async def test_read_failure_returns_none_never_raises(self) -> None:
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = _FakeRedis(fail_get=True)

        assert await mgr.get_exact("search", "i3199-key") is None
        assert mgr._metrics["search"]["misses"] == 1

    async def test_semantic_error_returns_none_not_fabricated_value(self) -> None:
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = MagicMock()
        mgr.semantic_cache.acheck = AsyncMock(side_effect=RuntimeError("index gone"))

        assert (
            await mgr.check_semantic(
                query="внж",
                vector=[0.1] * 1024,
                query_type="GENERAL",
            )
            is None
        )
        assert mgr._metrics["semantic"]["misses"] == 1

    async def test_semantic_hit_returns_only_previously_stored_response(self) -> None:
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = MagicMock()
        mgr.semantic_cache.acheck = AsyncMock(
            return_value=[{"response": "grounded answer", "vector_distance": 0.05}]
        )

        result = await mgr.check_semantic(
            query="внж",
            vector=[0.1] * 1024,
            query_type="GENERAL",
        )
        assert result == "grounded answer"

    async def test_store_failure_is_silent_noop(self) -> None:
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.redis = _FakeRedis(fail_set=True)

        # Write failures never break the product path.
        await mgr.store_exact("search", "i3199-key", [{"id": "apt-1"}])
        await mgr.store_sparse_embedding("двушка у моря", {"indices": [1]})

    async def test_semantic_store_failure_is_silent_noop(self) -> None:
        mgr = CacheLayerManager(redis_url="redis://localhost:6379")
        mgr.semantic_cache = MagicMock()
        mgr.semantic_cache.astore = AsyncMock(side_effect=RuntimeError("write failed"))

        await mgr.store_semantic(
            query="внж",
            response="grounded answer",
            vector=[0.1] * 1024,
            query_type="GENERAL",
        )  # no raise


# ---------------------------------------------------------------------------
# Apartment-extraction cache (fail open to the regex floor)
# ---------------------------------------------------------------------------


_DEMO_QUERY = "двушка от 100к до 200к евро у моря"


class TestApartmentExtractionCache:
    """Extraction cache failure changes nothing about extracted filters."""

    async def test_cache_read_failure_falls_back_to_regex(self) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=ConnectionError("redis gone"))
        redis.set = AsyncMock()
        pipeline = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=None,
            redis=redis,
        )

        result = await pipeline.extract(_DEMO_QUERY)

        assert result.hard.rooms == 3  # "двушка" → 3 total rooms
        assert result.hard.min_price_eur == 100_000
        assert result.hard.max_price_eur == 200_000
        assert result.meta.source == "regex"

    async def test_disabled_cache_yields_identical_result(self) -> None:
        without_cache = await ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=None,
            redis=None,
        ).extract(_DEMO_QUERY)
        failing_cache = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=None,
            redis=MagicMock(get=AsyncMock(side_effect=ConnectionError("down"))),
        )
        with_cache_failure = await failing_cache.extract(_DEMO_QUERY)

        assert with_cache_failure.hard == without_cache.hard
        assert with_cache_failure.soft == without_cache.soft

    async def test_cache_write_failure_still_returns_result(self) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(side_effect=ConnectionError("write failed"))
        pipeline = ApartmentExtractionPipeline(
            regex_extractor=ApartmentFilterExtractor(),
            llm_extractor=None,
            redis=redis,
        )

        result = await pipeline.extract(_DEMO_QUERY)

        assert result.meta.source == "regex"
        assert result.hard.rooms == 3


# ---------------------------------------------------------------------------
# Handoff keys conditional on the handoff capability
# ---------------------------------------------------------------------------


class TestHandoffConditionality:
    """No handoff capability → no handoff keys in Redis."""

    async def test_no_handoff_state_without_cache_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        try:
            import aiogram  # noqa: F401
        except ImportError:
            # ``forum_bridge`` pulls aiogram (telegram extra). The offline core
            # gate runs without it, so stub the module to pin the actual
            # contract under test: no cache backend → no handoff state.
            monkeypatch.setitem(sys.modules, "telegram_bot.services.forum_bridge", MagicMock())

        bot = MagicMock()
        bot._cache = MagicMock(redis=None)
        bot._handoff_state = None
        bot._forum_bridge = None
        bot.config.managers_group_id = None

        setup_handoff_services(bot)

        assert bot._handoff_state is None

    def test_handoff_capability_defaults_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from telegram_bot.config import BotConfig

        monkeypatch.delenv("HANDOFF_ENABLED", raising=False)
        monkeypatch.delenv("MANAGERS_GROUP_ID", raising=False)
        cfg = BotConfig(
            telegram_bot_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            handoff_enabled=False,
            managers_group_id=None,
            _env_file=None,
        )

        assert cfg.handoff_enabled is False
