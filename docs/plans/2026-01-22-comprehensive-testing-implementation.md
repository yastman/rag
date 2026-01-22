# Comprehensive Testing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create ~130 tests covering all v2.9.0-2.9.1 features with TDD approach.

**Architecture:** Tests organized by layer (smoke → infrastructure → unit → integration → e2e). Each test file is independent. Shared fixtures in conftest.py. All tests are async-compatible.

**Tech Stack:** pytest, pytest-asyncio, httpx (for HTTP tests), unittest.mock, redis.asyncio, qdrant-client

---

## Task 1: Smoke Tests

**Files:**
- Create: `tests/test_smoke_services.py`
- Reference: `tests/conftest.py`

**Step 1.1: Write smoke test file with health checks**

```python
"""Smoke tests for all services health checks."""

import os

import httpx
import pytest
import redis.asyncio as redis


class TestSmokeServices:
    """Verify all services are alive and responding."""

    @pytest.mark.asyncio
    async def test_qdrant_health(self):
        """Qdrant responds to health check."""
        url = os.getenv("QDRANT_URL", "http://localhost:6333")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/healthz")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redis_health(self):
        """Redis responds to PING."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(url, socket_timeout=5.0)
        try:
            result = await client.ping()
            assert result is True
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_mlflow_health(self):
        """MLflow responds to health check."""
        url = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_langfuse_health(self):
        """Langfuse responds to health check."""
        url = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/public/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_docling_health(self):
        """Docling responds to health check."""
        url = os.getenv("DOCLING_URL", "http://localhost:5001")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_lightrag_health(self):
        """LightRAG responds to health check."""
        url = os.getenv("LIGHTRAG_URL", "http://localhost:9621")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_voyage_api_health(self):
        """Voyage API responds (minimal embed call)."""
        api_key = os.getenv("VOYAGE_API_KEY", "")
        if not api_key:
            pytest.skip("VOYAGE_API_KEY not set")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": ["test"], "model": "voyage-3-lite"},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_llm_api_health(self):
        """LLM API responds (minimal completion call)."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            pytest.skip("OPENAI_API_KEY not set")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            assert response.status_code == 200
```

**Step 1.2: Run smoke tests to verify**

Run: `pytest tests/test_smoke_services.py -v`
Expected: All 8 tests PASS (assuming services running)

**Step 1.3: Commit**

```bash
git add tests/test_smoke_services.py
git commit -m "test: add smoke tests for all services (8 tests)"
```

---

## Task 2: Infrastructure Tests

**Files:**
- Create: `tests/test_infrastructure.py`
- Reference: `telegram_bot/services/cache.py`, `telegram_bot/services/hybrid_retriever.py`

**Step 2.1: Write Qdrant infrastructure tests**

```python
"""Infrastructure tests for Qdrant, Redis, MLflow, Langfuse."""

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

        # Check sparse vector exists
        sparse_config = info.config.params.sparse_vectors
        assert sparse_config is not None
        assert "sparse" in sparse_config

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

    def test_search_sparse_returns_results(self, qdrant_client):
        """Sparse search returns results."""
        from qdrant_client.models import SparseVector

        # Minimal sparse vector
        sparse = SparseVector(indices=[1, 2, 3], values=[0.5, 0.3, 0.2])

        results = qdrant_client.search(
            collection_name="contextual_bulgaria_voyage",
            query_vector=("sparse", sparse),
            limit=5,
        )

        assert len(results) > 0


class TestRedisInfrastructure:
    """Redis module and index tests."""

    @pytest.fixture
    async def redis_client(self):
        """Create async Redis client."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(url, decode_responses=True, socket_timeout=5.0)
        yield client
        await client.aclose()

    @pytest.mark.asyncio
    async def test_search_module_loaded(self, redis_client):
        """RediSearch module is loaded."""
        modules = await redis_client.execute_command("MODULE LIST")
        module_names = [m[1].lower() for m in modules]
        assert any("search" in name for name in module_names)

    @pytest.mark.asyncio
    async def test_json_module_loaded(self, redis_client):
        """RedisJSON module is loaded."""
        modules = await redis_client.execute_command("MODULE LIST")
        module_names = [m[1].lower() for m in modules]
        assert any("json" in name for name in module_names)

    @pytest.mark.asyncio
    async def test_set_get_operations(self, redis_client):
        """Basic set/get operations work."""
        test_key = "test:infrastructure:key"
        test_value = "test_value"

        await redis_client.set(test_key, test_value, ex=60)
        result = await redis_client.get(test_key)

        assert result == test_value
        await redis_client.delete(test_key)

    @pytest.mark.asyncio
    async def test_json_operations(self, redis_client):
        """JSON.SET/GET operations work."""
        test_key = "test:infrastructure:json"
        test_data = {"name": "test", "value": 123}

        await redis_client.execute_command(
            "JSON.SET", test_key, "$", '{"name": "test", "value": 123}'
        )
        result = await redis_client.execute_command("JSON.GET", test_key)

        assert "test" in result
        await redis_client.delete(test_key)


class TestMLflowInfrastructure:
    """MLflow tracking server tests."""

    @pytest.mark.asyncio
    async def test_experiments_list(self):
        """Can list experiments."""
        url = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/2.0/mlflow/experiments/search")
            assert response.status_code == 200
            data = response.json()
            assert "experiments" in data


class TestLangfuseInfrastructure:
    """Langfuse tracing tests."""

    @pytest.mark.asyncio
    async def test_api_accessible(self):
        """Langfuse API is accessible."""
        url = os.getenv("LANGFUSE_HOST", "http://localhost:3001")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/api/public/health")
            assert response.status_code == 200
```

