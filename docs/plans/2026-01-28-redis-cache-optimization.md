# Redis Cache Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix cache key versioning, restart Redis 8.4, add monitoring metrics, and calibrate distance threshold for Russian language.

**Architecture:** Add `CACHE_SCHEMA_VERSION` constant and `_get_vectorizer_id()` method to namespace all caches by model/version. Update SemanticCache and EmbeddingsCache names to include vectorizer info. Add Redis stats to metrics endpoint.

**Tech Stack:** Redis 8.4.0, RedisVL, pytest, asyncio

---

## Task 1: Restart Redis Container on 8.4.0

**Files:**
- None (Docker operation)

**Step 1: Stop current Redis container**

Run:
```bash
docker compose -f docker-compose.dev.yml stop redis
```

Expected: `Stopping dev-redis ... done`

**Step 2: Remove old container**

Run:
```bash
docker compose -f docker-compose.dev.yml rm -f redis
```

Expected: `Going to remove dev-redis`

**Step 3: Start Redis with new image**

Run:
```bash
docker compose -f docker-compose.dev.yml up -d redis
```

Expected: `Creating dev-redis ... done`

**Step 4: Verify Redis version**

Run:
```bash
docker exec dev-redis redis-cli INFO server | grep redis_version
```

Expected: `redis_version:8.4.0`

**Step 5: Run smoke test**

Run:
```bash
make test-redis
```

Expected: `✓ Redis Query Engine OK`

---

## Task 2: Add Cache Schema Version Constants

**Files:**
- Modify: `telegram_bot/services/cache.py:1-30`
- Test: `tests/unit/test_cache_service.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cache_service.py`:

```python
class TestCacheVersioning:
    """Tests for cache key versioning."""

    def test_cache_schema_version_exists(self):
        """CACHE_SCHEMA_VERSION constant should be defined."""
        from telegram_bot.services.cache import CACHE_SCHEMA_VERSION
        assert CACHE_SCHEMA_VERSION == "v2"

    def test_get_vectorizer_id_local(self):
        """_get_vectorizer_id returns userbase768 when USE_LOCAL_EMBEDDINGS=true."""
        from telegram_bot.services.cache import CacheService
        with patch.dict("os.environ", {"USE_LOCAL_EMBEDDINGS": "true"}):
            service = CacheService(redis_url="redis://localhost:6379")
            assert service._get_vectorizer_id() == "userbase768"

    def test_get_vectorizer_id_voyage(self):
        """_get_vectorizer_id returns voyage1024 when USE_LOCAL_EMBEDDINGS=false."""
        from telegram_bot.services.cache import CacheService
        with patch.dict("os.environ", {"USE_LOCAL_EMBEDDINGS": "false"}):
            service = CacheService(redis_url="redis://localhost:6379")
            assert service._get_vectorizer_id() == "voyage1024"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_service.py::TestCacheVersioning -v`

Expected: FAIL with `ImportError: cannot import name 'CACHE_SCHEMA_VERSION'`

**Step 3: Write minimal implementation**

Add after line 26 in `telegram_bot/services/cache.py`:

```python
# Cache versioning - bump when changing cache structure or models
CACHE_SCHEMA_VERSION = "v2"
```

Add method to `CacheService` class (after `__init__`):

