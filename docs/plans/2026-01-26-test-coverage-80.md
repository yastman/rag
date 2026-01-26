# Test Coverage 80% Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Достичь 80% покрытия тестами для `telegram_bot/services/` (текущее: 57%)

**Architecture:** Два параллельных трека — Track 1 фиксит 22 failing теста, Track 2 пишет новые тесты для 5 модулей с низким покрытием. Воркеры работают с разными файлами, синхронизируются через общий файл задач.

**Tech Stack:** pytest, pytest-cov, pytest-asyncio, unittest.mock

---

## Track 1: Fix Failing Tests (Worker 1)

### Task 1.1: Fix filter_extractor price tests

**Files:**
- Modify: `telegram_bot/services/filter_extractor.py`
- Test: `tests/unit/services/test_filter_extractor.py`

**Step 1: Run failing tests to understand errors**

```bash
. venv/bin/activate && pytest tests/unit/services/test_filter_extractor.py::TestFilterExtractorPrice -v --tb=short
```

Expected: 2 FAILED tests with regex mismatch errors

**Step 2: Read the failing test code**

```bash
# Read test expectations
grep -A 20 "test_price_range_pattern_order" tests/unit/services/test_filter_extractor.py
grep -A 20 "test_price_k_suffix_not_captured_by_regex" tests/unit/services/test_filter_extractor.py
```

**Step 3: Read filter_extractor.py price regex**

```bash
grep -A 10 "price" telegram_bot/services/filter_extractor.py | head -40
```

**Step 4: Fix the regex or test based on analysis**

If regex bug → fix in `filter_extractor.py`
If test expectation wrong → fix in test file

**Step 5: Run tests to verify fix**

```bash
pytest tests/unit/services/test_filter_extractor.py::TestFilterExtractorPrice -v
```

Expected: PASSED

**Step 6: Commit**

```bash
git add telegram_bot/services/filter_extractor.py tests/unit/services/test_filter_extractor.py
git commit -m "fix(filter): correct price regex patterns"
```

---

### Task 1.2: Fix filter_extractor distance tests

**Files:**
- Modify: `telegram_bot/services/filter_extractor.py`
- Test: `tests/unit/services/test_filter_extractor.py`

**Step 1: Run failing tests**

```bash
pytest tests/unit/services/test_filter_extractor.py::TestFilterExtractorDistanceToSea -v --tb=short
```

Expected: 2 FAILED (pervaya_liniya_bug, u_morya_bug)

**Step 2: Read test expectations**

```bash
grep -A 20 "test_distance_pervaya_liniya_bug" tests/unit/services/test_filter_extractor.py
grep -A 20 "test_distance_u_morya_bug" tests/unit/services/test_filter_extractor.py
```

**Step 3: Fix distance regex in filter_extractor.py**

Look for patterns like "первая линия", "у моря" and fix extraction logic.

**Step 4: Run tests to verify**

```bash
pytest tests/unit/services/test_filter_extractor.py::TestFilterExtractorDistanceToSea -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add telegram_bot/services/filter_extractor.py tests/unit/services/test_filter_extractor.py
git commit -m "fix(filter): correct distance to sea extraction"
```

---

### Task 1.3: Fix metrics_logger tests

**Files:**
- Investigate: `src/metrics/metrics_logger.py` or similar
- Test: `tests/unit/test_metrics_logger.py`

**Step 1: Check if module exists**

```bash
find . -name "metrics_logger.py" -type f 2>/dev/null
find . -name "*metrics*" -type f -path "*/src/*" 2>/dev/null
```

**Step 2: Read test imports to understand expected location**

```bash
head -20 tests/unit/test_metrics_logger.py
```

**Step 3: Based on findings, either:**

A) Module moved → Update imports in test file
B) Module deleted → Delete test file or mark skip
C) API changed → Update test mocks/assertions

**Step 4: Run tests**

```bash
pytest tests/unit/test_metrics_logger.py -v --tb=short
```

Expected: All 15 PASSED or properly skipped

**Step 5: Commit**

```bash
git add tests/unit/test_metrics_logger.py
git commit -m "fix(tests): update metrics_logger tests for new API"
```

---

### Task 1.4: Fix otel_setup tests

**Files:**
- Investigate: `src/observability/otel_setup.py` or similar
- Test: `tests/unit/test_otel_setup.py`

**Step 1: Run tests to see errors**

```bash
pytest tests/unit/test_otel_setup.py -v --tb=short
```

**Step 2: Read test file**

```bash
cat tests/unit/test_otel_setup.py
```

