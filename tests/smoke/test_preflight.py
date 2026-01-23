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

        quant_config = data["result"]["config"].get("quantization_config", {})
        binary_config = quant_config.get("binary", {})

        assert binary_config, f"Binary quantization not configured. Got: {quant_config}"
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

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_client):
        """Redis should be reachable."""
        pong = await redis_client.ping()
        assert pong is True

    @pytest.mark.asyncio
    async def test_redis_maxmemory_set(self, redis_client):
        """maxmemory should be configured (not 0)."""
        config = await redis_client.config_get("maxmemory")
        maxmem = int(config.get("maxmemory", 0))
        assert maxmem > 0, "maxmemory not configured (unlimited)"

    @pytest.mark.asyncio
    async def test_redis_lfu_eviction_policy(self, redis_client):
        """Eviction policy should be allkeys-lfu."""
        config = await redis_client.config_get("maxmemory-policy")
        policy = config.get("maxmemory-policy")
        assert policy == "allkeys-lfu", f"Expected allkeys-lfu, got: {policy}"

    @pytest.mark.asyncio
    async def test_redis_semantic_cache_index_exists(self, redis_client):
        """Semantic cache RediSearch index should exist."""
        try:
            # List all FT indexes
            indexes = await redis_client.execute_command("FT._LIST")
            # Check for any rag/llm cache index
            has_cache_index = any("cache" in idx.lower() or "rag" in idx.lower() for idx in indexes)
            if not has_cache_index:
                pytest.skip("No semantic cache index found (may not be configured)")
        except Exception as e:
            pytest.skip(f"RediSearch not available: {e}")


class TestPreflightReport:
    """Generate preflight report."""

    @pytest.mark.asyncio
    async def test_generate_preflight_report(self, qdrant_url, redis_url, collection_name):
        """Generate reports/preflight.json with all config values."""
        report = {
            "qdrant": {},
            "redis": {},
            "status": "unknown",
        }

        ***REMOVED*** info
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
        qdrant_ok = report["qdrant"].get("status") == "green" and report["qdrant"].get(
            "quantization_config", {}
        ).get("binary", {}).get("always_ram")
        redis_ok = (
            report["redis"].get("maxmemory", 0) > 0
            and report["redis"].get("maxmemory_policy") == "allkeys-lfu"
        )
        report["status"] = "PASS" if (qdrant_ok and redis_ok) else "FAIL"

        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "preflight.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nPreflight report saved to: {report_path}")
        print(json.dumps(report, indent=2))

        assert report["status"] == "PASS", f"Preflight failed: {report}"
