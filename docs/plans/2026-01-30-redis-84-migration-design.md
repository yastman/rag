# Redis 8.4 Migration Design

**Date:** 2026-01-30
**Status:** Implemented
**Author:** Claude + User

## Summary

Migrate app Redis from `redis/redis-stack-server:7.4.0-v3` to `redis:8.4.0` with capability-based verification instead of brand-based checks.

## Current State

| File | Image | Status |
|------|-------|--------|
| `docker-compose.dev.yml` | `redis/redis-stack-server:7.4.0-v3` | Works, but outdated (v8 available) |
| `docker-compose.local.yml` | `redis:8.4.0` | Works (FT.*/JSON.* available in Redis 8.4) |
| `redis-langfuse` | `redis:8.4.0` | OK (vanilla Redis, no modules needed) |

### Problem

1. **Inconsistent images** — dev uses Stack 7.4, local uses vanilla 8.4
2. **Outdated Stack** — 7.4.0-v3 is not the latest maintenance release (v8 available)
3. **Brand-based checks** — tests check for module names instead of command availability

## Target State

| File | Image | Notes |
|------|-------|-------|
| `docker-compose.dev.yml` | `redis:8.4.0` | Unified with local |
| `docker-compose.local.yml` | `redis:8.4.0` | Same image |
| `redis-langfuse` | `redis:8.4.0` | Unchanged |

### Key Insight

Per [Redis 8.0 release notes](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/release-notes/redisce/redisos-8.0-release-notes/):

> Redis 8 "merges Redis Stack and Redis Community Edition into a single unified distribution: Redis Open Source". Query Engine and 8 new data structures are now an integral part of Redis 8.

**Redis 8.4 includes FT.* (Query Engine) and JSON.* natively** — no separate Stack image needed.

## Implementation Plan

### Step 1: Pin Target Image

**Target:** `redis:8.4.0`

Principle: Use same image for app Redis in dev/local. Langfuse Redis remains separate.

### Step 2: Update Docker Compose Files

#### 2.1 docker-compose.dev.yml

```yaml
# Before
redis:
  image: redis/redis-stack-server:7.4.0-v3
  container_name: dev-redis
  ports:
    - "127.0.0.1:6379:6379"
  environment:
    REDIS_ARGS: "--maxmemory 512mb --maxmemory-policy allkeys-lfu --appendonly yes"

# After
redis:
  image: redis:8.4.0
  container_name: dev-redis
  ports:
    - "127.0.0.1:6379:6379"
  command: >
    redis-server
    --maxmemory 512mb
    --maxmemory-policy allkeys-lfu
    --appendonly yes
```

**Changes:**
- Image: `redis/redis-stack-server:7.4.0-v3` → `redis:8.4.0`
- Config: `REDIS_ARGS` env → `command` directive (Redis 8 style)

**Note:** Current compose does not expose port 8001, so no removal needed.

#### 2.2 docker-compose.local.yml

```yaml
# Before
redis:
  image: redis:8.4.0
  command: >
    redis-server
    --maxmemory 256mb
    --maxmemory-policy allkeys-lfu
    --appendonly yes

# After (same image, verify config is correct)
redis:
  image: redis:8.4.0
  container_name: rag-redis-local
  ports:
    - "6379:6379"
  command: >
    redis-server
    --maxmemory 256mb
    --maxmemory-policy allkeys-lfu
    --appendonly yes
```

**Note:** Image already correct, just verify FT.* works.

### Step 3: Update Capability Checks

#### 3.1 Makefile (test-redis target)

