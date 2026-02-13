"""Infrastructure tests for Qdrant, Redis, MLflow, Langfuse.

Each test class gracefully skips if the target service is unavailable.
"""

import contextlib
import os
import socket

import httpx
import pytest
import redis.asyncio as aioredis
from qdrant_client import QdrantClient
from redis.exceptions import AuthenticationError as RedisAuthError


def _check_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (OSError, TimeoutError):
            return False


class TestQdrantInfrastructure:
    """Qdrant collection and search tests."""

    @pytest.fixture
    def qdrant_client(self):
        """Create Qdrant client."""
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = os.getenv("QDRANT_API_KEY", "")
        if api_key:
            return QdrantClient(url=url, api_key=api_key, timeout=5.0)
        return QdrantClient(url=url, timeout=5.0)

    def test_collections_exist(self, qdrant_client):
        """Required collections exist."""
        collections = qdrant_client.get_collections().collections
        names = [c.name for c in collections]

        assert "contextual_bulgaria_voyage" in names

    def test_collection_voyage_vector_config(self, qdrant_client):
        """Voyage collection has correct vector config."""
        info = qdrant_client.get_collection("contextual_bulgaria_voyage")

        # Check dense vector config
        dense_config = info.config.params.vectors.get("dense")
        assert dense_config is not None
        assert dense_config.size == 1024  # voyage-3-large

        # Check sparse vector exists (may be named 'sparse' or 'bm42')
        sparse_config = info.config.params.sparse_vectors
        assert sparse_config is not None
        assert len(sparse_config) > 0

    def test_collection_points_count(self, qdrant_client):
        """Collection has expected number of points."""
        info = qdrant_client.get_collection("contextual_bulgaria_voyage")
        assert info.points_count >= 90

    def test_search_dense_returns_results(self, qdrant_client):
        """Dense search returns results (using query_points API)."""
        dummy_vector = [0.1] * 1024

        results = qdrant_client.query_points(
            collection_name="contextual_bulgaria_voyage",
            query=dummy_vector,
            using="dense",
            limit=5,
            with_payload=True,
        )

        assert len(results.points) > 0
        assert results.points[0].score is not None

    def test_search_sparse_works(self, qdrant_client):
        """Sparse search executes without error."""
        from qdrant_client.models import SparseVector

        # Get actual sparse vector name from collection config
        info = qdrant_client.get_collection("contextual_bulgaria_voyage")
        sparse_names = list(info.config.params.sparse_vectors.keys())
        sparse_name = sparse_names[0] if sparse_names else "bm42"

        sparse = SparseVector(indices=[1, 2, 3], values=[0.5, 0.3, 0.2])

        results = qdrant_client.query_points(
            collection_name="contextual_bulgaria_voyage",
            query=sparse,
            using=sparse_name,
            limit=5,
            with_payload=True,
        )

        # Sparse search with random indices may return 0 results
        assert isinstance(results.points, list)


class TestRedisInfrastructure:
    """Redis capability tests (Query Engine, JSON, basic ops)."""

    @pytest.fixture
    async def redis_client(self):
        """Create async Redis client."""
        if not _check_tcp("localhost", 6379):
            pytest.skip("Redis not running on localhost:6379")
        password = os.getenv("REDIS_PASSWORD", "")
        if password:
            url = f"redis://:{password}@localhost:6379"
        else:
            url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = aioredis.from_url(url, decode_responses=True, socket_timeout=5.0)
        try:
            await client.ping()
        except RedisAuthError:
            await client.aclose()
            pytest.skip("Redis requires authentication (set REDIS_PASSWORD)")
        yield client
        await client.aclose()

    @pytest.mark.asyncio
    async def test_query_engine_available(self, redis_client):
        """FT.* commands are available (Query Engine)."""
        try:
            result = await redis_client.execute_command("FT._LIST")
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"Query Engine not available: {e}")

    @pytest.mark.asyncio
    async def test_vector_search_available(self, redis_client):
        """Vector search (FT.CREATE with VECTOR) works."""
        index_name = "test:infra:vec_idx"
        try:
            await redis_client.execute_command(
                "FT.CREATE",
                index_name,
                "ON",
                "HASH",
                "PREFIX",
                "1",
                "test:infra:vec:",
                "SCHEMA",
                "name",
                "TEXT",
                "vec",
                "VECTOR",
                "FLAT",
                "6",
                "TYPE",
                "FLOAT32",
                "DIM",
                "4",
                "DISTANCE_METRIC",
                "COSINE",
            )
            info = await redis_client.execute_command("FT.INFO", index_name)
            assert info is not None
        except Exception as e:
            pytest.fail(f"Vector search not available: {e}")
        finally:
            with contextlib.suppress(Exception):
                await redis_client.execute_command("FT.DROPINDEX", index_name)

    @pytest.mark.asyncio
    async def test_json_commands_available(self, redis_client):
        """JSON.* commands are available."""
        require_json = os.getenv("REQUIRE_REDIS_JSON", "0") == "1"
        test_key = "test:infrastructure:json_check"

        try:
            await redis_client.execute_command(
                "JSON.SET", test_key, "$", '{"name": "test", "value": 123}'
            )
            result = await redis_client.execute_command("JSON.GET", test_key)
            assert "test" in result
        except Exception as e:
            if require_json:
                pytest.fail(f"JSON commands not available: {e}")
            else:
                pytest.skip(f"JSON not available (set REQUIRE_REDIS_JSON=1): {e}")
        finally:
            with contextlib.suppress(Exception):
                await redis_client.delete(test_key)

    @pytest.mark.asyncio
    async def test_set_get_operations(self, redis_client):
        """Basic set/get operations work."""
        test_key = "test:infrastructure:key"
        test_value = "test_value"

        await redis_client.set(test_key, test_value, ex=60)
        result = await redis_client.get(test_key)

        assert result == test_value
        await redis_client.delete(test_key)


class TestMLflowInfrastructure:
    """MLflow tracking server tests."""

    @pytest.mark.asyncio
    async def test_experiments_list(self):
        """Can list experiments."""
        url = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        if not _check_tcp("localhost", 5000):
            pytest.skip("MLflow not running on localhost:5000")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{url}/api/2.0/mlflow/experiments/search",
                json={"max_results": 10},
            )
            assert response.status_code == 200
            data = response.json()
            assert "experiments" in data


class TestLangfuseInfrastructure:
    """Langfuse tracing tests."""

    @pytest.mark.asyncio
    async def test_api_accessible(self):
        """Langfuse API is accessible."""
        url = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        if not _check_tcp("localhost", 3001):
            pytest.skip("Langfuse not running on localhost:3001")

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/public/health")
            assert response.status_code == 200
