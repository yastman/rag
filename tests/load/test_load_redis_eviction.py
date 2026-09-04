# tests/load/test_load_redis_eviction.py
"""Run-owned Redis LFU eviction load (#3447).

Every connection in this module is bound to the verified disposable
target fixture from ``tests/load/conftest.py``. Ambient endpoints —
``REDIS_URL``, repository ``.env`` values, localhost defaults, or known
development credentials — are never read, never probed, never written.
A separate foreign canary Redis carries sentinel keys whose survival is
asserted after the pressure, proving the load cannot leak beyond its
run-owned target.
"""

from __future__ import annotations

import random
import time

import pytest
import redis.asyncio as redis

from tests.load.conftest import DisposableRedis, assert_run_owned_target


FOREIGN_PERSISTENT_SENTINEL = "rag:foreign_sentinel_persistent"
FOREIGN_EXPIRING_SENTINEL = "rag:foreign_sentinel_expiring"
# Written pressure is hard-capped at 96 MiB (#3447).
PRESSURE_CAP_BYTES = 96 * 1024 * 1024
VALUE_SIZE_KB = 10


async def _connect(handle: DisposableRedis) -> redis.Redis:
    assert_run_owned_target(
        handle.url,
        container_id=handle.container_id,
        label=handle.run_id,
        run_id=handle.run_id,
        password=handle.password,
    )
    return redis.from_url(handle.url, decode_responses=True)


async def _foreign_evicted_keys(handle: DisposableRedis) -> int:
    client = redis.from_url(handle.url, decode_responses=True)
    try:
        info = await client.info("stats")
        return int(info.get("evicted_keys", 0))
    finally:
        await client.aclose()


async def _foreign_sentinels_intact(handle: DisposableRedis) -> bool:
    client = redis.from_url(handle.url, decode_responses=True)
    try:
        return int(await client.exists(FOREIGN_PERSISTENT_SENTINEL, FOREIGN_EXPIRING_SENTINEL)) == 2
    finally:
        await client.aclose()


class TestLoadTargetGuard:
    """The guard refuses every target that is not run-owned (#3447)."""

    _GOOD = {
        "container_id": "a" * 12,
        "label": "run123",
        "run_id": "run123",
        "password": "pw-secret",
    }
    _GOOD_URL = "redis://:pw-secret@127.0.0.1:49152/0"

    def test_accepts_verified_run_owned_target(self) -> None:
        assert_run_owned_target(self._GOOD_URL, **self._GOOD)

    def test_rejects_remote_host(self) -> None:
        with pytest.raises(ValueError, match="non-loopback"):
            assert_run_owned_target("redis://:pw-secret@redis.example.com:49152/0", **self._GOOD)

    def test_rejects_unlabeled_localhost_default_port(self) -> None:
        with pytest.raises(ValueError, match="default/unset port"):
            assert_run_owned_target("redis://:pw-secret@127.0.0.1:6379/0", **self._GOOD)

    def test_rejects_unlabeled_localhost_hostname(self) -> None:
        with pytest.raises(ValueError, match="non-loopback"):
            assert_run_owned_target("redis://:dev_redis_pass@localhost:6379/0", **self._GOOD)

    def test_rejects_missing_credential(self) -> None:
        with pytest.raises(ValueError, match="without a random credential"):
            assert_run_owned_target(
                "redis://127.0.0.1:49152/0",
                container_id=self._GOOD["container_id"],
                label=self._GOOD["label"],
                run_id=self._GOOD["run_id"],
                password="",
            )

    def test_rejects_mismatched_run_label(self) -> None:
        with pytest.raises(ValueError, match="run label"):
            assert_run_owned_target(
                self._GOOD_URL,
                container_id=self._GOOD["container_id"],
                label="other-run",
                run_id=self._GOOD["run_id"],
                password=self._GOOD["password"],
            )

    def test_rejects_credential_mismatch(self) -> None:
        with pytest.raises(ValueError, match="credential"):
            assert_run_owned_target(
                self._GOOD_URL,
                container_id=self._GOOD["container_id"],
                label=self._GOOD["label"],
                run_id=self._GOOD["run_id"],
                password="different-secret",
            )


