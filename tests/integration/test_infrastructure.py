"""Infrastructure tests for Qdrant, Redis, MLflow, Langfuse."""

import contextlib
import os

import httpx
import pytest
import redis.asyncio as redis
from qdrant_client import QdrantClient


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
        # legal_documents may not exist in all envs
        # assert "legal_documents" in names

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
        assert len(sparse_config) > 0  # At least one sparse vector configured

    def test_collection_points_count(self, qdrant_client):
        """Collection has expected number of points."""
        info = qdrant_client.get_collection("contextual_bulgaria_voyage")
        assert info.points_count >= 90  # At least 90 documents

    def test_search_dense_returns_results(self, qdrant_client):
        """Dense search returns results."""
        # Use random vector for test
        dummy_vector = [0.1] * 1024

        results = qdrant_client.search(
            collection_name="contextual_bulgaria_voyage",
            query_vector=("dense", dummy_vector),
            limit=5,
        )

        assert len(results) > 0
        assert results[0].score is not None

    def test_search_sparse_works(self, qdrant_client):
        """Sparse search executes without error."""
        from qdrant_client.models import NamedSparseVector, SparseVector

        # Get actual sparse vector name from collection config
        info = qdrant_client.get_collection("contextual_bulgaria_voyage")
        sparse_names = list(info.config.params.sparse_vectors.keys())
        sparse_name = sparse_names[0] if sparse_names else "bm42"

        # Minimal sparse vector using NamedSparseVector
        # Note: random indices may not match any documents (returns empty)
        sparse = NamedSparseVector(
            name=sparse_name,
            vector=SparseVector(indices=[1, 2, 3], values=[0.5, 0.3, 0.2]),
        )

        results = qdrant_client.search(
            collection_name="contextual_bulgaria_voyage",
            query_vector=sparse,
            limit=5,
        )

        # Sparse search with random indices may return 0 results
        # The important thing is it executes without error
        assert isinstance(results, list)


class TestRedisInfrastructure:
    """Redis capability tests (Query Engine, JSON, basic ops)."""

    @pytest.fixture
    async def redis_client(self):
        """Create async Redis client."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(url, decode_responses=True, socket_timeout=5.0)
        yield client
        await client.aclose()
    async def test_query_engine_available(self, redis_client):
        """FT.* commands are available (Query Engine)."""
        try:
            result = await redis_client.execute_command("FT._LIST")
            assert isinstance(result, list)  # Empty list is OK
        except Exception as e:
            pytest.fail(f"Query Engine not available: {e}")
    async def test_vector_search_available(self, redis_client):
        """Vector search (FT.CREATE with VECTOR) works."""
        index_name = "test:infra:vec_idx"
        try:
            # Create index with VECTOR field (DIM 4 for minimal test)
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
            # Verify index exists
            info = await redis_client.execute_command("FT.INFO", index_name)
            assert info is not None
        except Exception as e:
            pytest.fail(f"Vector search not available: {e}")
        finally:
            with contextlib.suppress(Exception):
                await redis_client.execute_command("FT.DROPINDEX", index_name)
    async def test_json_commands_available(self, redis_client):
        """JSON.* commands are available.

        Set REQUIRE_REDIS_JSON=1 for strict mode (fail instead of skip).
        """
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
    async def test_experiments_list(self):
        """Can list experiments."""
        url = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        async with httpx.AsyncClient(timeout=5.0) as client:
            # MLflow search experiments requires POST with max_results
            response = await client.post(
                f"{url}/api/2.0/mlflow/experiments/search",
                json={"max_results": 10},
            )
            assert response.status_code == 200
            data = response.json()
            assert "experiments" in data


class TestLangfuseInfrastructure:
    """Langfuse tracing tests."""
    async def test_api_accessible(self):
        """Langfuse API is accessible."""
        url = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/public/health")
            assert response.status_code == 200
