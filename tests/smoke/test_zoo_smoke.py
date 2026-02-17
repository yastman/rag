# tests/smoke/test_zoo_smoke.py
"""Zoo smoke tests - verify all services are alive and functional."""

import os
import socket

import httpx
import pytest


def _is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class TestZooHealth:
    """Health checks for services without existing coverage."""

    @pytest.fixture
    def user_base_url(self):
        return os.getenv("USER_BASE_URL", "http://localhost:8003")

    @pytest.fixture
    def litellm_url(self):
        return os.getenv("LLM_BASE_URL", "http://localhost:4000")

    @pytest.mark.skipif(
        not _is_port_open("localhost", 8003), reason="user-base not running (port 8003)"
    )
    @pytest.mark.asyncio
    async def test_user_base_health(self, user_base_url):
        """user-base /health returns status=healthy."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{user_base_url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") in ("ok", "healthy"), (
                f"Expected status 'ok' or 'healthy', got: {data.get('status')}"
            )

    @pytest.mark.skipif(
        not _is_port_open("localhost", 8003), reason="user-base not running (port 8003)"
    )
    @pytest.mark.asyncio
    async def test_user_base_embed_returns_768_dim(self, user_base_url):
        """user-base /embed returns 768-dimensional vector."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{user_base_url}/embed", json={"text": "тестовый запрос"})
            assert response.status_code == 200
            data = response.json()
            embedding = data.get("embedding", [])
            assert len(embedding) == 768, f"Expected 768 dims, got {len(embedding)}"

    @pytest.mark.asyncio
    async def test_litellm_health(self, litellm_url):
        """litellm /health/liveliness returns 200."""
        # Only test if URL points to local LiteLLM proxy
        if "localhost" not in litellm_url and "127.0.0.1" not in litellm_url:
            pytest.skip(f"LLM_BASE_URL points to external API ({litellm_url}), not LiteLLM")
        if not _is_port_open("localhost", 4000):
            pytest.skip("LiteLLM not running (port 4000)")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{litellm_url}/health/liveliness")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_litellm_completion(self, litellm_url):
        """litellm chat completion works."""
        api_key = os.getenv("LLM_API_KEY") or os.getenv("LITELLM_MASTER_KEY")
        if not api_key:
            pytest.skip("LLM_API_KEY or LITELLM_MASTER_KEY not set")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{litellm_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": "Say OK"}],
                    "max_tokens": 5,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert len(data["choices"]) > 0


bge_m3_available = pytest.mark.skipif(
    not _is_port_open("localhost", 8000),
    reason="BGE-M3 not running (port 8000)",
)


class TestBgeM3:
    """Smoke tests for live BGE-M3 embedding service."""

    BGE_M3_URL = "http://localhost:8000"

    @bge_m3_available
    async def test_bge_m3_health_detailed(self):
        """BGE-M3 /health returns model_loaded."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.BGE_M3_URL}/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("model_loaded") is True, f"Expected model_loaded=True, got: {data}"

    @bge_m3_available
    async def test_bge_m3_encode_dense(self):
        """BGE-M3 /encode/dense returns 1024-dim embeddings."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.BGE_M3_URL}/encode/dense",
                json={"texts": ["test query"]},
            )
            assert response.status_code == 200
            data = response.json()
            assert "dense_vecs" in data, (
                f"Missing 'dense_vecs' key in response: {list(data.keys())}"
            )
            vecs = data["dense_vecs"]
            assert len(vecs) >= 1, "Expected at least one embedding"
            assert len(vecs[0]) == 1024, f"Expected 1024-dim vector, got {len(vecs[0])}"

    @bge_m3_available
    async def test_bge_m3_encode_sparse(self):
        """BGE-M3 /encode/sparse returns sparse vectors."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.BGE_M3_URL}/encode/sparse",
                json={"texts": ["test query"]},
            )
            assert response.status_code == 200


@pytest.mark.smoke
class TestZooCache:
    """Cache roundtrip tests (requires live Redis)."""

    @pytest.fixture
    async def cache_service(self):
        """CacheLayerManager for testing."""
        from telegram_bot.integrations.cache import CacheLayerManager

        if not _is_port_open("localhost", 6379):
            pytest.skip("Redis not running (port 6379)")

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        password = os.getenv("REDIS_PASSWORD", "")
        if password and "@" not in redis_url:
            redis_url = redis_url.replace("redis://", f"redis://:{password}@", 1)
        service = CacheLayerManager(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_sparse_cache_roundtrip(self, cache_service):
        """Sparse cache store -> get works."""
        import time

        text = f"zoo_smoke_sparse_test_{int(time.time())}"
        sparse_vector = {"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]}

        await cache_service.store_sparse_embedding(text, sparse_vector, model="bm42")
        cached = await cache_service.get_sparse_embedding(text, model="bm42")

        assert cached is not None
        assert cached["indices"] == [1, 5, 10]
        assert cached["values"] == [0.5, 0.3, 0.2]


@pytest.mark.smoke
class TestZooEndToEnd:
    """End-to-end cache validation (requires live Redis)."""

    @pytest.fixture
    async def cache_service(self):
        """CacheLayerManager for testing."""
        from telegram_bot.integrations.cache import CacheLayerManager

        if not _is_port_open("localhost", 6379):
            pytest.skip("Redis not running (port 6379)")

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        password = os.getenv("REDIS_PASSWORD", "")
        if password and "@" not in redis_url:
            redis_url = redis_url.replace("redis://", f"redis://:{password}@", 1)
        service = CacheLayerManager(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_second_request_has_cache_hits(self, cache_service):
        """Second identical request should have cache hits."""
        import time

        baseline = cache_service.get_metrics()
        base_hits = baseline["analysis"]["hits"]
        base_misses = baseline["analysis"]["misses"]

        query = f"zoo_e2e_test_{int(time.time())}"
        analysis = {"filters": {"test": True}, "semantic_query": query}

        # First request - should be MISS
        key = cache_service.make_hash(query)
        await cache_service.get_exact("analysis", key)
        after_first = cache_service.get_metrics()
        first_misses = after_first["analysis"]["misses"] - base_misses
        assert first_misses >= 1, "First request should miss in analysis tier"

        # Store result
        await cache_service.store_exact("analysis", key, analysis)

        # Second request - should be HIT
        cached = await cache_service.get_exact("analysis", key)
        after_second = cache_service.get_metrics()
        second_hits = after_second["analysis"]["hits"] - base_hits

        assert cached is not None, "Second request should return cached result"
        assert second_hits >= 1, "Second request should be a cache hit in analysis tier"
        assert cached["semantic_query"] == query