```makefile
# Before: Checks FT._LIST only
test-redis:
	@docker exec dev-redis redis-cli FT._LIST > /dev/null 2>&1 || \
		(echo "FAIL: FT._LIST not available" && exit 1)
	@docker exec dev-redis redis-cli FT.CREATE __test_idx ON HASH PREFIX 1 __test: SCHEMA name TEXT > /dev/null 2>&1 || \
		(echo "FAIL: Cannot create test index" && exit 1)
	@docker exec dev-redis redis-cli FT.DROPINDEX __test_idx > /dev/null 2>&1 || true

# After: Full capability check (FT + VECTOR + optional JSON)
test-redis:
	@echo "Testing Redis Query Engine..."
	@docker exec dev-redis redis-cli FT._LIST > /dev/null 2>&1 || \
		(echo "FAIL: FT._LIST not available - Query Engine missing" && exit 1)
	@echo "  FT._LIST: OK"
	@docker exec dev-redis redis-cli FT.CREATE __test_vec_idx ON HASH PREFIX 1 __test_vec: SCHEMA name TEXT vec VECTOR FLAT 6 TYPE FLOAT32 DIM 4 DISTANCE_METRIC COSINE > /dev/null 2>&1 || \
		(echo "FAIL: Cannot create VECTOR index" && exit 1)
	@echo "  FT.CREATE VECTOR: OK"
	@docker exec dev-redis redis-cli FT.DROPINDEX __test_vec_idx > /dev/null 2>&1 || true
	@echo "Query Engine + Vector Search: OK"
	@if [ "$${REQUIRE_REDIS_JSON:-0}" = "1" ]; then \
		docker exec dev-redis redis-cli JSON.SET __test_json '$$' '{"test":1}' > /dev/null 2>&1 || \
			(echo "FAIL: JSON.SET not available" && exit 1); \
		docker exec dev-redis redis-cli JSON.GET __test_json > /dev/null 2>&1 || \
			(echo "FAIL: JSON.GET not available" && exit 1); \
		docker exec dev-redis redis-cli DEL __test_json > /dev/null 2>&1 || true; \
		echo "  JSON: OK"; \
	fi
	@echo "Redis capabilities verified"
```

**Notes:**
- `$$` in Makefile escapes to `$` in shell
- FT.CREATE command must be on single line (each Makefile line runs in separate shell)
- VECTOR index with DIM 4 verifies vector search capability (not just TEXT search)
- JSON check is optional, enable with `REQUIRE_REDIS_JSON=1 make test-redis`

#### 3.2 tests/test_infrastructure.py

Update tests to check **capabilities**, not module names. See "Full Test File Changes" section below for complete implementation.

#### 3.3 tests/smoke/test_preflight.py

Already has `REQUIRE_REDIS_FT_INDEX` flag. Add similar for JSON if needed:

```python
# Optional: Add REQUIRE_REDIS_JSON flag
@pytest.mark.asyncio
async def test_redis_json_available(self, redis_client):
    """JSON commands should be available.

    Set REQUIRE_REDIS_JSON=1 for strict mode.
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
            pytest.skip(f"JSON not available: {e}")
```

### Step 4: Update scripts/setup_redis_indexes.py

Replace Stack-specific hints with capability-based messaging:

```python
# Before
def check_redisearch_module(client: redis.Redis) -> bool:
    """Check if RediSearch module is available."""
    # ... checks MODULE LIST for "search" or "ft"

# After
def check_query_engine(client: redis.Redis) -> bool:
    """Check if Redis Query Engine (FT.* commands) is available."""
    try:
        client.execute_command("FT._LIST")
        return True
    except redis.ResponseError as e:
        if "unknown command" in str(e).lower():
            return False
        # Other errors mean command exists but something else failed
        return True
    except Exception:
        return False

# Update error message
if not check_query_engine(client):
    print("\n  ERROR: Redis Query Engine is not available!")
    print("\n  FT.* commands are required for vector search functionality.")
    print("  Solutions:")
    print("\n  Option 1: Use Redis 8.4+ (Query Engine built-in)")
    print("    docker run -p 6379:6379 redis:8.4.0")
    print("\n  Option 2: Use Redis Stack (legacy)")
    print("    docker run -p 6379:6379 redis/redis-stack-server:latest")
    print("\n  More info: https://redis.io/docs/latest/develop/whats-new/8-0/")
    sys.exit(1)
```

### Step 5: Update Documentation

