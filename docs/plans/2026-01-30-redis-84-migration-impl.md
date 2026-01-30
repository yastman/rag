# Redis 8.4 Migration Implementation Plan

> Execute task-by-task. No special sub-skill required.

**Goal:** Migrate app Redis from `redis/redis-stack-server:7.4.0-v3` to `redis:8.4.0` with capability-based verification.

**Architecture:** Replace Redis Stack with vanilla Redis 8.4 which includes Query Engine (FT.* commands) and JSON natively. Update all tests to check command availability instead of module names. Update documentation to reflect unified Redis 8.4 image.

**Tech Stack:** Docker Compose, Redis 8.4, pytest, Makefile

---

## Prerequisites

Before starting, ensure:
1. Docker is running
2. No critical work depends on current Redis data (cache is ephemeral)
3. You have access to run `docker compose` commands

---

### Task 1: Clean Docker Environment

**Files:**
- None (Docker commands only)

**Step 1: Stop and remove existing Redis container with volumes**

Run:
```bash
# Recommended clean start (stops all services + removes volumes)
docker compose -f docker-compose.dev.yml down -v

# If you must keep other services running, recreate Redis only:
# docker compose -f docker-compose.dev.yml stop redis
# docker compose -f docker-compose.dev.yml rm -fsv redis
```

Expected: Redis container stopped; volumes removed (clean slate).

**Step 2: Verify Redis is stopped**

Run:
```bash
docker ps --filter name=dev-redis
```

Expected: No output (container not running).

**Step 3: Commit (no code changes, skip)**

---

### Task 2: Update docker-compose.dev.yml

**Files:**
- Modify: `docker-compose.dev.yml:31-46`

**Step 1: Read current Redis service configuration**

Run:
```bash
head -50 docker-compose.dev.yml
```

Expected: See current `redis/redis-stack-server:7.4.0-v3` configuration.

**Step 2: Update Redis service to use redis:8.4.0**

Replace lines 31-46 in `docker-compose.dev.yml`:

```yaml
  redis:
    image: redis:8.4.0
    container_name: dev-redis
    restart: unless-stopped
    ports:
      - "127.0.0.1:6379:6379"
    command: >
      redis-server
      --maxmemory 512mb
      --maxmemory-policy allkeys-lfu
      --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
```

**Changes:**
- Image: `redis/redis-stack-server:7.4.0-v3` → `redis:8.4.0`
- Config: `REDIS_ARGS` env → `command` directive
- Removed `environment` section (not needed for redis:8.4.0)

**Step 3: Verify the change**

Run:
```bash
grep -A 15 "^  redis:" docker-compose.dev.yml | head -20
```

Expected: See `image: redis:8.4.0` and `command: >` directive.

**Step 4: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "$(cat <<'EOF'
feat(redis): migrate to redis:8.4.0

Replace redis-stack-server:7.4.0-v3 with vanilla redis:8.4.0.
Redis 8.4 includes Query Engine (FT.*) and JSON natively.

- Use `command` directive instead of REDIS_ARGS env
- Same maxmemory, eviction policy, and AOF settings

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Start Redis and Verify Capabilities

**Files:**
- None (Docker commands only)

**Step 1: Start Redis service**

Run:
```bash
docker compose -f docker-compose.dev.yml up -d redis
```

Expected: Redis container starts.

**Step 2: Wait for Redis to be healthy**

Run:
```bash
for i in {1..30}; do docker exec dev-redis redis-cli ping >/dev/null 2>&1 && break; sleep 0.2; done
docker compose -f docker-compose.dev.yml ps redis
```

Expected: Status shows "healthy" or "running".

**Step 3: Verify Query Engine (FT.*) is available**

Run:
```bash
docker exec dev-redis redis-cli FT._LIST
```

Expected: `(empty array)` or list of index names (no error).

**Step 4: Verify JSON commands are available**

Run:
```bash
docker exec dev-redis redis-cli JSON.SET test '$' '{"a":1}' && \
docker exec dev-redis redis-cli JSON.GET test && \
docker exec dev-redis redis-cli DEL test
```

Expected: `OK`, `{"a":1}`, `(integer) 1`.

**Step 5: Verify Vector search capability**

Run:
```bash
docker exec dev-redis redis-cli FT.CREATE __test_vec_idx ON HASH PREFIX 1 __test_vec: SCHEMA name TEXT vec VECTOR FLAT 6 TYPE FLOAT32 DIM 4 DISTANCE_METRIC COSINE && \
docker exec dev-redis redis-cli FT.DROPINDEX __test_vec_idx
```

Expected: `OK`, `OK`.

**Step 6: Commit (no code changes, skip)**

---

### Task 4: Update tests/test_infrastructure.py

**Files:**
- Modify: `tests/test_infrastructure.py:92-158`
- Test: `tests/test_infrastructure.py`

**Step 1: Write the failing tests first**

Replace `TestRedisInfrastructure` class (lines 92-158) with capability-based tests:

