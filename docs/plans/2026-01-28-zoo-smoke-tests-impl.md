# Zoo Smoke Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create smoke tests to verify all "zoo" services (Redis, Qdrant, bge-m3, bm42, user-base, litellm) are running and functional.

**Architecture:** Two-layer approach: bash script for fast local checks (~30 sec), pytest for CI with SDK-level validation. Bash checks health endpoints only; pytest adds embed/completion tests and cache roundtrips.

**Tech Stack:** Bash (curl, redis-cli), Python (pytest, httpx, redis.asyncio), existing fixtures from `tests/smoke/conftest.py`

---

## Task 1: Bash Smoke Script

**Files:**
- Create: `scripts/smoke-zoo.sh`

**Step 1: Create the bash script with health checks**

```bash
#!/usr/bin/env bash
# scripts/smoke-zoo.sh - Quick smoke test for all zoo services
# Usage: ./scripts/smoke-zoo.sh [--quiet]
# Exit: 0 if all pass, 1 if any fail

set -euo pipefail

QUIET="${1:-}"
FAILED=0
PASSED=0

# Colors (disabled in quiet mode)
if [[ "$QUIET" != "--quiet" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' NC=''
fi

check() {
    local name="$1"
    local cmd="$2"

    if eval "$cmd" > /dev/null 2>&1; then
        [[ "$QUIET" != "--quiet" ]] && echo -e "${GREEN}[OK]${NC} $name"
        ((PASSED++))
        return 0
    else
        [[ "$QUIET" != "--quiet" ]] && echo -e "${RED}[FAIL]${NC} $name"
        ((FAILED++))
        return 1
    fi
}

[[ "$QUIET" != "--quiet" ]] && echo -e "${YELLOW}Zoo Smoke Tests${NC}"
[[ "$QUIET" != "--quiet" ]] && echo "=================="

# 1. Redis
check "Redis PING" "redis-cli -h localhost -p 6379 PING | grep -q PONG"

# 2. Redis Query Engine (FT.*)
check "Redis FT._LIST" "redis-cli -h localhost -p 6379 FT._LIST"

# 3. Qdrant
check "Qdrant readyz" "curl -sf http://localhost:6333/readyz"

# 4. bge-m3
check "bge-m3 health" "curl -sf http://localhost:8000/health | grep -q ok"

# 5. bm42
check "bm42 health" "curl -sf http://localhost:8002/health | grep -q ok"

# 6. user-base
check "user-base health" "curl -sf http://localhost:8003/health | grep -q ok"

# 7. litellm
check "litellm health" "curl -sf http://localhost:4000/health/liveliness"

# Summary
[[ "$QUIET" != "--quiet" ]] && echo "=================="
[[ "$QUIET" != "--quiet" ]] && echo -e "Passed: ${GREEN}$PASSED${NC}, Failed: ${RED}$FAILED${NC}"

if [[ $FAILED -gt 0 ]]; then
    exit 1
fi
exit 0
```

**Step 2: Make script executable and test**

Run:
```bash
chmod +x scripts/smoke-zoo.sh
./scripts/smoke-zoo.sh
```

Expected: Table of OK/FAIL for each service (or failures if services not running)

**Step 3: Commit**

```bash
git add scripts/smoke-zoo.sh
git commit -m "feat(smoke): add bash zoo smoke script

Quick 30-sec smoke test for all services:
- Redis PING + FT._LIST
- Qdrant readyz
- bge-m3, bm42, user-base health
- litellm liveliness"
```

---

## Task 2: Pytest Zoo Health Tests

**Files:**
- Create: `tests/smoke/test_zoo_smoke.py`

**Step 2.1: Create test file with user-base health test**

```python
# tests/smoke/test_zoo_smoke.py
"""Zoo smoke tests - verify all services are alive and functional."""

import os

import httpx
import pytest


class TestZooHealth:
    """Health checks for services without existing coverage."""

    @pytest.fixture
    def user_base_url(self):
        return os.getenv("USER_BASE_URL", "http://localhost:8003")

    @pytest.fixture
    def litellm_url(self):
        return os.getenv("LLM_BASE_URL", "http://localhost:4000")

    @pytest.mark.asyncio
    async def test_user_base_health(self, user_base_url):
        """user-base /health returns status=ok."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{user_base_url}/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "ok"

    @pytest.mark.asyncio
    async def test_user_base_embed_returns_768_dim(self, user_base_url):
        """user-base /embed returns 768-dimensional vector."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{user_base_url}/embed",
                json={"text": "тестовый запрос"}
            )
            assert response.status_code == 200
            data = response.json()
            embedding = data.get("embedding", [])
            assert len(embedding) == 768, f"Expected 768 dims, got {len(embedding)}"

    @pytest.mark.asyncio
    async def test_litellm_health(self, litellm_url):
        """litellm /health/liveliness returns 200."""
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
```

**Step 2.2: Run tests to verify**

Run:
```bash
pytest tests/smoke/test_zoo_smoke.py -v
```

Expected: 4 tests pass (or skip if services not available)

**Step 2.3: Commit**

```bash
git add tests/smoke/test_zoo_smoke.py
git commit -m "test(smoke): add zoo health tests

- user-base health + 768-dim embed verification
- litellm health + completion test"
```

---

## Task 3: Pytest Zoo Cache Tests