```python
def _get_vectorizer_id(self) -> str:
    """Get vectorizer identifier for cache namespacing.

    Returns:
        'userbase768' for local USER-base model (768-dim)
        'voyage1024' for Voyage API (1024-dim)
    """
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"
    if use_local:
        return "userbase768"
    return "voyage1024"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_service.py::TestCacheVersioning -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py tests/unit/test_cache_service.py
git commit -m "feat(cache): add CACHE_SCHEMA_VERSION and _get_vectorizer_id

- Add CACHE_SCHEMA_VERSION = 'v2' constant
- Add _get_vectorizer_id() method for cache namespacing
- Prevents cache pollution when switching between USER-base and Voyage

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Update SemanticCache Name with Versioning

**Files:**
- Modify: `telegram_bot/services/cache.py:152-154`
- Test: `tests/unit/test_cache_service.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cache_service.py`:

```python
@pytest.mark.asyncio
async def test_semantic_cache_name_includes_version(self, cache_service, mock_redisvl_modules):
    """SemanticCache name should include version and vectorizer."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redisvl_modules["SemanticCache"].reset_mock()

    with patch("telegram_bot.services.cache.redis") as mock_redis_module:
        mock_redis_module.from_url.return_value = mock_redis_client
        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key", "USE_LOCAL_EMBEDDINGS": "false"}):
            await cache_service.initialize()

    call_kwargs = mock_redisvl_modules["SemanticCache"].call_args[1]
    assert call_kwargs["name"] == "sem:v2:voyage1024"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_service.py::TestCacheServiceInitialize::test_semantic_cache_name_includes_version -v`

Expected: FAIL with `AssertionError: assert 'rag_llm_cache' == 'sem:v2:voyage1024'`

**Step 3: Write minimal implementation**

Replace line 152-154 in `telegram_bot/services/cache.py`:

```python
# Old:
self.semantic_cache = SemanticCache(
    name="rag_llm_cache",

# New:
cache_name = f"sem:{CACHE_SCHEMA_VERSION}:{self._get_vectorizer_id()}"
self.semantic_cache = SemanticCache(
    name=cache_name,
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_service.py::TestCacheServiceInitialize::test_semantic_cache_name_includes_version -v`

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py tests/unit/test_cache_service.py
git commit -m "feat(cache): version SemanticCache name with vectorizer ID

- Change from 'rag_llm_cache' to 'sem:v2:{vectorizer}'
- Prevents cache pollution when switching embedding models

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Update EmbeddingsCache Name with Versioning

**Files:**
- Modify: `telegram_bot/services/cache.py:176-178`
- Test: `tests/unit/test_cache_service.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cache_service.py`:

```python
@pytest.mark.asyncio
async def test_embeddings_cache_name_includes_version(self, cache_service, mock_redisvl_modules):
    """EmbeddingsCache name should include version."""
    mock_redis_client = AsyncMock()
    mock_redis_client.ping = AsyncMock(return_value=True)
    mock_redisvl_modules["EmbeddingsCache"].reset_mock()

    with patch("telegram_bot.services.cache.redis") as mock_redis_module:
        mock_redis_module.from_url.return_value = mock_redis_client
        with patch.dict("os.environ", {"VOYAGE_API_KEY": ""}):
            await cache_service.initialize()

    call_kwargs = mock_redisvl_modules["EmbeddingsCache"].call_args[1]
    assert call_kwargs["name"] == "emb:v2"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_service.py::TestCacheServiceInitialize::test_embeddings_cache_name_includes_version -v`

Expected: FAIL with `AssertionError: assert 'bge_m3_embeddings' == 'emb:v2'`

**Step 3: Write minimal implementation**

Replace line 176-178 in `telegram_bot/services/cache.py`:

```python
# Old:
self.embeddings_cache = EmbeddingsCache(
    name="bge_m3_embeddings",

# New:
self.embeddings_cache = EmbeddingsCache(
    name=f"emb:{CACHE_SCHEMA_VERSION}",
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_service.py::TestCacheServiceInitialize::test_embeddings_cache_name_includes_version -v`

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py tests/unit/test_cache_service.py
git commit -m "feat(cache): version EmbeddingsCache name

- Change from 'bge_m3_embeddings' to 'emb:v2'
- Name was misleading (BGE-M3 not used anymore)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Fix Double v1:v1 Bug in Search Cache

**Files:**
- Modify: `telegram_bot/services/cache.py:565,603`
- Test: `tests/unit/test_cache_service.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cache_service.py`:

```python
class TestSearchCacheKeys:
    """Tests for search cache key format."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_search_cache_key_no_double_version(self, cache_service):
        """Search cache key should not have double v1:v1."""
        cache_service.redis_client.get = AsyncMock(return_value=None)

        await cache_service.get_cached_search(
            embedding=[0.1] * 10,
            filters=None,
            index_version="v1"
        )

        call_args = cache_service.redis_client.get.call_args[0][0]
        # Should be search:v2:v1:hash:hash, not search:v1:v1:hash:hash
        assert call_args.startswith("search:v2:")
        assert ":v1:v1:" not in call_args
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_service.py::TestSearchCacheKeys -v`

Expected: FAIL with `AssertionError`

**Step 3: Write minimal implementation**

Replace lines 565 and 603 in `telegram_bot/services/cache.py`:

```python
# Line 565 (get_cached_search) - Old:
key = f"rag:search:v1:{index_version}:{embedding_hash}:{filters_hash}"

# New:
key = f"search:{CACHE_SCHEMA_VERSION}:{index_version}:{embedding_hash}:{filters_hash}"


# Line 603 (store_search_results) - Old:
key = f"rag:search:v1:{index_version}:{embedding_hash}:{filters_hash}"