```python
class TestRedisInfrastructure:
    """Redis capability tests (Query Engine, JSON, basic ops)."""

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

**Step 2: Run the tests to verify they pass**

Run:
```bash
pytest tests/test_infrastructure.py::TestRedisInfrastructure -v
```

Expected: All 4 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_infrastructure.py
git commit -m "$(cat <<'EOF'
test(redis): use capability-based checks instead of MODULE LIST

Replace module name checks with command availability tests:
- test_query_engine_available: FT._LIST
- test_vector_search_available: FT.CREATE with VECTOR
- test_json_commands_available: JSON.SET/GET (optional)
- test_set_get_operations: basic Redis ops

REQUIRE_REDIS_JSON=1 makes JSON tests strict.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update tests/smoke/test_preflight.py

**Files:**
- Modify: `tests/smoke/test_preflight.py:98-127`
- Test: `tests/smoke/test_preflight.py`

**Step 1: Add Query Engine and JSON capability tests**

After `test_redis_semantic_cache_index_exists` (around line 127), add:

```python
    @pytest.mark.asyncio
    async def test_redis_query_engine_available(self, redis_client):
        """Query Engine (FT.*) should be available."""
        try:
            result = await redis_client.execute_command("FT._LIST")
            assert isinstance(result, list)
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

**Step 2: Run the preflight tests to verify they pass**

Run:
```bash
pytest tests/smoke/test_preflight.py::TestPreflightRedis -v
```

Expected: All tests PASS (JSON may skip if REQUIRE_REDIS_JSON not set).

**Step 3: Commit**

```bash
git add tests/smoke/test_preflight.py
git commit -m "$(cat <<'EOF'
test(preflight): add Query Engine and JSON capability checks

- test_redis_query_engine_available: verify FT._LIST works
- test_redis_json_available: verify JSON.SET/GET (optional)

REQUIRE_REDIS_JSON=1 makes JSON tests strict.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Update Makefile test-redis Target

**Files:**
- Modify: `Makefile:172-179`

**Step 1: Update test-redis target with Vector and optional JSON checks**

Replace lines 172-179 in `Makefile`:

```makefile
test-redis: ## Verify Redis Query Engine is available
	@echo "$(BLUE)Testing Redis Query Engine...$(NC)"
	@docker exec dev-redis redis-cli FT._LIST > /dev/null 2>&1 || \
		(echo "$(RED)FAIL: FT._LIST not available - Query Engine missing$(NC)" && exit 1)
	@echo "  FT._LIST: OK"
	@docker exec dev-redis redis-cli FT.CREATE __test_vec_idx ON HASH PREFIX 1 __test_vec: SCHEMA name TEXT vec VECTOR FLAT 6 TYPE FLOAT32 DIM 4 DISTANCE_METRIC COSINE > /dev/null 2>&1 || \
		(echo "$(RED)FAIL: Cannot create VECTOR index$(NC)" && exit 1)
	@echo "  FT.CREATE VECTOR: OK"
	@docker exec dev-redis redis-cli FT.DROPINDEX __test_vec_idx > /dev/null 2>&1 || true
	@echo "$(GREEN)Query Engine + Vector Search: OK$(NC)"
	@if [ "$${REQUIRE_REDIS_JSON:-0}" = "1" ]; then \
		docker exec dev-redis redis-cli JSON.SET __test_json '$$' '{"test":1}' > /dev/null 2>&1 || \
			(echo "$(RED)FAIL: JSON.SET not available$(NC)" && exit 1); \
		docker exec dev-redis redis-cli JSON.GET __test_json > /dev/null 2>&1 || \
			(echo "$(RED)FAIL: JSON.GET not available$(NC)" && exit 1); \
		docker exec dev-redis redis-cli DEL __test_json > /dev/null 2>&1 || true; \
		echo "  JSON: OK"; \
	fi
	@echo "$(GREEN)✓ Redis capabilities verified$(NC)"
```

**Step 2: Run the updated test-redis target**

Run:
```bash
make test-redis
```

Expected: All checks pass with "Query Engine + Vector Search: OK".

**Step 3: Commit**

```bash
git add Makefile
git commit -m "$(cat <<'EOF'
chore(make): add VECTOR and optional JSON to test-redis

- Add FT.CREATE with VECTOR type to verify vector search capability
- Optional JSON.SET/GET check via REQUIRE_REDIS_JSON=1
- Clearer output messages

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Update scripts/setup_redis_indexes.py

**Files:**
- Modify: `scripts/setup_redis_indexes.py:42-63` and `scripts/setup_redis_indexes.py:237-248`

**Step 1: Update check_redisearch_module function**

Rename to `check_query_engine` and simplify (lines 42-63):

```python
def check_query_engine(client: redis.Redis) -> bool:
    """Check if Redis Query Engine (FT.* commands) is available.

    Works with both Redis 8.4+ (native) and Redis Stack (module).
    """
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
```