**Files:**
- Modify: `tests/smoke/test_zoo_smoke.py`

**Step 3.1: Add sparse cache roundtrip test**

Append to `tests/smoke/test_zoo_smoke.py`:

```python
class TestZooCache:
    """Cache roundtrip tests."""

    @pytest.fixture
    async def cache_service(self):
        """CacheService for testing."""
        from telegram_bot.services.cache import CacheService

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_sparse_cache_roundtrip(self, cache_service):
        """Sparse cache store -> get works."""
        import time

        text = f"zoo_smoke_sparse_test_{int(time.time())}"
        sparse_vector = {"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]}

        await cache_service.store_sparse_embedding(text, sparse_vector, model_name="bm42")
        cached = await cache_service.get_cached_sparse_embedding(text, model_name="bm42")

        assert cached is not None
        assert cached["indices"] == [1, 5, 10]
        assert cached["values"] == [0.5, 0.3, 0.2]
```

**Step 3.2: Run test to verify**

Run:
```bash
pytest tests/smoke/test_zoo_smoke.py::TestZooCache::test_sparse_cache_roundtrip -v
```

Expected: PASS

**Step 3.3: Commit**

```bash
git add tests/smoke/test_zoo_smoke.py
git commit -m "test(smoke): add sparse cache roundtrip test"
```

---

## Task 4: Pytest End-to-End Cache Validation

**Files:**
- Modify: `tests/smoke/test_zoo_smoke.py`

**Step 4.1: Add "second request cheaper" test**

Append to `tests/smoke/test_zoo_smoke.py`:

```python
class TestZooEndToEnd:
    """End-to-end validation."""

    @pytest.fixture
    async def cache_service(self):
        """CacheService for testing."""
        from telegram_bot.services.cache import CacheService

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        service = CacheService(redis_url=redis_url)
        await service.initialize()
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_second_request_has_cache_hits(self, cache_service):
        """Second identical request should have cache hits."""
        import time

        # Reset metrics
        for cache_type in cache_service.metrics:
            cache_service.metrics[cache_type] = {"hits": 0, "misses": 0}

        query = f"zoo_e2e_test_{int(time.time())}"
        analysis = {"filters": {"test": True}, "semantic_query": query}

        # First request - should be MISS
        await cache_service.get_cached_analysis(query)
        first_misses = cache_service.metrics["analyzer"]["misses"]
        assert first_misses >= 1, "First request should miss"

        # Store result
        await cache_service.store_analysis(query, analysis)

        # Second request - should be HIT
        cached = await cache_service.get_cached_analysis(query)
        second_hits = cache_service.metrics["analyzer"]["hits"]

        assert cached is not None, "Second request should return cached result"
        assert second_hits >= 1, "Second request should be a cache hit"
        assert cached["semantic_query"] == query
```

**Step 4.2: Run test to verify**

Run:
```bash
pytest tests/smoke/test_zoo_smoke.py::TestZooEndToEnd::test_second_request_has_cache_hits -v
```

Expected: PASS

**Step 4.3: Commit**

```bash
git add tests/smoke/test_zoo_smoke.py
git commit -m "test(smoke): add second-request-cheaper e2e test

Validates cache wiring: first request misses, second hits"
```

---

## Task 5: Makefile Targets

**Files:**
- Modify: `Makefile`

**Step 5.1: Add smoke targets to Makefile**

Add after line ~153 (after `test-all-smoke-load`):

```makefile
smoke-fast: ## Quick zoo smoke (~30 sec, bash only)
	@echo "$(BLUE)Running quick zoo smoke...$(NC)"
	./scripts/smoke-zoo.sh
	@echo "$(GREEN)✓ Zoo smoke complete$(NC)"

smoke-zoo: ## Run zoo smoke tests (pytest)
	@echo "$(BLUE)Running zoo smoke tests...$(NC)"
	pytest tests/smoke/test_zoo_smoke.py -v
	@echo "$(GREEN)✓ Zoo smoke tests complete$(NC)"
```

**Step 5.2: Test Makefile targets**

Run:
```bash
make smoke-fast
make smoke-zoo
```

Expected: Both commands run successfully

**Step 5.3: Commit**

```bash
git add Makefile
git commit -m "build: add smoke-fast and smoke-zoo make targets

- smoke-fast: bash script (~30 sec)
- smoke-zoo: pytest zoo tests"
```

---

## Task 6: Final Verification

**Step 6.1: Run full smoke suite**

Run:
```bash
make smoke-fast && make smoke-zoo
```

Expected: All checks pass

**Step 6.2: Verify quiet mode**

Run:
```bash
./scripts/smoke-zoo.sh --quiet && echo "All services OK" || echo "Some services FAIL"
```

Expected: Output shows only "All services OK" or "Some services FAIL"

**Step 6.3: Final commit (if any cleanup needed)**

```bash
git status
# If clean, no commit needed
```

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1 | `scripts/smoke-zoo.sh` | 7 health checks |
| 2 | `tests/smoke/test_zoo_smoke.py` | 4 health tests |
| 3 | `tests/smoke/test_zoo_smoke.py` | 1 sparse cache test |
| 4 | `tests/smoke/test_zoo_smoke.py` | 1 e2e cache test |
| 5 | `Makefile` | 2 new targets |
| 6 | - | Final verification |

**Total: 6 tasks, ~15 minutes**