#### 5.1 CLAUDE.md

```markdown
# Before
| Redis       | 6379       | Semantic cache (Redis Stack 7.4 with RediSearch/RedisJSON) |

# After
| Redis       | 6379       | Semantic cache (Redis 8.4, Query Engine + JSON built-in) |
```

#### 5.2 DOCKER.md

```markdown
# Before
| **redis** | dev-redis | 6379, 8001 | Redis Stack (cache, RediSearch). UI: http://localhost:8001 |

# After
| **redis** | dev-redis | 6379 | Redis 8.4 (cache, Query Engine) |
```

**Note:** Current DOCKER.md already shows port 8001, but actual compose doesn't expose it. Update docs to match reality.

#### 5.3 src/cache/README.md

Update Redis Setup section:

```markdown
# Before
services:
  redis:
    image: redis:8.2-alpine
    ...

# After
services:
  redis:
    image: redis:8.4.0
    ...
```

## Validation Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Clean start | `docker compose -f docker-compose.dev.yml down -v` | Volumes removed |
| Docker starts | `docker compose -f docker-compose.dev.yml up -d` | All services healthy |
| Query Engine | `docker exec dev-redis redis-cli FT._LIST` | Empty list or index names |
| FT.CREATE | `docker exec dev-redis redis-cli FT.CREATE test ON HASH PREFIX 1 t: SCHEMA n TEXT` | OK |
| FT.DROPINDEX | `docker exec dev-redis redis-cli FT.DROPINDEX test` | OK |
| JSON.SET | `docker exec dev-redis redis-cli JSON.SET test '$' '{"a":1}'` | OK |
| JSON.GET | `docker exec dev-redis redis-cli JSON.GET test` | `{"a":1}` |
| Makefile check | `make test-redis` | Pass |
| Infrastructure tests | `pytest tests/test_infrastructure.py -v` | Pass |
| Preflight tests | `pytest tests/smoke/test_preflight.py -v` | Pass |
| **E2E SemanticCache** | `python -c "..."` (see below) | Index created, store/check works |
| Unit tests | `pytest tests/unit/ -v` | Pass |

### E2E SemanticCache Test

**Prerequisites:**
- Either `VOYAGE_API_KEY` set (uses Voyage API for embeddings)
- Or `USE_LOCAL_EMBEDDINGS=true` + user-base service running

```python
# Run after docker-compose up
# Requires: VOYAGE_API_KEY or USE_LOCAL_EMBEDDINGS=true
import asyncio
import os
from telegram_bot.services.cache import CacheService

async def test_cache():
    # Verify prereqs
    voyage_key = os.getenv("VOYAGE_API_KEY", "")
    use_local = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"

    if not voyage_key and not use_local:
        print("SKIP: Set VOYAGE_API_KEY or USE_LOCAL_EMBEDDINGS=true")
        return

    cache = CacheService(redis_url="redis://localhost:6379")
    await cache.initialize()

    # Verify semantic cache initialized
    assert cache.semantic_cache is not None, (
        "SemanticCache not initialized! "
        "Check VOYAGE_API_KEY or USE_LOCAL_EMBEDDINGS + user-base service"
    )

    # Store and retrieve
    await cache.store_semantic_cache("test query for e2e", "test answer for e2e")
    result = await cache.check_semantic_cache("test query for e2e")

    # Note: semantic cache uses vector similarity, exact match not guaranteed
    # but with same query it should return the answer
    assert result is not None, "SemanticCache check returned None"
    assert "test answer" in result, f"Unexpected result: {result}"

    await cache.close()
    print("SemanticCache E2E: OK")

asyncio.run(test_cache())
```

**What this verifies:**
1. Redis 8.4 FT.* commands work for RedisVL
2. SemanticCache creates index automatically
3. Vector store/search pipeline works end-to-end

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| FT.* not in redis:8.4.0 | Very Low | High | Already verified: `redis:8.4.0` includes Query Engine |
| RedisVL incompatibility | Low | Medium | Test SemanticCache initialization |
| AOF/RDB format incompatibility | Medium | Low | Run `docker compose down -v` for clean start |
| Old indexes from Stack 7.4 | Medium | Low | Delete redis_data volume before upgrade |

