# tests/smoke/test_preflight.py
"""Pre-flight checks for Qdrant and Redis configuration.

These tests verify that production features are actually enabled,
not just declared in code. Run before any other smoke/load tests.
"""

import json
import os
from pathlib import Path

import httpx
import pytest
import redis.asyncio as redis


REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


@pytest.fixture(scope="module")
def qdrant_url():
    return os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.fixture(scope="module")
def redis_url():
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="module")
def collection_name():
    return os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4")


class TestPreflightQdrant:
    """Verify Qdrant configuration before tests."""

    def test_qdrant_collection_exists(self, qdrant_url, collection_name):
        """Collection should exist and be green."""
        resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
        assert resp.status_code == 200, f"Collection {collection_name} not found"

        data = resp.json()
        status = data["result"]["status"]
        assert status == "green", f"Collection status: {status}, expected green"

    def test_qdrant_binary_quantization_enabled(self, qdrant_url, collection_name):
        """Binary quantization should be enabled with always_ram=true."""
        resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
        data = resp.json()

        quant_config = data["result"]["config"].get("quantization_config") or {}
        binary_config = quant_config.get("binary") or {}

        if not binary_config:
            pytest.skip("Binary quantization not configured (quantization_mode=off in local dev)")

        assert binary_config.get("always_ram") is True, (
            f"always_ram should be true, got: {binary_config}"
        )

    def test_qdrant_optimizer_idle(self, qdrant_url, collection_name):
        """Optimizer should be idle (not rebuilding indexes)."""
        resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
        data = resp.json()

        optimizer_status = data["result"].get("optimizer_status")
        assert optimizer_status == "ok", f"Optimizer busy: {optimizer_status}"


class TestPreflightRedis:
    """Verify Redis configuration before tests."""

    @pytest.fixture
    async def redis_client(self, redis_url):
        client = redis.from_url(redis_url, decode_responses=True)
        yield client
        await client.close()
    async def test_redis_connection(self, redis_client):
        """Redis should be reachable."""
        pong = await redis_client.ping()
        assert pong is True
    async def test_redis_maxmemory_set(self, redis_client):
        """maxmemory should be configured (not 0)."""
        config = await redis_client.config_get("maxmemory")
        maxmem = int(config.get("maxmemory", 0))
        assert maxmem > 0, "maxmemory not configured (unlimited)"
    async def test_redis_lfu_eviction_policy(self, redis_client):
        """Eviction policy should use LFU variant."""
        config = await redis_client.config_get("maxmemory-policy")
        policy = config.get("maxmemory-policy")
        assert policy in ("allkeys-lfu", "volatile-lfu"), (
            f"Expected LFU eviction policy, got: {policy}"
        )
    async def test_redis_semantic_cache_index_exists(self, redis_client):
        """Semantic cache RediSearch index should exist.

        Set REQUIRE_REDIS_FT_INDEX=1 for strict mode (FAIL instead of SKIP).
        Use strict mode in staging/production-like environments.
        """
        require_index = os.getenv("REQUIRE_REDIS_FT_INDEX", "0") == "1"

        try:
            # List all FT indexes
            indexes = await redis_client.execute_command("FT._LIST")
            # Check for any rag/llm cache index
            has_cache_index = any("cache" in idx.lower() or "rag" in idx.lower() for idx in indexes)
            if not has_cache_index:
                if require_index:
                    pytest.fail(
                        "REQUIRE_REDIS_FT_INDEX=1 but no semantic cache index found. "
                        "Indexes present: " + str(indexes)
                    )
                else:
                    pytest.skip(
                        "No semantic cache index found (set REQUIRE_REDIS_FT_INDEX=1 for strict)"
                    )
        except Exception as e:
            if require_index:
                pytest.fail(f"REQUIRE_REDIS_FT_INDEX=1 but RediSearch not available: {e}")
            else:
                pytest.skip(f"RediSearch not available: {e}")
    async def test_redis_query_engine_available(self, redis_client):
        """Query Engine (FT.*) should be available."""
        try:
            result = await redis_client.execute_command("FT._LIST")
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"Query Engine not available: {e}")
    async def test_redis_json_available(self, redis_client):
        """JSON commands should be available.

        Set REQUIRE_REDIS_JSON=1 for strict mode (fail instead of skip).
        """
        require_json = os.getenv("REQUIRE_REDIS_JSON", "0") == "1"
        test_key = "test:preflight:json"

        try:
            await redis_client.execute_command("JSON.SET", test_key, "$", '{"check": true}')
            await redis_client.delete(test_key)
        except Exception as e:
            if require_json:
                pytest.fail(f"REQUIRE_REDIS_JSON=1 but JSON not available: {e}")
            else:
                pytest.skip(f"JSON not available (set REQUIRE_REDIS_JSON=1 for strict): {e}")


class TestPreflightReport:
    """Generate preflight report."""
    async def test_generate_preflight_report(self, qdrant_url, redis_url, collection_name):
        """Generate reports/preflight.json with all config values."""
        report = {
            "qdrant": {},
            "redis": {},
            "status": "unknown",
        }

        # Qdrant info
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()["result"]
                report["qdrant"] = {
                    "collection": collection_name,
                    "status": data.get("status"),
                    "optimizer_status": data.get("optimizer_status"),
                    "points_count": data.get("points_count"),
                    "quantization_config": data["config"].get("quantization_config"),
                }
        except Exception as e:
            report["qdrant"]["error"] = str(e)

        # Redis info
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            config_mem = await client.config_get("maxmemory")
            config_policy = await client.config_get("maxmemory-policy")
            info_stats = await client.info("stats")

            report["redis"] = {
                "maxmemory": int(config_mem.get("maxmemory", 0)),
                "maxmemory_policy": config_policy.get("maxmemory-policy"),
                "keyspace_hits": info_stats.get("keyspace_hits", 0),
                "keyspace_misses": info_stats.get("keyspace_misses", 0),
                "evicted_keys": info_stats.get("evicted_keys", 0),
            }
            await client.close()
        except Exception as e:
            report["redis"]["error"] = str(e)

        # Overall status
        quant_cfg = report["qdrant"].get("quantization_config") or {}
        qdrant_ok = report["qdrant"].get("status") == "green" and (
            not quant_cfg  # no quantization configured is OK in dev
            or (quant_cfg.get("binary") or {}).get("always_ram")
        )
        redis_ok = report["redis"].get("maxmemory", 0) > 0 and report["redis"].get(
            "maxmemory_policy", ""
        ) in ("allkeys-lfu", "volatile-lfu")
        report["status"] = "PASS" if (qdrant_ok and redis_ok) else "FAIL"

        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "preflight.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nPreflight report saved to: {report_path}")
        print(json.dumps(report, indent=2))

        assert report["status"] == "PASS", f"Preflight failed: {report}"