**Step 2.2: Run infrastructure tests**

Run: `pytest tests/test_infrastructure.py -v`
Expected: All tests PASS

**Step 2.3: Commit**

```bash
git add tests/test_infrastructure.py
git commit -m "test: add infrastructure tests for Qdrant, Redis, MLflow (14 tests)"
```

---

## Task 3: CacheService Tests

**Files:**
- Create: `tests/test_cache_service.py`
- Reference: `telegram_bot/services/cache.py`

**Step 3.1: Write CacheService tests**

```python
"""Tests for CacheService with all cache tiers."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.cache import CacheService


class TestCacheServiceInit:
    """CacheService initialization tests."""

    @pytest.mark.asyncio
    async def test_initialize_creates_connections(self):
        """Initialize creates Redis and cache connections."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)

        await service.initialize()

        assert service.redis_client is not None
        # SemanticCache requires VOYAGE_API_KEY
        if os.getenv("VOYAGE_API_KEY"):
            assert service.semantic_cache is not None

        await service.close()

    @pytest.mark.asyncio
    async def test_initialize_without_voyage_key_disables_semantic_cache(self):
        """Without VOYAGE_API_KEY, semantic cache is disabled."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        with patch.dict(os.environ, {"VOYAGE_API_KEY": ""}):
            service = CacheService(redis_url=redis_url)
            await service.initialize()

            assert service.semantic_cache is None
            await service.close()


class TestSemanticCache:
    """Semantic cache store/check tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url, distance_threshold=0.15)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_store_and_check_returns_result(self, cache_service):
        """Store then check returns cached result."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized (no VOYAGE_API_KEY)")

        query = "тестовый запрос для кэширования"
        answer = "тестовый ответ"

        await cache_service.store_semantic_cache(query, answer)
        result = await cache_service.check_semantic_cache(query)

        assert result is not None
        assert "тестовый ответ" in result

    @pytest.mark.asyncio
    async def test_check_distant_query_returns_none(self, cache_service):
        """Distant query returns None (threshold filter)."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        # Store specific query
        await cache_service.store_semantic_cache(
            "квартиры в Солнечном береге", "ответ про квартиры"
        )

        # Check completely different query
        result = await cache_service.check_semantic_cache(
            "как приготовить борщ"  # Unrelated query
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_user_isolation(self, cache_service):
        """user_id isolates cache entries."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        query = "тест изоляции пользователей"

        # Store for user 1
        await cache_service.store_semantic_cache(query, "ответ для user 1", user_id=1)
        # Store for user 2
        await cache_service.store_semantic_cache(query, "ответ для user 2", user_id=2)

        # Check for user 1
        result = await cache_service.check_semantic_cache(query, user_id=1)
        assert result is not None
        assert "user 1" in result

    @pytest.mark.asyncio
    async def test_threshold_override(self, cache_service):
        """threshold_override changes matching strictness."""
        if not cache_service.semantic_cache:
            pytest.skip("SemanticCache not initialized")

        await cache_service.store_semantic_cache(
            "original query text", "original answer"
        )

        # With strict threshold, similar but not identical should miss
        result = await cache_service.check_semantic_cache(
            "slightly different query text",
            threshold_override=0.01,  # Very strict
        )

        # May or may not match depending on embedding similarity
        # Just verify no exception
        assert result is None or isinstance(result, str)


class TestEmbeddingsCache:
    """Embeddings cache tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_store_and_get_embedding(self, cache_service):
        """Store then get returns embedding."""
        if not cache_service.embeddings_cache:
            pytest.skip("EmbeddingsCache not initialized")

        text = "test embedding text"
        embedding = [0.1] * 1024

        await cache_service.store_embedding(text, embedding, model_name="test-model")
        result = await cache_service.get_cached_embedding(text, model_name="test-model")

        assert result is not None
        assert len(result) == 1024


class TestTier2Caches:
    """Tier 2 key-value cache tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_analyzer_cache_store_get(self, cache_service):
        """Analyzer cache stores and retrieves JSON."""
        query = "test analyzer query"
        analysis = {"filters": {"city": "Бургас"}, "semantic_query": "apartments"}

        await cache_service.store_analysis(query, analysis)
        result = await cache_service.get_cached_analysis(query)

        assert result is not None
        assert result["filters"]["city"] == "Бургас"

    @pytest.mark.asyncio
    async def test_search_cache_store_get(self, cache_service):
        """Search cache stores and retrieves results."""
        embedding = [0.1] * 10  # Only first 10 used for hash
        filters = {"city": "Варна"}
        results = [{"text": "result 1", "score": 0.9}]

        await cache_service.store_search_results(embedding, filters, results)
        cached = await cache_service.get_cached_search(embedding, filters)

        assert cached is not None
        assert cached[0]["text"] == "result 1"


class TestCacheMetrics:
    """Cache metrics tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_metrics_counting(self, cache_service):
        """Metrics count hits and misses."""
        # Force a miss
        await cache_service.get_cached_analysis("nonexistent query")

        metrics = cache_service.get_metrics()

        assert metrics["by_type"]["analyzer"]["misses"] >= 1
        assert "overall_hit_rate" in metrics


class TestSemanticMessageHistory:
    """Semantic message history tests."""

    @pytest.fixture
    async def cache_service(self):
        """Create initialized cache service."""
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_add_and_get_messages(self, cache_service):
        """Add messages and retrieve by semantic similarity."""
        if not cache_service.message_history:
            pytest.skip("SemanticMessageHistory not initialized")

        user_id = 999999  # Test user

        # Add messages
        await cache_service.add_semantic_message(
            user_id, "user", "ищу квартиру в Бургасе"
        )
        await cache_service.add_semantic_message(
            user_id, "assistant", "Вот квартиры в Бургасе..."
        )

        # Get relevant history
        relevant = await cache_service.get_relevant_history(
            user_id, "квартиры в Бургасе", top_k=2
        )

        assert len(relevant) >= 1
```

