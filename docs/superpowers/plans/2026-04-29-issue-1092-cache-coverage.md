# Cache Layers Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close issue #1092 by adding deterministic unit coverage for cache policy decisions, Redis cache TTL/error behavior, and search cache key collision guards.

**Architecture:** This is a test-only change. Keep canonical coverage in the existing unit owners: `tests/unit/services/test_cache_policy.py` for pure cache policy logic and `tests/unit/integrations/test_cache_layers.py` for `CacheLayerManager` Redis/RedisVL behavior. Do not add live Redis/Qdrant dependencies; use mocks/fakes only.

**Tech Stack:** pytest async tests, `AsyncMock`/`MagicMock`, existing `CacheLayerManager`, existing `build_cacheability_decision`, redis-py/RedisVL SDK wrappers as mocked dependencies.

---

## Smart Routing

- Routing: Full plan, because issue #1092 is `lane:plan-needed` and spans cache policy plus Redis/RedisVL cache layer behavior.
- Execution: parallel workers with disjoint write scopes, then final integration worker.
- SDK coverage: `redisvl` and `redis-py (asyncio)` from `docs/engineering/sdk-registry.md`; no new SDK or broad SDK docs lookup required because tests target current wrappers and mocks.
- Non-goals: no production cache behavior changes unless a focused test reveals an existing bug; no live Redis/Qdrant tests; no broad cache refactor.

## File Structure

- Modify: `tests/unit/services/test_cache_policy.py`
  - Owner for pure `build_cacheability_decision()` coverage.
  - Worker: `W-1092-policy`.
- Modify: `tests/unit/integrations/test_cache_layers.py`
  - Owner for `CacheLayerManager` TTL, Redis failure, key generation, and clear/eviction-like behavior.
  - Worker: `W-1092-layers`.
- Do not modify: `telegram_bot/services/cache_policy.py` or `telegram_bot/integrations/cache.py` unless an existing bug is proven by a failing test and the worker records the reason in DONE JSON.

## Worker Split

| Worker | Reserved Files | Scope |
|--------|----------------|-------|
| `W-1092-policy` | `tests/unit/services/test_cache_policy.py` | Cache eligibility policy and RRF confidence gate coverage |
| `W-1092-layers` | `tests/unit/integrations/test_cache_layers.py` | Redis/RedisVL layer TTLs, key generation, connection failure, exact cache behavior |
| `W-1092-final` | integration branch only | Merge worker branches, run focused tests, `make check`, create PR |

## Task 1: Cache Policy Coverage

**Files:**
- Modify: `tests/unit/services/test_cache_policy.py`

- [ ] **Step 1: Add a local helper for baseline successful policy input**

Add a helper near the top of `tests/unit/services/test_cache_policy.py`:

```python
def _cacheable_result() -> dict:
    return {
        "response": "Подтвержденный ответ.",
        "fallback_used": False,
        "safe_fallback_used": False,
        "llm_provider_model": "gpt-4.1",
        "llm_timeout": False,
        "grounded": True,
        "legal_answer_safe": True,
        "semantic_cache_safe_reuse": True,
    }
```

- [ ] **Step 2: Add threshold boundary tests for the RRF confidence guard**

Add tests proving `grade_confidence >= confidence_threshold` is required:

```python
def test_build_cacheability_decision_allows_rrf_threshold_boundary() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="GENERAL",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.005,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is True
    assert decision.store_reason == "store_allowed"


def test_build_cacheability_decision_blocks_below_rrf_threshold() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="GENERAL",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.0049,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False
```

- [ ] **Step 3: Add policy guard tests for cache hit, contextual query, and missing docs**

Add tests proving non-cacheable cases stay blocked:

```python
def test_build_cacheability_decision_blocks_existing_cache_hit() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=True,
        contextual=False,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False


def test_build_cacheability_decision_blocks_contextual_query() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[{"text": "doc"}],
        cache_hit=False,
        contextual=True,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False


def test_build_cacheability_decision_blocks_empty_documents() -> None:
    decision = build_cacheability_decision(
        result=_cacheable_result(),
        query_type="FAQ",
        grounding_mode="strict",
        documents=[],
        cache_hit=False,
        contextual=False,
        grade_confidence=0.9,
        confidence_threshold=0.005,
        schema_version="v8",
    )

    assert decision.cache_eligible is False
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/unit/services/test_cache_policy.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit worker slice**

```bash
git add tests/unit/services/test_cache_policy.py
git commit -m "test(cache): cover semantic cache policy guards"
```

## Task 2: Cache Layer TTL, Redis, and Key Coverage

**Files:**
- Modify: `tests/unit/integrations/test_cache_layers.py`

- [ ] **Step 1: Add semantic TTL selection coverage**

Extend `TestSemanticCache` or `TestScopeRoleIsolation` with a test proving `store_semantic()` uses per-query-type TTL:

```python
async def test_semantic_store_uses_query_type_ttl(self):
    mgr = CacheLayerManager(redis_url="redis://localhost:6379")
    mgr.semantic_cache = AsyncMock()
    mgr.semantic_cache.astore = AsyncMock()
    mgr.cache_ttl = {"FAQ": 86400, "GENERAL": 3600}

    await mgr.store_semantic(
        query="faq",
        response="answer",
        vector=[0.1] * 1024,
        query_type="FAQ",
    )

    assert mgr.semantic_cache.astore.await_args.kwargs["ttl"] == 86400
