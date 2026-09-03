"""Live Redis healthy/degraded probes for the demo Redis contract (#3199).

Companion to docs/audits/redis-demo-behavior-2026-09-03.md and
tests/characterization/test_redis_demo_behavior.py (offline counterpart).

Probes, against a live Redis:

- Healthy: the polling lock admits exactly one owner; a second owner is
  rejected with `PollingLockBusy`; release hands the lease over.
- Healthy: exact cache tiers miss deterministically, store, then hit with the
  identical value.
- Degraded: `CacheLayerManager.initialize` against an unreachable Redis leaves
  every cache disabled and every read is a miss (fail open, no exception).
- Degraded mid-run: a read against a dropped connection returns ``None``
  (uncached product behavior), never raises.

Artifacts are limited to the unique ``i3199-`` key prefix and are deleted in
``finally`` teardown; nothing else in the shared Redis instance is touched.

Skips (instead of failing) when Redis is not reachable on the configured URL.
"""

from __future__ import annotations

import socket

import pytest
import redis.asyncio as aioredis

from src.runtime.integrations.cache import CacheLayerManager
from src.runtime.integrations.polling_lock import PollingLockBusy, RedisPollingLock

pytestmark = pytest.mark.requires_services

_PROBE_LOCK_KEY = "i3199-polling"
_PROBE_CACHE_KEY = "i3199-probe"
_PROBE_TIER_PATTERNS = ("search:v5:i3199-*", "sparse:v5:i3199-*")
_DEAD_REDIS_URL = "redis://localhost:1/0"  # port 1: connection refused, fast


def _redis_reachable(url: str) -> bool:
    host = url.split("://", 1)[-1].split(":", 1)[0].split("@")[-1] or "localhost"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2.0)
        try:
            sock.connect((host, 6379))
            return True
        except OSError:
            return False


async def _cleanup_probe_keys(client: aioredis.Redis) -> None:
    """Delete every i3199-prefixed probe artifact (best effort)."""
    try:
        await client.delete(_PROBE_LOCK_KEY)
        for pattern in _PROBE_TIER_PATTERNS:
            keys = [key async for key in client.scan_iter(match=pattern)]
            if keys:
                await client.delete(*keys)
    except Exception:  # noqa: S110 - cleanup is best effort
        pass


class TestLivePollingLockProbe:
    """Healthy-Redis probe: exactly one polling owner."""

    async def test_single_owner_contention_and_handover(self, redis_url: str) -> None:
        if not _redis_reachable(redis_url):
            pytest.skip("Redis not reachable — live probe skipped")
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await client.ping()

            winner = RedisPollingLock(redis=client, key=_PROBE_LOCK_KEY, ttl_sec=10)
            await winner.acquire(owner="i3199-winner")
            # The lease records the winning owner...
            assert await client.get(_PROBE_LOCK_KEY) == "i3199-winner"

            # ...rejects a second owner...
            loser = RedisPollingLock(redis=client, key=_PROBE_LOCK_KEY, ttl_sec=10)
            with pytest.raises(PollingLockBusy) as exc_info:
                await loser.acquire(owner="i3199-loser")
            assert "i3199-winner" in str(exc_info.value)

            # ...and release hands the lease to the next acquirer.
            await winner.release()
            await loser.acquire(owner="i3199-loser")
            assert await client.get(_PROBE_LOCK_KEY) == "i3199-loser"
            await loser.release()
        finally:
            await _cleanup_probe_keys(client)
            await client.aclose()


class TestLiveCacheProbes:
    """Healthy and degraded cache probes: fail-open determinism."""

    async def test_healthy_exact_tier_miss_store_hit(self, redis_url: str) -> None:
        if not _redis_reachable(redis_url):
            pytest.skip("Redis not reachable — live probe skipped")
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await client.ping()

            mgr = CacheLayerManager(redis_url=redis_url)
            # Bind the live client directly: no semantic/embed index is created,
            # so the probe only ever touches i3199-prefixed exact-tier keys.
            mgr.redis = client

            assert await mgr.get_exact("search", _PROBE_CACHE_KEY) is None
            payload = [{"id": "apt-i3199", "score": 0.42}]
            await mgr.store_exact("search", _PROBE_CACHE_KEY, payload)
            assert await mgr.get_exact("search", _PROBE_CACHE_KEY) == payload
        finally:
            await _cleanup_probe_keys(client)
            await client.aclose()

    async def test_index_failure_fails_open(self) -> None:
        mgr = CacheLayerManager(redis_url=_DEAD_REDIS_URL)
        await mgr.initialize()

        assert mgr.redis is None
        assert mgr.semantic_cache is None
        assert mgr.embed_cache is None
        assert await mgr.get_exact("search", _PROBE_CACHE_KEY) is None
        await mgr.store_exact("search", _PROBE_CACHE_KEY, [{"x": 1}])  # no-op, no raise

    async def test_dropped_connection_read_fails_open(self, redis_url: str) -> None:
        if not _redis_reachable(redis_url):
            pytest.skip("Redis not reachable — live probe skipped")
        client = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await client.ping()
            mgr = CacheLayerManager(redis_url=redis_url)
            mgr.redis = client
            await client.aclose()  # simulate mid-run Redis loss

            # Fail open: uncached behavior, no exception escapes.
            assert await mgr.get_exact("search", _PROBE_CACHE_KEY) is None
        finally:
            await _cleanup_probe_keys(client)