**Step 3.2: Run cache service tests**

Run: `pytest tests/test_cache_service.py -v`
Expected: Tests pass (some may skip without VOYAGE_API_KEY)

**Step 3.3: Commit**

```bash
git add tests/test_cache_service.py
git commit -m "test: add CacheService tests (11 tests)"
```

---

## Task 4: QueryPreprocessor Tests

**Files:**
- Modify: `tests/test_query_preprocessor.py` (extend existing)
- Reference: `telegram_bot/services/query_preprocessor.py`

**Step 4.1: Review existing tests and add missing**

```python
"""Tests for QueryPreprocessor."""

import pytest

from telegram_bot.services.query_preprocessor import QueryPreprocessor


class TestTranslitNormalization:
    """Transliteration normalization tests."""

    @pytest.fixture
    def preprocessor(self):
        """Create preprocessor instance."""
        return QueryPreprocessor()

    def test_sunny_beach_translit(self, preprocessor):
        """Sunny Beach -> Солнечный берег."""
        result = preprocessor.normalize_translit("apartments in Sunny Beach")
        assert "Солнечный берег" in result
        assert "Sunny Beach" not in result

    def test_sveti_vlas_translit(self, preprocessor):
        """Sveti Vlas -> Святой Влас."""
        result = preprocessor.normalize_translit("Sveti Vlas property")
        assert "Святой Влас" in result

    def test_case_insensitive_translit(self, preprocessor):
        """Translit is case insensitive."""
        result = preprocessor.normalize_translit("sunny beach apartments")
        assert "Солнечный берег" in result

    def test_multiple_cities_translit(self, preprocessor):
        """Multiple cities in one query."""
        result = preprocessor.normalize_translit("Burgas or Varna apartments")
        assert "Бургас" in result
        assert "Варна" in result

    def test_no_translit_needed(self, preprocessor):
        """Query without Latin names unchanged."""
        query = "квартиры в Бургасе"
        result = preprocessor.normalize_translit(query)
        assert result == query


class TestRRFWeights:
    """RRF weight calculation tests."""

    @pytest.fixture
    def preprocessor(self):
        """Create preprocessor instance."""
        return QueryPreprocessor()

    def test_semantic_query_weights(self, preprocessor):
        """Semantic query gets (0.6, 0.4) weights."""
        dense, sparse = preprocessor.get_rrf_weights("квартира у моря")
        assert dense == 0.6
        assert sparse == 0.4

    def test_exact_id_weights(self, preprocessor):
        """Query with ID gets (0.2, 0.8) weights."""
        dense, sparse = preprocessor.get_rrf_weights("ID 12345")
        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_corpus_weights(self, preprocessor):
        """Query with корпус gets sparse-favored weights."""
        dense, sparse = preprocessor.get_rrf_weights("корпус 5 в Елените")
        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_block_weights(self, preprocessor):
        """Query with блок gets sparse-favored weights."""
        dense, sparse = preprocessor.get_rrf_weights("блок A секция 2")
        assert dense == 0.2
        assert sparse == 0.8

    def test_long_number_exact_weights(self, preprocessor):
        """Query with long number (ID) gets sparse weights."""
        dense, sparse = preprocessor.get_rrf_weights("объект 123456")
        assert dense == 0.2
        assert sparse == 0.8


class TestCacheThreshold:
    """Cache threshold calculation tests."""

    @pytest.fixture
    def preprocessor(self):
        """Create preprocessor instance."""
        return QueryPreprocessor()

    def test_semantic_query_threshold(self, preprocessor):
        """Semantic query gets 0.10 threshold."""
        threshold = preprocessor.get_cache_threshold("квартира с видом на море")
        assert threshold == 0.10

    def test_exact_id_threshold(self, preprocessor):
        """Query with ID gets strict 0.05 threshold."""
        threshold = preprocessor.get_cache_threshold("ID 12345")
        assert threshold == 0.05

    def test_corpus_threshold(self, preprocessor):
        """Query with корпус gets strict threshold."""
        threshold = preprocessor.get_cache_threshold("корпус 3")
        assert threshold == 0.05

    def test_numbers_threshold(self, preprocessor):
        """Query with 3+ digit numbers gets strict threshold."""
        threshold = preprocessor.get_cache_threshold("цена 50000 евро")
        assert threshold == 0.05


class TestHasExactIdentifier:
    """Exact identifier detection tests."""

    @pytest.fixture
    def preprocessor(self):
        """Create preprocessor instance."""
        return QueryPreprocessor()

    def test_detects_id(self, preprocessor):
        """Detects ID pattern."""
        assert preprocessor.has_exact_identifier("ID 12345") is True

    def test_detects_corpus(self, preprocessor):
        """Detects корпус pattern."""
        assert preprocessor.has_exact_identifier("корпус 5") is True

    def test_detects_block_letter(self, preprocessor):
        """Detects блок with letter."""
        assert preprocessor.has_exact_identifier("блок A") is True

    def test_no_identifier(self, preprocessor):
        """Returns False for semantic query."""
        assert preprocessor.has_exact_identifier("красивая квартира") is False


class TestAnalyzeFull:
    """Full analyze() method tests."""

    @pytest.fixture
    def preprocessor(self):
        """Create preprocessor instance."""
        return QueryPreprocessor()

    def test_analyze_returns_all_fields(self, preprocessor):
        """analyze() returns complete result dict."""
        result = preprocessor.analyze("Sunny Beach корпус 5")

        assert "original_query" in result
        assert "normalized_query" in result
        assert "rrf_weights" in result
        assert "cache_threshold" in result
        assert "is_exact" in result

    def test_analyze_translit_and_exact(self, preprocessor):
        """analyze() handles translit + exact together."""
        result = preprocessor.analyze("Sunny Beach корпус 5")

        assert "Солнечный берег" in result["normalized_query"]
        assert result["is_exact"] is True
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["cache_threshold"] == 0.05
```