**Step 2: Update the error message (around lines 238-248)**

Replace the error message in `main()`:

```python
    # Check for Query Engine
    print("\nChecking Redis Query Engine...")
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
    print("  Query Engine: OK")
```

**Step 3: Run the script to verify it works**

Run:
```bash
uv run python scripts/setup_redis_indexes.py --dry-run
# or (without uv):
# python3 scripts/setup_redis_indexes.py --dry-run
```

Expected: "Query Engine: OK" (no errors).

**Step 4: Commit**

```bash
git add scripts/setup_redis_indexes.py
git commit -m "$(cat <<'EOF'
refactor(setup-redis): update hints for Redis 8.4

- Rename check_redisearch_module → check_query_engine
- Update error messages to mention Redis 8.4+ as primary option
- Keep Redis Stack as legacy fallback option

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md` (External Services table and references)

**Step 1: Update Redis row in External Services table**

Find and replace:
```markdown
| Redis       | 6379       | Semantic cache (Redis Stack 7.4 with RediSearch/RedisJSON) |
```

With:
```markdown
| Redis       | 6379       | Semantic cache (Redis 8.4, Query Engine + JSON built-in) |
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(claude): update Redis to 8.4 in External Services

Redis 8.4 includes Query Engine and JSON natively,
no longer using Redis Stack image.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Update DOCKER.md Documentation

**Files:**
- Modify: `DOCKER.md:35`

**Step 1: Update Redis row in Databases table**

Find and replace:
```markdown
| **redis** | dev-redis | 6379, 8001 | Redis Stack (cache, RediSearch). UI: http://localhost:8001 |
```

With:
```markdown
| **redis** | dev-redis | 6379 | Redis 8.4 (cache, Query Engine) |
```

**Note:** Port 8001 was listed in docs but never exposed in actual compose file.

**Step 2: Commit**

```bash
git add DOCKER.md
git commit -m "$(cat <<'EOF'
docs(docker): update Redis to 8.4, remove phantom port 8001

- Update from Redis Stack to Redis 8.4
- Remove port 8001 (RedisInsight) which was never exposed
- Simplify description: "Query Engine" instead of "RediSearch"

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Update src/cache/README.md

**Files:**
- Modify: `src/cache/README.md:299-313`

**Step 1: Update Redis Setup example**

Find and replace the Docker Compose example (around lines 299-313):

```markdown
### Redis Setup

```bash
# Docker Compose
services:
  redis:
    image: redis:8.4.0
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save 60 1000
```

**Step 2: Commit**

```bash
git add src/cache/README.md
git commit -m "$(cat <<'EOF'
docs(cache): update Redis image to 8.4.0 in setup example

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Run Full Validation Suite

**Files:**
- None (validation commands only)

**Step 1: Run Makefile redis check**

Run:
```bash
make test-redis
```

Expected: "✓ Redis capabilities verified"

**Step 2: Run infrastructure tests**

Run:
```bash
pytest tests/test_infrastructure.py -v
```

Expected: All tests PASS.

**Step 3: Run preflight tests**

Run:
```bash
pytest tests/smoke/test_preflight.py -v
```

Expected: All tests PASS (some may skip if optional).

**Step 4: Run unit tests**

Run:
```bash
pytest tests/unit/ -v --tb=short
```

Expected: All tests PASS.

**Step 5: Commit (no code changes, skip)**

---

### Task 12: Update Design Document Status

**Files:**
- Modify: `docs/plans/2026-01-30-redis-84-migration-design.md:5`

**Step 1: Update status to Implemented**

Change:
```markdown
**Status:** Draft
```

To:
```markdown
**Status:** Implemented
```

**Step 2: Commit**

```bash
git add docs/plans/2026-01-30-redis-84-migration-design.md
git commit -m "$(cat <<'EOF'
docs(plans): mark Redis 8.4 migration as implemented

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

| Task | Description | Files Modified |
|------|-------------|----------------|
| 1 | Clean Docker environment | Docker commands |
| 2 | Update docker-compose.dev.yml | `docker-compose.dev.yml` |
| 3 | Start Redis and verify capabilities | Docker commands |
| 4 | Update test_infrastructure.py | `tests/test_infrastructure.py` |
| 5 | Update test_preflight.py | `tests/smoke/test_preflight.py` |
| 6 | Update Makefile test-redis | `Makefile` |
| 7 | Update setup_redis_indexes.py | `scripts/setup_redis_indexes.py` |
| 8 | Update CLAUDE.md | `CLAUDE.md` |
| 9 | Update DOCKER.md | `DOCKER.md` |
| 10 | Update src/cache/README.md | `src/cache/README.md` |
| 11 | Run full validation suite | Validation only |
| 12 | Update design document status | `docs/plans/2026-01-30-redis-84-migration-design.md` |

**Total commits:** 10 (Tasks 2, 4, 5, 6, 7, 8, 9, 10, 12)