# New:
key = f"search:{CACHE_SCHEMA_VERSION}:{index_version}:{embedding_hash}:{filters_hash}"
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_service.py::TestSearchCacheKeys -v`

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py tests/unit/test_cache_service.py
git commit -m "fix(cache): remove double version in search cache keys

- Change from 'rag:search:v1:v1:' to 'search:v2:{index_version}:'
- Use CACHE_SCHEMA_VERSION constant

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Add Redis Stats to Metrics

**Files:**
- Modify: `telegram_bot/services/cache.py:675-700`
- Test: `tests/unit/test_cache_service.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cache_service.py`:

```python
class TestCacheMetrics:
    """Tests for cache metrics."""

    @pytest.fixture
    def cache_service(self):
        service = CacheService(redis_url="redis://localhost:6379")
        service.redis_client = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_get_full_metrics_includes_redis_stats(self, cache_service):
        """get_full_metrics should include Redis memory and eviction stats."""
        cache_service.redis_client.info = AsyncMock(side_effect=[
            {"used_memory_human": "10M", "maxmemory_human": "512M"},  # memory
            {"evicted_keys": 5, "keyspace_hits": 100, "keyspace_misses": 20},  # stats
        ])

        metrics = await cache_service.get_full_metrics()

        assert "redis" in metrics
        assert metrics["redis"]["used_memory_human"] == "10M"
        assert metrics["redis"]["evicted_keys"] == 5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cache_service.py::TestCacheMetrics -v`

Expected: FAIL with `AttributeError: 'CacheService' object has no attribute 'get_full_metrics'`

**Step 3: Write minimal implementation**

Add after `get_metrics()` method in `telegram_bot/services/cache.py`:

```python
async def get_full_metrics(self) -> dict[str, Any]:
    """Get comprehensive cache metrics including Redis stats.

    Returns:
        Dict with cache hit rates and Redis memory/eviction stats
    """
    base_metrics = self.get_metrics()

    if not self.redis_client:
        return base_metrics

    try:
        memory_info = await self.redis_client.info("memory")
        stats_info = await self.redis_client.info("stats")

        base_metrics["redis"] = {
            "used_memory_human": memory_info.get("used_memory_human"),
            "maxmemory_human": memory_info.get("maxmemory_human"),
            "evicted_keys": stats_info.get("evicted_keys", 0),
            "keyspace_hits": stats_info.get("keyspace_hits", 0),
            "keyspace_misses": stats_info.get("keyspace_misses", 0),
        }
    except Exception as e:
        logger.warning(f"Failed to get Redis stats: {e}")

    return base_metrics
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cache_service.py::TestCacheMetrics -v`

Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py tests/unit/test_cache_service.py
git commit -m "feat(cache): add get_full_metrics with Redis stats

- Add memory usage (used/max)
- Add eviction and keyspace hit/miss counts
- Helps monitor cache health

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Update Other Cache Key Prefixes

**Files:**
- Modify: `telegram_bot/services/cache.py:506,534,635,666`

**Step 1: Update analyzer cache keys**

Replace lines 506 and 534:

```python
# Line 506 (get_cached_analysis) - Old:
key = f"rag:analysis:v1:{self._hash_key(query)}"

# New:
key = f"analysis:{CACHE_SCHEMA_VERSION}:{self._hash_key(query)}"


# Line 534 (store_analysis) - Old:
key = f"rag:analysis:v1:{self._hash_key(query)}"

# New:
key = f"analysis:{CACHE_SCHEMA_VERSION}:{self._hash_key(query)}"
```

**Step 2: Update rerank cache keys**

Replace lines 635 and 666:

```python
# Line 635 (get_cached_rerank) - Old:
key = f"rag:rerank:v1:{query_hash}:{chunk_hash}"

# New:
key = f"rerank:{CACHE_SCHEMA_VERSION}:{query_hash}:{chunk_hash}"


# Line 666 (store_rerank_results) - Old:
key = f"rag:rerank:v1:{query_hash}:{chunk_hash}"

# New:
key = f"rerank:{CACHE_SCHEMA_VERSION}:{query_hash}:{chunk_hash}"
```

**Step 3: Update sparse cache keys**

Replace lines 439 and 478:

```python
# Line 439 (get_cached_sparse_embedding) - Old:
key = f"sparse:{model_name}:{self._hash_key(text)}"

# New:
key = f"sparse:{CACHE_SCHEMA_VERSION}:{model_name}:{self._hash_key(text)}"


# Line 478 (store_sparse_embedding) - Old:
key = f"sparse:{model_name}:{self._hash_key(text)}"

# New:
key = f"sparse:{CACHE_SCHEMA_VERSION}:{model_name}:{self._hash_key(text)}"
```

**Step 4: Run all cache tests**

Run: `pytest tests/unit/test_cache_service.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/cache.py
git commit -m "refactor(cache): use CACHE_SCHEMA_VERSION in all cache keys

- Update analyzer, rerank, sparse cache key prefixes
- Consistent versioning across all cache types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Final Verification

**Files:**
- None (verification only)

**Step 1: Run all unit tests**

Run: `pytest tests/unit/test_cache_service.py -v`

Expected: All PASS

**Step 2: Run linter**

Run: `make check`

Expected: `✓ Quick check complete`

**Step 3: Verify Redis Query Engine**

Run: `make test-redis`

Expected: `✓ Redis Query Engine OK`

**Step 4: Check new cache keys format**

Run:
```bash
docker exec dev-redis redis-cli KEYS "*" | head -10
```

Expected: Keys with new prefixes (`sem:v2:`, `emb:v2:`, `search:v2:`, etc.)

---

## Testing Checklist

- [ ] Redis 8.4.0 running (`docker exec dev-redis redis-cli INFO server | grep redis_version`)
- [ ] `make test-redis` passes
- [ ] All unit tests pass (`pytest tests/unit/test_cache_service.py -v`)
- [ ] Linter passes (`make check`)
- [ ] New cache keys have `v2` prefix

---

## Rollback

If issues occur, bump `CACHE_SCHEMA_VERSION` to `"v3"` to invalidate problematic keys.

Old keys will naturally expire (TTL 2h-7d).