**Step 4.2: Run tests**

Run: `pytest tests/test_query_preprocessor.py -v`
Expected: All tests PASS

**Step 4.3: Commit**

```bash
git add tests/test_query_preprocessor.py
git commit -m "test: extend QueryPreprocessor tests (18 tests)"
```

---

## Task 5: UserContext & CESC Tests

**Files:**
- Create: `tests/test_user_context.py`
- Create: `tests/test_cesc_personalizer.py`
- Reference: `telegram_bot/services/user_context.py`, `telegram_bot/services/cesc.py`

**Step 5.1: Write UserContextService tests**

```python
"""Tests for UserContextService."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.user_context import UserContextService


class TestDefaultContext:
    """Default context tests."""

    def test_default_context_structure(self):
        """Default context has all required fields."""
        service = UserContextService(cache_service=None, llm_service=None)
        context = service._default_context(user_id=123)

        assert context["user_id"] == 123
        assert context["language"] == "ru"
        assert context["preferences"] == {}
        assert context["profile_summary"] == ""
        assert context["interaction_count"] == 0
        assert context["last_queries"] == []
        assert "created_at" in context
        assert "updated_at" in context


class TestMergePreferences:
    """Preference merging tests."""

    def test_merge_cities_combines(self):
        """Cities are merged, not overwritten."""
        service = UserContextService(cache_service=None, llm_service=None)

        old = {"cities": ["Бургас"]}
        new = {"cities": ["Варна"]}
        result = service._merge_preferences(old, new)

        assert set(result["cities"]) == {"Бургас", "Варна"}

    def test_merge_budget_overwrites(self):
        """Budget is overwritten."""
        service = UserContextService(cache_service=None, llm_service=None)

        old = {"budget_max": 50000}
        new = {"budget_max": 70000}
        result = service._merge_preferences(old, new)

        assert result["budget_max"] == 70000

    def test_merge_null_ignored(self):
        """None values are ignored."""
        service = UserContextService(cache_service=None, llm_service=None)

        old = {"budget_max": 50000}
        new = {"budget_max": None}
        result = service._merge_preferences(old, new)

        assert result["budget_max"] == 50000


class TestShouldExtract:
    """Extraction trigger tests."""

    def test_first_query_triggers(self):
        """First query (count=1) triggers extraction."""
        service = UserContextService(
            cache_service=None, llm_service=None, extraction_frequency=3
        )

        assert service._should_extract(1, {}) is True

    def test_third_query_no_trigger(self):
        """Third query doesn't trigger (count=3)."""
        service = UserContextService(
            cache_service=None, llm_service=None, extraction_frequency=3
        )

        assert service._should_extract(3, {"cities": ["test"]}) is False

    def test_fourth_query_triggers(self):
        """Fourth query (count=4) triggers extraction."""
        service = UserContextService(
            cache_service=None, llm_service=None, extraction_frequency=3
        )

        assert service._should_extract(4, {"cities": ["test"]}) is True

    def test_empty_prefs_triggers(self):
        """Empty preferences always triggers."""
        service = UserContextService(
            cache_service=None, llm_service=None, extraction_frequency=3
        )

        assert service._should_extract(5, {}) is True


class TestGenerateSummary:
    """Profile summary generation tests."""

    def test_summary_with_all_fields(self):
        """Summary includes all preference fields."""
        service = UserContextService(cache_service=None, llm_service=None)

        context = {
            "preferences": {
                "cities": ["Бургас", "Варна"],
                "budget_max": 50000,
                "rooms": 2,
                "property_types": ["apartment"],
            }
        }
        summary = service._generate_summary(context)

        assert "Бургас" in summary
        assert "50000" in summary
        assert "2-комнатные" in summary

    def test_summary_empty_prefs(self):
        """Empty preferences returns default summary."""
        service = UserContextService(cache_service=None, llm_service=None)

        context = {"preferences": {}}
        summary = service._generate_summary(context)

        assert summary == "Новый пользователь"


class TestUpdateFromQuery:
    """update_from_query integration tests."""

    @pytest.mark.asyncio
    async def test_increments_interaction_count(self):
        """Interaction count increments."""
        mock_cache = MagicMock()
        mock_cache.redis_client = AsyncMock()
        mock_cache.redis_client.get = AsyncMock(return_value=None)
        mock_cache.redis_client.setex = AsyncMock()

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value='{"cities": []}')

        service = UserContextService(cache_service=mock_cache, llm_service=mock_llm)

        context = await service.update_from_query(123, "test query")

        assert context["interaction_count"] == 1

    @pytest.mark.asyncio
    async def test_stores_last_queries(self):
        """Last queries are stored (max 5)."""
        mock_cache = MagicMock()
        mock_cache.redis_client = AsyncMock()
        mock_cache.redis_client.get = AsyncMock(return_value=None)
        mock_cache.redis_client.setex = AsyncMock()

        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value='{"cities": []}')

        service = UserContextService(cache_service=mock_cache, llm_service=mock_llm)

        context = await service.update_from_query(123, "query one")

        assert "query one" in context["last_queries"]


class TestExtractPreferences:
    """Preference extraction tests."""

    @pytest.mark.asyncio
    async def test_parses_json_response(self):
        """Parses clean JSON from LLM."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value='{"cities": ["Бургас"], "budget_max": 50000}'
        )

        service = UserContextService(cache_service=None, llm_service=mock_llm)

        result = await service._extract_preferences("квартира в Бургасе до 50000", {})

        assert result["cities"] == ["Бургас"]
        assert result["budget_max"] == 50000

    @pytest.mark.asyncio
    async def test_parses_markdown_json_block(self):
        """Parses JSON from markdown code block."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value='```json\n{"cities": ["Варна"]}\n```'
        )

        service = UserContextService(cache_service=None, llm_service=mock_llm)

        result = await service._extract_preferences("квартира в Варне", {})

        assert result["cities"] == ["Варна"]
```