@pytest.mark.load
class TestLoadRedisEviction:
    """Eviction behavior exercised only on the disposable target."""

    async def test_target_policy_and_memory_are_fixture_owned(
        self, load_redis_target: DisposableRedis
    ) -> None:
        """volatile-lfu + 64 MiB maxmemory come from the fixture, not ambient."""
        client = await _connect(load_redis_target)
        try:
            policy = await client.config_get("maxmemory-policy")
            maxmem = int((await client.config_get("maxmemory")).get("maxmemory", 0))
        finally:
            await client.aclose()
        assert policy.get("maxmemory-policy") == "volatile-lfu"
        assert maxmem == load_redis_target.maxmemory_bytes

    async def test_eviction_under_pressure(
        self,
        load_redis_target: DisposableRedis,
        foreign_redis_canary: DisposableRedis,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Pressure beyond target maxmemory evicts — on the target only (#3447)."""
        foreign_before = await _foreign_evicted_keys(foreign_redis_canary)

        client = await _connect(load_redis_target)
        value_size = VALUE_SIZE_KB * 1024
        # Guarantee pressure beyond the fixture-owned 64 MiB (1.5x), capped hard.
        total_bytes = min(int(load_redis_target.maxmemory_bytes * 1.5), PRESSURE_CAP_BYTES)
        num_keys = total_bytes // value_size
        test_prefix = f"rag:eviction_test:{load_redis_target.run_id}:{int(time.time())}"
        stats_timeseries: list[dict[str, float | int]] = []

        info_start = await client.info("stats")
        try:
            for i in range(num_keys):
                key = f"{test_prefix}:{i}"
                await client.setex(key, 300, "x" * value_size)
                if i % 500 == 0:
                    info = await client.info("stats")
                    stats_timeseries.append(
                        {
                            "timestamp": time.time(),
                            "keys_written": i,
                            "evicted_keys": info.get("evicted_keys", 0),
                        }
                    )
            info_end = await client.info("stats")
            evictions = int(info_end.get("evicted_keys", 0)) - int(
                info_start.get("evicted_keys", 0)
            )
        finally:
            keys = await client.keys(f"{test_prefix}:*")
            if keys:
                await client.delete(*keys)
            await client.aclose()

        report_dir = tmp_path_factory.mktemp("load_reports")
        (report_dir / "redis_stats_timeseries.json").write_text(
            repr(stats_timeseries), encoding="utf-8"
        )

        assert evictions > 0, (
            f"Expected evictions under pressure ({total_bytes // (1024 * 1024)}MiB "
            f"written, maxmemory={load_redis_target.maxmemory_bytes} bytes) on the "
            "run-owned target."
        )
        foreign_after = await _foreign_evicted_keys(foreign_redis_canary)
        assert foreign_after == foreign_before, (
            f"foreign canary eviction counter changed: {foreign_before} -> {foreign_after}"
        )
        assert await _foreign_sentinels_intact(foreign_redis_canary), (
            "foreign canary sentinel keys did not survive the load run"
        )

    async def test_hit_rate_under_zipf_access(
        self,
        load_redis_target: DisposableRedis,
        foreign_redis_canary: DisposableRedis,
    ) -> None:
        """Zipf-like access pattern against the run-owned target only."""
        foreign_before = await _foreign_evicted_keys(foreign_redis_canary)
        client = await _connect(load_redis_target)
        test_prefix = f"rag:zipf_test:{load_redis_target.run_id}"
        try:
            for i in range(50):
                await client.setex(f"{test_prefix}:{i}", 60, f"value_{i}")

            hits = 0
            misses = 0
            for _ in range(200):
                key_id = int(random.paretovariate(1.5)) % 50
                if await client.get(f"{test_prefix}:{key_id}"):
                    hits += 1
                else:
                    misses += 1
        finally:
            keys = await client.keys(f"{test_prefix}:*")
            if keys:
                await client.delete(*keys)
            await client.aclose()

        hit_rate = hits / (hits + misses)
        assert hit_rate >= 0.5, f"Hit rate too low: {hit_rate:.0%}"
        foreign_after = await _foreign_evicted_keys(foreign_redis_canary)
        assert foreign_after == foreign_before
        assert await _foreign_sentinels_intact(foreign_redis_canary)
