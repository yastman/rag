# tests/load/test_load_redis_eviction.py
"""Load tests for Redis LFU eviction behavior."""

import json
import os
import random
import socket
import time
from pathlib import Path

import pytest
import redis.asyncio as redis


REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
class TestLoadRedisEviction:
    """Test Redis eviction behavior under load."""

    @pytest.fixture
    async def redis_client(self):
        if not _is_port_open("localhost", 6379):
            pytest.skip("Redis not running on localhost:6379")
        client = redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
        yield client
        await client.close()

    @pytest.fixture
    def eviction_config(self):
        """Configurable eviction test parameters."""
        return {
            "total_mb": int(os.getenv("EVICTION_TEST_MB", "10")),
            "value_size_kb": 10,
            "sample_interval_sec": 2,
        }

    async def test_redis_lfu_policy_configured(self, redis_client):
        """Verify volatile-lfu eviction policy."""
        policy = await redis_client.config_get("maxmemory-policy")
        assert policy.get("maxmemory-policy") == "volatile-lfu"

    async def test_redis_maxmemory_set(self, redis_client):
        """Verify maxmemory is configured."""
        maxmem = await redis_client.config_get("maxmemory")
        assert int(maxmem.get("maxmemory", 0)) > 0

    async def test_eviction_under_pressure(self, redis_client, eviction_config):
        """Test eviction behavior under write pressure."""
        total_mb = eviction_config["total_mb"]
        value_size_kb = eviction_config["value_size_kb"]

        total_bytes = total_mb * 1024 * 1024
        value_size = value_size_kb * 1024
        num_keys = total_bytes // value_size

        test_prefix = f"rag:eviction_test:{int(time.time())}"
        stats_timeseries = []

        # Get initial stats
        info_start = await redis_client.info("stats")

        # Write keys and sample stats
        for i in range(num_keys):
            key = f"{test_prefix}:{i}"
            value = "x" * value_size
            await redis_client.setex(key, 300, value)

            if i % 100 == 0:
                info = await redis_client.info("stats")
                stats_timeseries.append(
                    {
                        "timestamp": time.time(),
                        "keys_written": i,
                        "evicted_keys": info.get("evicted_keys", 0),
                        "keyspace_hits": info.get("keyspace_hits", 0),
                        "keyspace_misses": info.get("keyspace_misses", 0),
                    }
                )

        # Get final stats
        info_end = await redis_client.info("stats")
        evictions = info_end.get("evicted_keys", 0) - info_start.get("evicted_keys", 0)

        # Cleanup
        keys = await redis_client.keys(f"{test_prefix}:*")
        if keys:
            await redis_client.delete(*keys)

        # Save stats timeseries
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(REPORTS_DIR / "redis_stats_timeseries.json", "w") as f:
            json.dump(stats_timeseries, f, indent=2)

        print(f"\nWrote {num_keys} keys ({total_mb}MB), evictions: {evictions}")

    async def test_hit_rate_under_zipf_access(self, redis_client):
        """Test hit rate under Zipf-like access pattern."""
        test_prefix = f"rag:zipf_test:{int(time.time())}"

        # Populate 50 keys
        for i in range(50):
            await redis_client.setex(f"{test_prefix}:{i}", 60, f"value_{i}")

        # Zipf access (popular keys accessed more)
        hits = 0
        misses = 0

        for _ in range(200):
            key_id = int(random.paretovariate(1.5)) % 50
            result = await redis_client.get(f"{test_prefix}:{key_id}")
            if result:
                hits += 1
            else:
                misses += 1

        # Cleanup
        keys = await redis_client.keys(f"{test_prefix}:*")
        if keys:
            await redis_client.delete(*keys)

        hit_rate = hits / (hits + misses)
        print(f"\nZipf hit rate: {hit_rate:.0%}")

        assert hit_rate >= 0.5, f"Hit rate too low: {hit_rate:.0%}"