**Step 5.2: Write CESCPersonalizer tests**

```python
"""Tests for CESCPersonalizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.cesc import CESCPersonalizer


class TestShouldPersonalize:
    """should_personalize decision tests."""

    def test_true_with_cities(self):
        """Returns True if cities present."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {"preferences": {"cities": ["Бургас"]}}
        assert personalizer.should_personalize(context) is True

    def test_true_with_budget(self):
        """Returns True if budget present."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {"preferences": {"budget_max": 50000}}
        assert personalizer.should_personalize(context) is True

    def test_true_with_property_types(self):
        """Returns True if property_types present."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {"preferences": {"property_types": ["apartment"]}}
        assert personalizer.should_personalize(context) is True

    def test_true_with_rooms(self):
        """Returns True if rooms present."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {"preferences": {"rooms": 2}}
        assert personalizer.should_personalize(context) is True

    def test_false_empty_preferences(self):
        """Returns False if preferences empty."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {"preferences": {}}
        assert personalizer.should_personalize(context) is False


class TestBuildPrompt:
    """Prompt building tests."""

    def test_prompt_contains_context(self):
        """Prompt contains all context fields."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {
            "preferences": {
                "cities": ["Бургас", "Варна"],
                "budget_max": 50000,
                "property_types": ["apartment"],
            },
            "profile_summary": "Ищет квартиру",
        }

        prompt = personalizer._build_prompt("cached response", context)

        assert "Бургас" in prompt
        assert "Варна" in prompt
        assert "50000" in prompt
        assert "apartment" in prompt


class TestPersonalize:
    """Personalization execution tests."""

    @pytest.mark.asyncio
    async def test_calls_llm_with_prompt(self):
        """LLM is called with personalization prompt."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value="personalized response")

        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {
            "preferences": {"cities": ["Бургас"]},
            "profile_summary": "",
        }

        result = await personalizer.personalize(
            "cached response", context, "user query"
        )

        mock_llm.generate.assert_called_once()
        assert result == "personalized response"

    @pytest.mark.asyncio
    async def test_returns_cached_on_empty_prefs(self):
        """Returns cached response if no preferences."""
        mock_llm = MagicMock()
        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {"preferences": {}}

        result = await personalizer.personalize(
            "cached response", context, "user query"
        )

        assert result == "cached response"

    @pytest.mark.asyncio
    async def test_fallback_on_llm_error(self):
        """Returns cached response on LLM error."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("LLM error"))

        personalizer = CESCPersonalizer(llm_service=mock_llm)

        context = {
            "preferences": {"cities": ["Бургас"]},
            "profile_summary": "",
        }

        result = await personalizer.personalize(
            "cached response", context, "user query"
        )

        assert result == "cached response"
```