**Migration requirement:** Run `docker compose down -v` to remove old volumes. Cache is ephemeral, no data migration needed.

## Files to Modify

### Infrastructure (Docker)

| File | Change |
|------|--------|
| `docker-compose.dev.yml` | Image `redis:8.4.0` + `command` directive |
| `docker-compose.local.yml` | Already correct, verify FT.* works |

### Tests (Capability-based)

| File | Change | Priority |
|------|--------|----------|
| `tests/test_infrastructure.py` | Replace MODULE LIST with capability checks (FT + VECTOR + optional JSON) | **P0** |
| `tests/smoke/test_preflight.py` | Add optional `test_redis_json_available` | P1 |
| `tests/integration/test_docker_services.py` | Already OK (just pings Redis) | - |
| `tests/smoke/test_smoke_cache.py` | Already OK (uses CacheService) | - |
| `tests/unit/test_cache_service.py` | Already OK (mocks redisvl) | - |
| `tests/unit/test_redis_semantic_cache.py` | Already OK (mocks redis) | - |
| `tests/test_redis_cache.py` | Legacy file, uses old `RedisSemanticCache` | P2 (consider removal) |

### Scripts

| File | Change |
|------|--------|
| `Makefile` | Add optional JSON check to `test-redis` target |
| `scripts/setup_redis_indexes.py` | Update hints: "Redis 8.4+" instead of "Redis Stack" |

### Documentation

| File | Change |
|------|--------|
| `CLAUDE.md` | Update Redis description (Redis 8.4, Query Engine) |
| `DOCKER.md` | Remove port 8001 reference, update to Redis 8.4 |
| `src/cache/README.md` | Update image version in examples |

### Full Test File Changes

#### tests/test_infrastructure.py (P0)

```python
class TestRedisInfrastructure:
    """Redis capability tests."""

    @pytest.fixture
    async def redis_client(self):
        """Create async Redis client."""
        url = os.getenv("REDIS_URL", "redis://localhost:6379")
        client = redis.from_url(url, decode_responses=True, socket_timeout=5.0)
        yield client
        await client.aclose()

    @pytest.mark.asyncio
    async def test_query_engine_available(self, redis_client):
        """FT.* commands are available (Query Engine)."""
        try:
            result = await redis_client.execute_command("FT._LIST")
            assert isinstance(result, list)  # Empty list is OK
        except Exception as e:
            pytest.fail(f"Query Engine not available: {e}")

    @pytest.mark.asyncio
    async def test_vector_search_available(self, redis_client):
        """Vector search (FT.CREATE with VECTOR) works."""
        index_name = "test:infra:vec_idx"
        try:
            # Create index with VECTOR field (DIM 4 for minimal test)
            await redis_client.execute_command(
                "FT.CREATE", index_name, "ON", "HASH",
                "PREFIX", "1", "test:infra:vec:",
                "SCHEMA", "name", "TEXT",
                "vec", "VECTOR", "FLAT", "6",
                "TYPE", "FLOAT32", "DIM", "4", "DISTANCE_METRIC", "COSINE"
            )
            # Verify index exists
            info = await redis_client.execute_command("FT.INFO", index_name)
            assert info is not None
        except Exception as e:
            pytest.fail(f"Vector search not available: {e}")
        finally:
            try:
                await redis_client.execute_command("FT.DROPINDEX", index_name)
            except Exception:
                pass

    @pytest.mark.asyncio
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
            try:
                await redis_client.delete(test_key)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_set_get_operations(self, redis_client):
        """Basic set/get operations work."""
        test_key = "test:infrastructure:key"
        test_value = "test_value"

        await redis_client.set(test_key, test_value, ex=60)
        result = await redis_client.get(test_key)

        assert result == test_value
        await redis_client.delete(test_key)
```