```

- [ ] **Step 2: Add exact cache TTL override coverage**

Add a test proving `store_exact()` respects caller TTL override rather than tier default:

```python
async def test_exact_store_uses_explicit_ttl_override(self):
    mgr = CacheLayerManager(redis_url="redis://localhost:6379")
    mgr.redis = AsyncMock()
    mgr.redis.setex = AsyncMock()

    await mgr.store_exact("search", "key1", [{"id": "1"}], ttl=45)

    mgr.redis.setex.assert_awaited_once()
    assert mgr.redis.setex.await_args.args[1] == 45
```

- [ ] **Step 3: Add search key collision guard tests**

Add tests around `store_search_results()`/`get_search_results()` proving full embedding content and normalized filter JSON affect the exact cache key:

```python
async def test_search_cache_key_uses_full_embedding_vector(self):
    mgr = CacheLayerManager(redis_url="redis://localhost:6379")
    seen_keys: list[str] = []

    async def mock_store_exact(tier, key, value, ttl=None):
        seen_keys.append(key)

    mgr.store_exact = AsyncMock(side_effect=mock_store_exact)

    prefix_a = [0.1] * 10 + [0.2]
    prefix_b = [0.1] * 10 + [0.3]

    await mgr.store_search_results(prefix_a, {"city": "Sofia"}, [{"id": "a"}])
    await mgr.store_search_results(prefix_b, {"city": "Sofia"}, [{"id": "b"}])

    assert len(set(seen_keys)) == 2


async def test_search_cache_key_is_stable_for_filter_order(self):
    mgr = CacheLayerManager(redis_url="redis://localhost:6379")
    seen_keys: list[str] = []

    async def mock_store_exact(tier, key, value, ttl=None):
        seen_keys.append(key)

    mgr.store_exact = AsyncMock(side_effect=mock_store_exact)

    vector = [0.1, 0.2, 0.3]
    await mgr.store_search_results(vector, {"city": "Sofia", "rooms": 2}, [{"id": "a"}])
    await mgr.store_search_results(vector, {"rooms": 2, "city": "Sofia"}, [{"id": "b"}])

    assert len(set(seen_keys)) == 1
```

- [ ] **Step 4: Add Redis ping failure coverage**

Add a test proving `initialize()` leaves Redis disabled when the connection object is created but `ping()` fails:

```python
async def test_initialize_disables_redis_when_ping_fails(self):
    mgr = CacheLayerManager(redis_url="redis://localhost:6379")
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=ConnectionError("pool exhausted"))

    with patch("telegram_bot.integrations.cache.redis.from_url", return_value=mock_redis):
        await mgr.initialize()

    assert mgr.redis is None
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/unit/integrations/test_cache_layers.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit worker slice**

```bash
git add tests/unit/integrations/test_cache_layers.py
git commit -m "test(cache): cover cache layer ttl and key guards"
```

## Task 3: Final Integration

**Files:**
- Merge worker branches into `fix/1092-cache-coverage`.
- Keep plan file committed.

- [ ] **Step 1: Merge worker branches**

```bash
git merge --no-ff origin/fix/1092-cache-policy-tests
git merge --no-ff origin/fix/1092-cache-layer-tests
```

- [ ] **Step 2: Run focused verification**

```bash
uv run pytest tests/unit/services/test_cache_policy.py tests/unit/integrations/test_cache_layers.py -q
make check
```

- [ ] **Step 3: Create PR**

```bash
git push -u origin fix/1092-cache-coverage
gh pr create --base dev --head fix/1092-cache-coverage --title "test(cache): cover cache policy and layer guards" --body "Closes #1092"
```

- [ ] **Step 4: Record evidence**

DONE JSON must include focused pytest output, `make check`, branch, PR URL, and changed files.

## Definition of Done

- Plan file exists before implementation.
- Two implementation workers completed disjoint slices in separate worktrees.
- Focused cache tests pass.
- `make check` passes.
- PR targets `dev` and closes #1092.
- Orchestrator reviews diff and waits for fresh GitHub CI before merge.