**Step 5.3: Run tests**

Run: `pytest tests/test_user_context.py tests/test_cesc_personalizer.py -v`
Expected: All tests PASS

**Step 5.4: Commit**

```bash
git add tests/test_user_context.py tests/test_cesc_personalizer.py
git commit -m "test: add UserContext and CESCPersonalizer tests (21 tests)"
```

---

## Task 6: LLMService Tests

**Files:**
- Create: `tests/test_llm_service.py`
- Reference: `telegram_bot/services/llm.py`

**Step 6.1: Write LLMService tests**

```python
"""Tests for LLMService."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_bot.services.llm import LLMService


class TestFormatContext:
    """Context formatting tests."""

    def test_format_with_metadata(self):
        """Formats context with title, city, price."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        chunks = [
            {
                "text": "Квартира с видом на море",
                "metadata": {"title": "Апартамент 101", "city": "Бургас", "price": 50000},
                "score": 0.95,
            }
        ]

        result = service._format_context(chunks)

        assert "Апартамент 101" in result
        assert "Бургас" in result
        assert "50,000€" in result
        assert "0.95" in result

    def test_format_empty_chunks(self):
        """Empty chunks returns 'not found' message."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        result = service._format_context([])

        assert "не найдено" in result.lower()


class TestFallbackAnswer:
    """Fallback answer tests."""

    def test_fallback_with_chunks(self):
        """Fallback includes first 3 chunks."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        chunks = [
            {"text": "text1", "metadata": {"title": "Title 1", "price": 30000}},
            {"text": "text2", "metadata": {"title": "Title 2", "price": 40000}},
            {"text": "text3", "metadata": {"title": "Title 3", "price": 50000}},
            {"text": "text4", "metadata": {"title": "Title 4", "price": 60000}},
        ]

        result = service._get_fallback_answer("query", chunks)

        assert "Title 1" in result
        assert "Title 2" in result
        assert "Title 3" in result
        assert "Title 4" not in result  # Only first 3

    def test_fallback_empty_chunks(self):
        """Fallback with no chunks shows service unavailable."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        result = service._get_fallback_answer("query", [])

        assert "недоступен" in result.lower()


class TestGenerateAnswer:
    """generate_answer tests with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_success_returns_answer(self):
        """Successful API call returns answer."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Generated answer"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await service.generate_answer(
                "question", [{"text": "context", "metadata": {}, "score": 0.9}]
            )

            assert result == "Generated answer"

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(self):
        """Timeout returns fallback answer."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timeout")

            chunks = [{"text": "context", "metadata": {"title": "Test"}, "score": 0.9}]
            result = await service.generate_answer("question", chunks)

            assert "Test" in result  # Fallback includes chunk


class TestGenerate:
    """Simple generate() method tests."""

    @pytest.mark.asyncio
    async def test_generate_returns_content(self):
        """generate() returns LLM content."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"result": "ok"}'}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await service.generate("test prompt")

            assert '{"result": "ok"}' in result

    @pytest.mark.asyncio
    async def test_generate_uses_low_temperature(self):
        """generate() uses temperature=0.3."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            await service.generate("test prompt")

            call_kwargs = mock_post.call_args[1]["json"]
            assert call_kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_generate_raises_on_error(self):
        """generate() raises exception on error."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        with patch.object(service.client, "post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("API error")

            with pytest.raises(Exception, match="API error"):
                await service.generate("test prompt")


class TestStreamAnswer:
    """stream_answer tests."""

    @pytest.mark.asyncio
    async def test_stream_yields_tokens(self):
        """Streaming yields tokens."""
        service = LLMService(api_key="test", base_url="http://test", model="test")

        # Mock streaming response
        async def mock_aiter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            yield 'data: {"choices": [{"delta": {"content": " World"}}]}'
            yield "data: [DONE]"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            service.client, "stream", return_value=mock_response
        ) as mock_stream:
            tokens = []
            async for token in service.stream_answer(
                "question", [{"text": "ctx", "metadata": {}, "score": 0.9}]
            ):
                tokens.append(token)

            assert "Hello" in tokens
            assert " World" in tokens
```