#### tests/smoke/test_preflight.py (P1)

Add after `test_redis_semantic_cache_index_exists`:

```python
@pytest.mark.asyncio
async def test_redis_query_engine_available(self, redis_client):
    """Query Engine (FT.*) should be available."""
    try:
        await redis_client.execute_command("FT._LIST")
    except Exception as e:
        pytest.fail(f"Query Engine not available: {e}")

@pytest.mark.asyncio
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
```

## Decision: JSON Requirement

**Question:** Should JSON.* commands be strictly required?

**Analysis:**
- `tests/test_infrastructure.py` — tests JSON.SET/GET
- No production code uses JSON.* directly
- RedisVL SemanticCache uses HASH, not JSON

**Decision:** JSON is **optional everywhere** via `REQUIRE_REDIS_JSON` env var:
- `REQUIRE_REDIS_JSON=0` (default): JSON tests skip if unavailable
- `REQUIRE_REDIS_JSON=1`: JSON tests fail if unavailable

This applies to:
- `make test-redis`
- `tests/test_infrastructure.py::test_json_commands_available`
- `tests/smoke/test_preflight.py::test_redis_json_available`

## Cache Configuration (No Changes Needed)

CacheService configuration remains unchanged:

| Setting | Value | Notes |
|---------|-------|-------|
| `semantic_cache_ttl` | 48h | LLM answers |
| `embeddings_cache_ttl` | 7d | Query embeddings |
| `analyzer_cache_ttl` | 24h | QueryAnalyzer results |
| `search_cache_ttl` | 2h | Qdrant results |
| `distance_threshold` | 0.20 | Cosine distance for semantic match |

RedisVL SemanticCache creates FT index automatically on first store. No manual index setup required.

**Key prefixes:**
- `sem:v2:{vectorizer}` — SemanticCache
- `emb:v2` — EmbeddingsCache
- `sparse:v2:{model}` — Sparse embeddings
- `analysis:v2` — QueryAnalyzer
- `search:v2:{index_ver}` — Search results
- `rerank:v2` — Rerank results
- `conversation:{user_id}` — Chat history

## Migration Steps Summary

### Phase 1: Infrastructure

1. `docker compose -f docker-compose.dev.yml down -v` — clean volumes
2. Edit `docker-compose.dev.yml` (Step 2.1)
3. `docker compose -f docker-compose.dev.yml up -d`
4. Verify manually:
   ```bash
   docker exec dev-redis redis-cli FT._LIST
   docker exec dev-redis redis-cli JSON.SET test '$' '{"a":1}'
   docker exec dev-redis redis-cli JSON.GET test
   docker exec dev-redis redis-cli DEL test
   ```

### Phase 2: Tests

5. Update `tests/test_infrastructure.py` (capability-based)
6. Update `tests/smoke/test_preflight.py` (add JSON check)
7. Run tests:
   ```bash
   pytest tests/test_infrastructure.py -v
   pytest tests/smoke/test_preflight.py -v
   ```

### Phase 3: Scripts & Docs

8. Update `Makefile` (test-redis target)
9. Update `scripts/setup_redis_indexes.py` (hints)
10. Update documentation (CLAUDE.md, DOCKER.md, src/cache/README.md)

### Phase 4: Validation

11. `make test-redis` — Makefile check
12. E2E SemanticCache test (see Validation Checklist)
13. `pytest tests/unit/ -v` — unit tests
14. `pytest tests/smoke/ -v` — smoke tests

## References

- [Redis 8.0 Release Notes](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/release-notes/redisce/redisos-8.0-release-notes/) — Query Engine merger
- [Redis 8.4 Release Notes](https://redis.io/docs/latest/develop/whats-new/8-4/) — FT.HYBRID, performance improvements
- [Redis Docker Hub](https://hub.docker.com/_/redis) — Official images
- [RedisVL Documentation](https://redis.io/docs/latest/develop/ai/redisvl/) — SemanticCache requirements