**Step 3: Fix imports or mocks**

OpenTelemetry tests often fail due to mock issues. Fix the patching.

**Step 4: Run tests**

```bash
pytest tests/unit/test_otel_setup.py -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add tests/unit/test_otel_setup.py
git commit -m "fix(tests): update otel_setup test mocks"
```

---

### Task 1.5: Fix evaluator test

**Files:**
- Test: `tests/unit/test_evaluator.py`

**Step 1: Run test**

```bash
pytest tests/unit/test_evaluator.py::TestCompareEngines::test_compare_engines_improvements -v --tb=short
```

**Step 2: Read and fix**

```bash
grep -A 30 "test_compare_engines_improvements" tests/unit/test_evaluator.py
```

**Step 3: Fix assertion or mock**

**Step 4: Run test**

```bash
pytest tests/unit/test_evaluator.py -v
```

Expected: PASSED

**Step 5: Commit**

```bash
git add tests/unit/test_evaluator.py
git commit -m "fix(tests): update evaluator test assertions"
```

---

### Task 1.6: Verify all Track 1 tests pass

**Step 1: Run all previously failing tests**

```bash
pytest tests/unit/services/test_filter_extractor.py tests/unit/test_metrics_logger.py tests/unit/test_otel_setup.py tests/unit/test_evaluator.py -v
```

Expected: All PASSED

**Step 2: Run full unit test suite**

```bash
pytest tests/unit/ -q
```

Expected: 0 failed

**Step 3: Update task file**

Mark all Track 1 tasks as `[x]` in `docs/plans/2026-01-26-test-coverage-tasks.md`

---

## Track 2: Write New Tests (Worker 2)

### Task 2.1: Write cache.py tests — initialize

**Files:**
- Read: `telegram_bot/services/cache.py`
- Create/Modify: `tests/unit/test_cache_service.py`

**Step 1: Read cache.py initialize method**

```bash
grep -A 30 "async def initialize" telegram_bot/services/cache.py
```

**Step 2: Write failing test**

```python
# tests/unit/test_cache_service.py

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from telegram_bot.services.cache import CacheService


class TestCacheServiceInitialize:
    """Tests for CacheService.initialize()."""

    @pytest.fixture
    def cache_service(self):
        return CacheService(redis_url="redis://localhost:6379")

    @pytest.mark.asyncio
    async def test_initialize_connects_to_redis(self, cache_service):
        """Test that initialize() connects to Redis."""
        with patch("telegram_bot.services.cache.aioredis") as mock_redis:
            mock_client = AsyncMock()
            mock_redis.from_url.return_value = mock_client

            await cache_service.initialize()

            mock_redis.from_url.assert_called_once()
            assert cache_service._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, cache_service):
        """Test that initialize() is idempotent."""
        cache_service._initialized = True
        cache_service.redis_client = MagicMock()

        await cache_service.initialize()

        # Should not reconnect
        assert cache_service._initialized is True
```

**Step 3: Run test to verify it fails**

```bash
pytest tests/unit/test_cache_service.py::TestCacheServiceInitialize -v
```