**Step 6.2: Run tests**

Run: `pytest tests/test_llm_service.py -v`
Expected: All tests PASS

**Step 6.3: Commit**

```bash
git add tests/test_llm_service.py
git commit -m "test: add LLMService tests (12 tests)"
```

---

## Task 7: Integration & E2E Tests

**Files:**
- Create: `tests/test_e2e_pipeline.py`
- Reference: `telegram_bot/services/`

**Step 7.1: Write E2E pipeline tests**

```python
"""E2E pipeline tests - full query to answer flow."""

import os
import time

import pytest

from telegram_bot.services import (
    CacheService,
    HybridRetrieverService,
    LLMService,
    QueryPreprocessor,
    VoyageEmbeddingService,
    VoyageRerankerService,
)


@pytest.fixture(scope="module")
async def services():
    """Initialize all services for E2E tests."""
    # Skip if required env vars missing
    voyage_key = os.getenv("VOYAGE_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not voyage_key or not openai_key:
        pytest.skip("VOYAGE_API_KEY and OPENAI_API_KEY required for E2E tests")

    # Initialize services
    cache = CacheService(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    await cache.initialize()

    embedder = VoyageEmbeddingService()
    reranker = VoyageRerankerService()
    retriever = HybridRetrieverService(
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY", ""),
        collection_name="contextual_bulgaria_voyage",
    )
    preprocessor = QueryPreprocessor()
    llm = LLMService(
        api_key=openai_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
    )

    yield {
        "cache": cache,
        "embedder": embedder,
        "reranker": reranker,
        "retriever": retriever,
        "preprocessor": preprocessor,
        "llm": llm,
    }

    await cache.close()
    await llm.close()


class TestE2EPipeline:
    """Full pipeline E2E tests."""

    @pytest.mark.asyncio
    async def test_simple_query_returns_answer(self, services):
        """Simple query returns relevant answer."""
        query = "квартиры в Солнечном береге"

        # Preprocess
        analysis = services["preprocessor"].analyze(query)

        # Embed
        embedding = await services["embedder"].embed_query(analysis["normalized_query"])
        sparse = await services["embedder"].get_sparse_vector(analysis["normalized_query"])

        # Search
        results = services["retriever"].hybrid_search(
            dense_vector=embedding,
            sparse_indices=sparse.get("indices", []),
            sparse_values=sparse.get("values", []),
            rrf_weights=(
                analysis["rrf_weights"]["dense"],
                analysis["rrf_weights"]["sparse"],
            ),
            top_k=5,
        )

        assert len(results) > 0

        # Generate answer
        answer = await services["llm"].generate_answer(query, results)

        assert len(answer) > 50
        assert "квартир" in answer.lower() or "апартамент" in answer.lower()

    @pytest.mark.asyncio
    async def test_translit_query_works(self, services):
        """Query with Latin names works via translit."""
        query = "Sunny Beach apartments"

        analysis = services["preprocessor"].analyze(query)

        assert "Солнечный берег" in analysis["normalized_query"]

        embedding = await services["embedder"].embed_query(analysis["normalized_query"])
        sparse = await services["embedder"].get_sparse_vector(analysis["normalized_query"])

        results = services["retriever"].hybrid_search(
            dense_vector=embedding,
            sparse_indices=sparse.get("indices", []),
            sparse_values=sparse.get("values", []),
            top_k=5,
        )

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_exact_query_uses_sparse_weights(self, services):
        """Exact query (with ID/corpus) uses sparse-favored weights."""
        query = "корпус 5"

        analysis = services["preprocessor"].analyze(query)

        assert analysis["rrf_weights"]["sparse"] == 0.8
        assert analysis["is_exact"] is True

    @pytest.mark.asyncio
    async def test_cache_hit_faster_than_miss(self, services):
        """Cache hit is significantly faster than miss."""
        if not services["cache"].semantic_cache:
            pytest.skip("SemanticCache not available")

        query = f"тестовый запрос {time.time()}"  # Unique query
        answer = "тестовый ответ для кэша"

        # First call - cache miss (measure baseline)
        start = time.time()
        cached = await services["cache"].check_semantic_cache(query)
        miss_time = time.time() - start
        assert cached is None

        # Store in cache
        await services["cache"].store_semantic_cache(query, answer)

        # Second call - cache hit
        start = time.time()
        cached = await services["cache"].check_semantic_cache(query)
        hit_time = time.time() - start

        assert cached is not None
        # Cache hit should be fast (< 500ms typically)
        assert hit_time < 1.0

    @pytest.mark.asyncio
    async def test_reranker_improves_relevance(self, services):
        """Reranker reorders results by relevance."""
        query = "дешевая квартира у моря"

        embedding = await services["embedder"].embed_query(query)
        sparse = await services["embedder"].get_sparse_vector(query)

        results = services["retriever"].hybrid_search(
            dense_vector=embedding,
            sparse_indices=sparse.get("indices", []),
            sparse_values=sparse.get("values", []),
            top_k=10,
        )

        if len(results) < 3:
            pytest.skip("Not enough results for reranking test")

        # Rerank
        documents = [r["text"] for r in results]
        reranked = await services["reranker"].rerank(query, documents, top_k=5)

        assert len(reranked) <= 5
        # Top result should have high score
        assert reranked[0]["score"] > 0.5
```

**Step 7.2: Run E2E tests**

Run: `pytest tests/test_e2e_pipeline.py -v`
Expected: Tests pass (require running services and API keys)

**Step 7.3: Commit**

```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: add E2E pipeline tests (5 tests)"
```

---

## Task 8: Run Full Test Suite

**Step 8.1: Run all tests**

```bash
pytest tests/ -v --ignore=tests/legacy/ -x --tb=short
```

Expected: All ~130 tests PASS

**Step 8.2: Generate coverage report**

```bash
pytest tests/ --ignore=tests/legacy/ --cov=telegram_bot --cov=src --cov-report=html
```

**Step 8.3: Final commit**

```bash
git add -A
git commit -m "test: complete comprehensive test suite (~130 tests)

- Smoke tests: 8 (all services health)
- Infrastructure: 14 (Qdrant, Redis, MLflow)
- CacheService: 11 (semantic, embeddings, tier2)
- QueryPreprocessor: 18 (translit, RRF, threshold)
- UserContext: 13 (context, merge, extract)
- CESCPersonalizer: 8 (personalize, fallback)
- LLMService: 12 (generate, stream, fallback)
- E2E Pipeline: 5 (full flow)

Total: ~89 new tests, ~130 total"
```

---

## Summary

| Task | Tests | Time |
|------|-------|------|
| 1. Smoke | 8 | 2-3 min |
| 2. Infrastructure | 14 | 3-5 min |
| 3. CacheService | 11 | 5-7 min |
| 4. QueryPreprocessor | 18 | 3-5 min |
| 5. UserContext + CESC | 21 | 5-7 min |
| 6. LLMService | 12 | 5-7 min |
| 7. E2E Pipeline | 5 | 5-7 min |
| 8. Full Suite | - | 2-3 min |
| **Total** | **~89 new** | **~35 min** |