Expected: FAIL (test doesn't exist yet or assertion fails)

**Step 4: Verify test passes with mocks**

Adjust mocks if needed based on actual implementation.

**Step 5: Run coverage check**

```bash
pytest tests/unit/test_cache_service.py --cov=telegram_bot/services/cache --cov-report=term-missing
```

**Step 6: Commit**

```bash
git add tests/unit/test_cache_service.py
git commit -m "test(cache): add initialize tests"
```

---

### Task 2.2: Write cache.py tests — semantic cache

**Files:**
- Modify: `tests/unit/test_cache_service.py`

**Step 1: Read semantic cache methods**

```bash
grep -A 20 "check_semantic_cache\|store_semantic_cache" telegram_bot/services/cache.py
```

**Step 2: Write tests**

```python
class TestSemanticCache:
    """Tests for semantic cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        service._initialized = True
        return service

    @pytest.mark.asyncio
    async def test_check_semantic_cache_hit(self, cache_service):
        """Test semantic cache hit returns cached answer."""
        cache_service.redis_client.get = AsyncMock(return_value='{"answer": "cached response"}')

        result = await cache_service.check_semantic_cache("test query")

        assert result == "cached response"
        assert cache_service.metrics["semantic"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_check_semantic_cache_miss(self, cache_service):
        """Test semantic cache miss returns None."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.check_semantic_cache("test query")

        assert result is None
        assert cache_service.metrics["semantic"]["misses"] == 1

    @pytest.mark.asyncio
    async def test_store_semantic_cache(self, cache_service):
        """Test storing in semantic cache."""
        cache_service.redis_client.setex = AsyncMock()

        await cache_service.store_semantic_cache("query", "answer")

        cache_service.redis_client.setex.assert_called_once()
```

**Step 3: Run tests**

```bash
pytest tests/unit/test_cache_service.py::TestSemanticCache -v
```

**Step 4: Commit**

```bash
git add tests/unit/test_cache_service.py
git commit -m "test(cache): add semantic cache tests"
```

---

### Task 2.3: Write cache.py tests — embedding cache

**Files:**
- Modify: `tests/unit/test_cache_service.py`

**Step 1: Write tests**

```python
class TestEmbeddingCache:
    """Tests for embedding cache operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        service._initialized = True
        return service

    @pytest.mark.asyncio
    async def test_get_cached_embedding_hit(self, cache_service):
        """Test embedding cache hit."""
        cache_service.redis_client.get = AsyncMock(return_value='[0.1, 0.2, 0.3]')

        result = await cache_service.get_cached_embedding("test query")

        assert result == [0.1, 0.2, 0.3]
        assert cache_service.metrics["embeddings"]["hits"] == 1

    @pytest.mark.asyncio
    async def test_get_cached_embedding_miss(self, cache_service):
        """Test embedding cache miss."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        result = await cache_service.get_cached_embedding("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_store_embedding(self, cache_service):
        """Test storing embedding."""
        cache_service.redis_client.setex = AsyncMock()

        await cache_service.store_embedding("query", [0.1, 0.2, 0.3])

        cache_service.redis_client.setex.assert_called_once()
```

**Step 2: Run and commit**

```bash
pytest tests/unit/test_cache_service.py::TestEmbeddingCache -v
git add tests/unit/test_cache_service.py
git commit -m "test(cache): add embedding cache tests"
```

---

### Task 2.4: Write cache.py tests — conversation history

**Files:**
- Modify: `tests/unit/test_cache_service.py`

**Step 1: Write tests**

```python
class TestConversationHistory:
    """Tests for conversation history operations."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        service._initialized = True
        return service

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, cache_service):
        """Test getting conversation history."""
        cache_service.redis_client.lrange = AsyncMock(return_value=[
            '{"role": "user", "content": "hello"}',
            '{"role": "assistant", "content": "hi"}',
        ])

        result = await cache_service.get_conversation_history(user_id=123, last_n=5)

        assert len(result) == 2
        assert result[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_store_conversation_message(self, cache_service):
        """Test storing conversation message."""
        cache_service.redis_client.rpush = AsyncMock()
        cache_service.redis_client.ltrim = AsyncMock()

        await cache_service.store_conversation_message(123, "user", "hello")

        cache_service.redis_client.rpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_conversation_history(self, cache_service):
        """Test clearing conversation history."""
        cache_service.redis_client.delete = AsyncMock()

        await cache_service.clear_conversation_history(123)

        cache_service.redis_client.delete.assert_called_once()
```

**Step 2: Run and commit**

```bash
pytest tests/unit/test_cache_service.py::TestConversationHistory -v
git add tests/unit/test_cache_service.py
git commit -m "test(cache): add conversation history tests"
```

---

### Task 2.5: Write user_context.py tests

**Files:**
- Read: `telegram_bot/services/user_context.py`
- Create: `tests/unit/test_user_context_service.py`

**Step 1: Read user_context.py**

```bash
cat telegram_bot/services/user_context.py
```

**Step 2: Write tests**

```python
# tests/unit/test_user_context_service.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.user_context import UserContextService


class TestUserContextService:
    """Tests for UserContextService."""

    @pytest.fixture
    def mock_cache(self):
        cache = MagicMock()
        cache.get = AsyncMock(return_value=None)
        cache.set = AsyncMock()
        return cache

    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate = AsyncMock(return_value='{"cities": ["Бургас"]}')
        return llm

    @pytest.fixture
    def service(self, mock_cache, mock_llm):
        return UserContextService(
            cache_service=mock_cache,
            llm_service=mock_llm,
            context_ttl=3600,
            extraction_frequency=5,
        )

    @pytest.mark.asyncio
    async def test_get_context_new_user(self, service, mock_cache):
        """Test getting context for new user returns empty."""
        mock_cache.get = AsyncMock(return_value=None)

        result = await service.get_context(user_id=123)

        assert result == {} or result.get("preferences") == {}

    @pytest.mark.asyncio
    async def test_get_context_existing_user(self, service, mock_cache):
        """Test getting context for existing user."""
        mock_cache.get = AsyncMock(return_value='{"preferences": {"cities": ["Бургас"]}}')

        result = await service.get_context(user_id=123)

        assert "preferences" in result
        assert "Бургас" in result["preferences"].get("cities", [])

    @pytest.mark.asyncio
    async def test_update_from_query(self, service, mock_llm, mock_cache):
        """Test updating context from query."""
        await service.update_from_query(user_id=123, query="Ищу квартиру в Бургасе")

        mock_llm.generate.assert_called_once()
        mock_cache.set.assert_called()
```

**Step 3: Run and commit**

```bash
pytest tests/unit/test_user_context_service.py -v
git add tests/unit/test_user_context_service.py
git commit -m "test(user_context): add UserContextService tests"
```

---

### Task 2.6: Write qdrant.py tests — MMR rerank

**Files:**
- Read: `telegram_bot/services/qdrant.py`
- Modify: `tests/unit/test_qdrant_service.py`

**Step 1: Read mmr_rerank method**

```bash
grep -A 40 "def mmr_rerank" telegram_bot/services/qdrant.py
```

**Step 2: Write tests**

```python
class TestQdrantServiceMMR:
    """Tests for MMR reranking."""

    @pytest.fixture
    def service(self):
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            return QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

    def test_mmr_rerank_basic(self, service):
        """Test basic MMR reranking."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.8},
            {"id": "3", "text": "doc3", "score": 0.7},
        ]
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ]

        result = service.mmr_rerank(
            points=points,
            embeddings=embeddings,
            lambda_mult=0.5,
            top_k=2,
        )

        assert len(result) == 2
        # First should be highest score
        assert result[0]["id"] == "1"

    def test_mmr_rerank_diversity(self, service):
        """Test MMR promotes diversity."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.85},
            {"id": "3", "text": "doc3", "score": 0.8},
        ]
        # Doc 2 similar to doc 1, doc 3 is different
        embeddings = [
            [1.0, 0.0],
            [0.99, 0.01],  # Very similar to doc 1
            [0.0, 1.0],    # Very different
        ]

        result = service.mmr_rerank(
            points=points,
            embeddings=embeddings,
            lambda_mult=0.5,
            top_k=2,
        )

        # With lambda=0.5, should pick doc1 then doc3 (diverse)
        assert result[0]["id"] == "1"
        # Second should prefer diversity
        assert result[1]["id"] == "3"
```

**Step 3: Run and commit**

```bash
pytest tests/unit/test_qdrant_service.py::TestQdrantServiceMMR -v
git add tests/unit/test_qdrant_service.py
git commit -m "test(qdrant): add MMR rerank tests"
```

---

### Task 2.7: Write query_router.py tests

**Files:**
- Read: `telegram_bot/services/query_router.py`
- Create: `tests/unit/test_query_router_full.py`

**Step 1: Read query_router.py**

```bash
cat telegram_bot/services/query_router.py
```

**Step 2: Write comprehensive tests**

```python
# tests/unit/test_query_router_full.py

import pytest

from telegram_bot.services.query_router import (
    QueryType,
    classify_query,
    get_chitchat_response,
    needs_rerank,
)


class TestClassifyQuery:
    """Tests for classify_query function."""

    @pytest.mark.parametrize("query", [
        "Привет",
        "Здравствуйте",
        "Добрый день",
        "Хай",
    ])
    def test_classify_greetings_as_chitchat(self, query):
        """Test greetings classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize("query", [
        "Спасибо",
        "Благодарю",
        "Спасибо большое",
    ])
    def test_classify_thanks_as_chitchat(self, query):
        """Test thanks classified as CHITCHAT."""
        assert classify_query(query) == QueryType.CHITCHAT

    @pytest.mark.parametrize("query", [
        "квартиры",
        "студии",
        "недвижимость",
    ])
    def test_classify_simple_queries(self, query):
        """Test simple queries classified as SIMPLE."""
        result = classify_query(query)
        assert result in (QueryType.SIMPLE, QueryType.COMPLEX)

    @pytest.mark.parametrize("query", [
        "двухкомнатная квартира в Бургасе до 100000 евро у моря",
        "сравни цены в Несебре и Солнечном берегу",
    ])
    def test_classify_complex_queries(self, query):
        """Test complex queries classified as COMPLEX."""
        assert classify_query(query) == QueryType.COMPLEX


class TestGetChitchatResponse:
    """Tests for get_chitchat_response function."""

    def test_hello_response(self):
        """Test response to hello."""
        response = get_chitchat_response("Привет")
        assert response is not None
        assert len(response) > 0

    def test_thanks_response(self):
        """Test response to thanks."""
        response = get_chitchat_response("Спасибо")
        assert response is not None

    def test_non_chitchat_returns_none(self):
        """Test non-chitchat query returns None."""
        response = get_chitchat_response("квартиры в Бургасе")
        assert response is None


class TestNeedsRerank:
    """Tests for needs_rerank function."""

    def test_simple_query_few_results_no_rerank(self):
        """Test SIMPLE with few results skips rerank."""
        assert needs_rerank(QueryType.SIMPLE, num_results=3) is False

    def test_complex_query_needs_rerank(self):
        """Test COMPLEX always needs rerank."""
        assert needs_rerank(QueryType.COMPLEX, num_results=5) is True

    def test_chitchat_no_rerank(self):
        """Test CHITCHAT never needs rerank."""
        assert needs_rerank(QueryType.CHITCHAT, num_results=10) is False
```

**Step 3: Run and commit**

```bash
pytest tests/unit/test_query_router_full.py -v
git add tests/unit/test_query_router_full.py
git commit -m "test(query_router): add comprehensive tests"
```

---

### Task 2.8: Write cesc.py tests — is_personalized_query

**Files:**
- Read: `telegram_bot/services/cesc.py`
- Modify: `tests/test_cesc.py`

**Step 1: Read is_personalized_query**

```bash
grep -A 30 "def is_personalized_query" telegram_bot/services/cesc.py
```

**Step 2: Write tests**

```python
# Add to tests/test_cesc.py

class TestIsPersonalizedQuery:
    """Tests for is_personalized_query function."""

    def test_query_with_moi_marker(self):
        """Test query with 'мои' marker."""
        from telegram_bot.services.cesc import is_personalized_query

        context = {"preferences": {"cities": ["Бургас"]}}
        assert is_personalized_query("покажи мои сохранённые", context) is True

    def test_query_with_preference_marker(self):
        """Test query with preference reference."""
        from telegram_bot.services.cesc import is_personalized_query

        context = {"preferences": {"cities": ["Бургас"]}}
        assert is_personalized_query("как я просил", context) is True

    def test_generic_query_no_personalization(self):
        """Test generic query without markers."""
        from telegram_bot.services.cesc import is_personalized_query

        context = {"preferences": {"cities": ["Бургас"]}}
        assert is_personalized_query("квартиры в Несебре", context) is False

    def test_empty_context_no_personalization(self):
        """Test empty context never personalizes."""
        from telegram_bot.services.cesc import is_personalized_query

        context = {}
        assert is_personalized_query("мои предпочтения", context) is False
```

**Step 3: Run and commit**

```bash
pytest tests/test_cesc.py::TestIsPersonalizedQuery -v
git add tests/test_cesc.py
git commit -m "test(cesc): add is_personalized_query tests"
```

---

### Task 2.9: Verify 80% coverage

**Step 1: Run full coverage report**

```bash
pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing --cov-fail-under=80
```

Expected: PASSED with coverage >= 80%

**Step 2: If coverage < 80%, identify gaps**

```bash
pytest tests/unit/ --cov=telegram_bot/services --cov-report=html
# Open htmlcov/index.html to see uncovered lines
```

**Step 3: Write additional tests for uncovered code**

**Step 4: Final commit**

```bash
git add tests/
git commit -m "test: achieve 80% coverage for telegram_bot/services"
```

---

## Final Verification

### Task 3.1: Run complete test suite

**Step 1: All unit tests pass**

```bash
pytest tests/unit/ -q
```

Expected: `X passed, 0 failed`

**Step 2: Coverage meets target**

```bash
pytest tests/unit/ --cov=telegram_bot/services --cov-fail-under=80 -q
```

Expected: PASSED

**Step 3: Update task file**

Mark all tasks as `[x]` in `docs/plans/2026-01-26-test-coverage-tasks.md`

**Step 4: Final commit**

```bash
git add docs/plans/
git commit -m "docs: mark test coverage tasks complete"
```

---

## Commands Reference

```bash
# Activate venv
. venv/bin/activate

# Run specific test
pytest tests/unit/path/test_file.py::TestClass::test_method -v

# Run with coverage
pytest tests/unit/ --cov=telegram_bot/services --cov-report=term-missing

# Check coverage threshold
pytest tests/unit/ --cov=telegram_bot/services --cov-fail-under=80

# See uncovered lines
pytest tests/unit/ --cov=telegram_bot/services --cov-report=html
```
