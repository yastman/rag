# Validation Retry/Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `scripts/validate_traces.py` resilient to transient failures in Langfuse, Redis, and Qdrant — no more false negatives from network blips.

**Architecture:** Add tenacity retry to Langfuse setup auth probe (`auth_check()`), verify Redis flush completeness before cold phase (SKIP if unavailable), replace hardcoded collection list with Qdrant API discovery, and surface `EXTERNAL_DEPENDENCY_UNAVAILABLE` status in Go/No-Go report.

**Tech Stack:** tenacity (already in deps), qdrant-client AsyncQdrantClient, redis.asyncio

**Issue:** #166

---

### Task 1: Langfuse auth probe with retry + timeout

**Files:**
- Modify: `scripts/validate_traces.py:129-150` (`check_langfuse_config`)
- Test: `tests/unit/test_validate_aggregates.py` (class `TestLangfusePreflight`)

**Step 1: Write failing tests for retry behavior**

Add to `tests/unit/test_validate_aggregates.py`, class `TestLangfusePreflight`:

```python
def test_retries_on_transient_failure_then_succeeds(self, monkeypatch: pytest.MonkeyPatch):
    """Auth probe retries up to 3 times on transient errors."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3001")

    mock_lf = MagicMock()
    # Fail twice, succeed on third call
    mock_lf.auth_check.side_effect = [
        ConnectionError("timeout"),
        ConnectionError("timeout"),
        True,  # success
    ]

    with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
        check_langfuse_config()  # should not raise

    assert mock_lf.auth_check.call_count == 3


def test_gives_up_after_3_retries(self, monkeypatch: pytest.MonkeyPatch):
    """Auth probe exits after exhausting 3 retry attempts."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3001")

    mock_lf = MagicMock()
    mock_lf.auth_check.side_effect = ConnectionError("timeout")

    with (
        patch("scripts.validate_traces.Langfuse", return_value=mock_lf),
        pytest.raises(SystemExit),
    ):
        check_langfuse_config()

    assert mock_lf.auth_check.call_count == 3
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestLangfusePreflight -v`
Expected: 2 new tests FAIL (no retry logic yet, first transient error → sys.exit)

**Step 3: Implement retry with tenacity**

In `scripts/validate_traces.py`, add import at top:

```python
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)
```

Replace `check_langfuse_config()` (lines 129-150) with:

```python
def check_langfuse_config() -> None:
    """Preflight: verify Langfuse credentials are set and API is reachable.

    Retries auth probe 3 times with exponential backoff (max 10s total).
    """
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "")
    if not public:
        logger.error("LANGFUSE_PUBLIC_KEY not set — cannot authenticate Langfuse API")
        sys.exit(1)
    if not secret:
        logger.error("LANGFUSE_SECRET_KEY not set — cannot record traces")
        sys.exit(1)
    if not host:
        logger.error("LANGFUSE_HOST not set — cannot connect to Langfuse")
        sys.exit(1)
    try:
        _langfuse_auth_probe()
    except Exception as e:
        logger.error("Langfuse auth check failed after retries: %s", e)
        sys.exit(1)
    logger.info("Langfuse config OK: host=%s", host)


@retry(
    stop=(stop_after_attempt(3) | stop_after_delay(10)),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _langfuse_auth_probe() -> None:
    """Auth probe with retry. Separated for testability."""
    lf = Langfuse()
    if not lf.auth_check():
        raise RuntimeError("Langfuse auth_check returned False")
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestLangfusePreflight -v`
Expected: all 5 tests PASS (3 existing + 2 new)

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): add retry/timeout to Langfuse auth probe #166"
```

---

### Task 2: Redis flush verification + SKIPPED status

**Files:**
- Modify: `scripts/validate_traces.py:374-402` (`_flush_redis_caches`)
- Modify: `scripts/validate_traces.py:405-486` (`run_collection_validation`)
- Test: `tests/unit/test_validate_aggregates.py` (new class `TestRedisFlush`)

**Step 1: Write failing tests for Redis flush verification**

Add new class to `tests/unit/test_validate_aggregates.py`:

```python
class TestRedisFlush:
    """Redis cache flush must verify completeness or return SKIPPED."""

    async def test_returns_ok_when_all_keys_deleted(self):
        """Flush succeeds: all patterns cleared, verify returns OK."""
        mock_redis = AsyncMock()
        # scan_iter returns keys on first call (flush), empty on verify
        call_count = 0
        async def fake_scan_iter(match=None, count=100):
            nonlocal call_count
            call_count += 1
            # Odd calls = flush phase (return keys), even = verify (return empty)
            if call_count % 2 == 1:
                for k in [f"key:{call_count}"]:
                    yield k
            # Even calls (verify) yield nothing

        mock_redis.scan_iter = fake_scan_iter
        mock_redis.delete = AsyncMock()

        mock_cache = MagicMock()
        mock_cache.redis = mock_redis
        mock_cache.semantic_cache = None

        result = await _flush_redis_caches(mock_cache)
        assert result == "OK"

    async def test_returns_skipped_when_redis_unavailable(self):
        """No redis connection → SKIPPED, not silent warm run."""
        mock_cache = MagicMock()
        mock_cache.redis = None

        result = await _flush_redis_caches(mock_cache)
        assert result == "SKIPPED"

    async def test_returns_skipped_when_keys_remain_after_flush(self):
        """Flush runs but keys remain → SKIPPED."""
        mock_redis = AsyncMock()
        # scan_iter always returns keys (can't delete)
        async def fake_scan_iter(match=None, count=100):
            for k in [b"remaining:1"]:
                yield k

        mock_redis.scan_iter = fake_scan_iter
        mock_redis.delete = AsyncMock()

        mock_cache = MagicMock()
        mock_cache.redis = mock_redis
        mock_cache.semantic_cache = None

        result = await _flush_redis_caches(mock_cache)
        assert result == "SKIPPED"
```

NOTE: import `AsyncMock` from `unittest.mock` and `_flush_redis_caches` from `scripts.validate_traces`.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestRedisFlush -v`
Expected: FAIL — current function returns None, not "OK"/"SKIPPED"

**Step 3: Implement Redis flush verification**

Replace `_flush_redis_caches` (lines 374-402) with:

```python
async def _flush_redis_caches(cache: Any) -> str:
    """Clear cache keys for cold run without dropping RediSearch index.

    Returns:
        "OK" if flush verified (0 keys remaining).
        "SKIPPED" if Redis unavailable or flush incomplete.
    """
    if not hasattr(cache, "redis") or not cache.redis:
        logger.warning("  Redis not available — cold phase will be SKIPPED")
        return "SKIPPED"

    deleted = 0
    patterns = [
        "embeddings:v3:*",
        "sparse:v3:*",
        "analysis:v3:*",
        "search:v3:*",
        "rerank:v3:*",
        "conversation:*",
    ]
    for pattern in patterns:
        keys = [k async for k in cache.redis.scan_iter(match=pattern)]
        if keys:
            deleted += len(keys)
            await cache.redis.delete(*keys)

    # Semantic cache has its own key namespace and index lifecycle.
    if hasattr(cache, "semantic_cache") and cache.semantic_cache:
        try:
            await cache.semantic_cache.aclear()
        except Exception as e:
            logger.warning("  Semantic cache clear failed: %s", e)

    # Verify: re-scan to confirm keys are actually gone
    remaining = 0
    for pattern in patterns:
        remaining += len([k async for k in cache.redis.scan_iter(match=pattern, count=100)])

    if remaining > 0:
        logger.error(
            "  Redis flush incomplete: %d keys remain after deletion — cold phase SKIPPED",
            remaining,
        )
        return "SKIPPED"

    logger.info("  Redis cache flush verified — deleted %d keys, 0 remaining", deleted)
    return "OK"
```

**Step 4: Update `run_collection_validation` to handle SKIPPED cold phase**

In `run_collection_validation`, after the flush call (~line 440), change:

```python
    # Phase 2: Cold run — flush caches for true cold measurement
    logger.info("Phase 2: Flushing Redis caches for true cold run...")
    flush_status = await _flush_redis_caches(services["cache"])
    cold_queries = get_queries_for_collection(collection)
    if flush_status == "SKIPPED":
        logger.warning("Phase 2: Cold run SKIPPED — Redis flush not verified")
        # Mark results as skipped so Go/No-Go knows
        for q in cold_queries:
            results.append(
                TraceResult(
                    trace_id="skipped",
                    query=q.text,
                    collection=collection,
                    phase="cold",
                    source=q.source,
                    difficulty=q.difficulty,
                    latency_wall_ms=0,
                    state={"cold_skipped": True, "skip_reason": "redis_flush_failed"},
                )
            )
    else:
        logger.info("Phase 2: Cold run (%d queries)", len(cold_queries))
        for q in cold_queries:
            result = await run_single_query(q, services, run_meta, phase="cold")
            results.append(result)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestRedisFlush -v`
Expected: all 3 PASS

**Step 6: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): verify Redis flush + SKIPPED cold phase on failure #166"
```

---

### Task 3: Replace hardcoded collections with Qdrant API discovery

**Files:**
- Modify: `scripts/validate_traces.py:50,199-212` (`COLLECTIONS_TO_CHECK`, `discover_collections`)
- Test: `tests/unit/test_validate_aggregates.py` (new class `TestCollectionDiscovery`)

**Step 1: Write failing tests for Qdrant API-based discovery**

Add new class to `tests/unit/test_validate_aggregates.py`:

```python
class TestCollectionDiscovery:
    """Collection discovery should use Qdrant API, not hardcoded list."""

    async def test_discovers_exact_match(self):
        """Finds collection by exact name from Qdrant API."""
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[
                MagicMock(name="gdrive_documents_bge"),
                MagicMock(name="some_other_collection"),
            ]
        )
        mock_client.close = AsyncMock()

        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        assert "gdrive_documents_bge" in result

    async def test_discovers_collection_with_quantization_suffix(self):
        """Finds base collection even when stored with _scalar or _binary suffix."""
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[
                MagicMock(name="gdrive_documents_bge_scalar"),
                MagicMock(name="contextual_bulgaria_voyage_binary"),
            ]
        )
        mock_client.close = AsyncMock()

        with (
            patch("qdrant_client.AsyncQdrantClient", return_value=mock_client),
            patch("scripts.validate_traces.check_voyage_available", return_value=True),
        ):
            result = await discover_collections("http://localhost:6333")

        assert "gdrive_documents_bge_scalar" in result
        assert "contextual_bulgaria_voyage_binary" in result

    async def test_prefers_exact_match_over_suffixed(self):
        """If both base and suffixed exist, prefer exact match."""
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[
                MagicMock(name="gdrive_documents_bge"),
                MagicMock(name="gdrive_documents_bge_scalar"),
            ]
        )
        mock_client.close = AsyncMock()

        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        # Exact match preferred — only one entry per base name
        assert result.count("gdrive_documents_bge") == 1
        assert "gdrive_documents_bge_scalar" not in result

    async def test_returns_empty_when_qdrant_unavailable(self):
        """Qdrant connection failure returns empty list, not crash."""
        mock_client = AsyncMock()
        mock_client.get_collections.side_effect = ConnectionError("refused")
        mock_client.close = AsyncMock()

        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        assert result == []

    async def test_skips_voyage_collection_without_api_key(self):
        """Voyage collections discovered but skipped if VOYAGE_API_KEY missing."""
        mock_client = AsyncMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[
                MagicMock(name="gdrive_documents_bge"),
                MagicMock(name="contextual_bulgaria_voyage"),
            ]
        )
        mock_client.close = AsyncMock()

        with (
            patch("qdrant_client.AsyncQdrantClient", return_value=mock_client),
            patch("scripts.validate_traces.check_voyage_available", return_value=False),
        ):
            result = await discover_collections("http://localhost:6333")

        assert "gdrive_documents_bge" in result
        assert "contextual_bulgaria_voyage" not in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestCollectionDiscovery -v`
Expected: FAIL — current code uses `collection_exists` per name, not `get_collections`

**Step 3: Implement Qdrant API-based discovery**

Replace constant and function in `scripts/validate_traces.py`:

```python
# Base collection names to look for (without quantization suffix)
COLLECTION_BASE_NAMES = ["gdrive_documents_bge", "contextual_bulgaria_voyage"]
QUANTIZATION_SUFFIXES = ["", "_scalar", "_binary"]


async def discover_collections(qdrant_url: str) -> list[str]:
    """Discover available collections for validation via Qdrant API.

    Queries Qdrant for all collections, matches against known base names
    (with optional _scalar/_binary suffixes). Prefers exact match over suffixed.
    """
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(url=qdrant_url)
    try:
        response = await client.get_collections()
        all_names = {c.name for c in response.collections}
    except Exception as e:
        logger.error("Qdrant collection discovery failed: %s", e)
        return []
    finally:
        await client.close()

    available: list[str] = []
    for base_name in COLLECTION_BASE_NAMES:
        # Prefer exact match
        matched = None
        for suffix in QUANTIZATION_SUFFIXES:
            candidate = f"{base_name}{suffix}"
            if candidate in all_names:
                if suffix == "":
                    matched = candidate
                    break  # exact match wins
                elif matched is None:
                    matched = candidate  # keep first suffix match

        if matched is None:
            logger.warning("Collection %s (any suffix) not found in Qdrant", base_name)
            continue

        # Voyage collections need API key
        if "voyage" in base_name and not check_voyage_available():
            logger.warning(
                "Skipping %s: collection exists but VOYAGE_API_KEY not set",
                matched,
            )
            continue

        available.append(matched)

    logger.info("Discovered collections: %s (from %d total in Qdrant)", available, len(all_names))
    return available
```

Also remove the old `check_collection_available` function and update `run_validation` to remove the single-collection `check_collection_available` call — replace with `collection_exists`:

```python
    if args.collection:
        from qdrant_client import AsyncQdrantClient
        client = AsyncQdrantClient(url=qdrant_url)
        try:
            exists = await client.collection_exists(args.collection)
        finally:
            await client.close()
        if exists:
            collections = [args.collection]
        else:
            logger.error("Collection %s not found, aborting", args.collection)
            sys.exit(1)
    else:
        collections = await discover_collections(qdrant_url)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestCollectionDiscovery tests/unit/test_validate_aggregates.py::TestCollectionResolution -v`
Expected: all PASS

**Step 5: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): replace hardcoded collections with Qdrant API discovery #166"
```

---

### Task 4: Add EXTERNAL_DEPENDENCY_UNAVAILABLE status to Go/No-Go

**Files:**
- Modify: `scripts/validate_traces.py:588-726` (`evaluate_go_no_go`)
- Modify: `scripts/validate_traces.py:921-1077` (`generate_report`)
- Test: `tests/unit/test_validate_aggregates.py` (new tests in `TestEvaluateGoNoGo`)

**Step 1: Write failing tests for dependency unavailable status**

Add to `tests/unit/test_validate_aggregates.py`, class `TestEvaluateGoNoGo`:

```python
def test_cold_skipped_marks_criteria_as_dependency_unavailable(self):
    """When cold phase was SKIPPED (Redis flush failed), latency criteria → DEP_UNAVAILABLE."""
    aggregates = {
        "cold": {},
        "cache_hit": {"latency_p50": 500},
    }
    # All cold results have cold_skipped=True
    results = [
        _make_result(phase="cold", latency=0),
    ]
    results[0].state["cold_skipped"] = True
    results[0].state["skip_reason"] = "redis_flush_failed"

    criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

    assert criteria["cold_p50_lt_5s"].get("dep_unavailable") is True
    assert criteria["cold_p50_lt_5s"]["passed"] is True  # not a failure
    assert "SKIPPED" in criteria["cold_p50_lt_5s"]["actual"]


def test_mixed_cold_results_not_marked_unavailable(self):
    """If some cold results ran normally, criteria are NOT marked dep_unavailable."""
    aggregates = {
        "cold": {"latency_p50": 3000, "latency_p90": 5000, "latency_p95": 6000,
                 "node_p50": {"generate": 1500}},
        "cache_hit": {"latency_p50": 500},
    }
    results = [_make_result(phase="cold", latency=3000)]

    criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

    assert criteria["cold_p50_lt_5s"].get("dep_unavailable") is not True
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo::test_cold_skipped_marks_criteria_as_dependency_unavailable -v`
Expected: FAIL — no `dep_unavailable` key

**Step 3: Implement dependency unavailable detection**

At the top of `evaluate_go_no_go`, detect skipped cold phase:

```python
    cold_skipped = all(
        r.state.get("cold_skipped") for r in cold_results
    ) if cold_results else False
```

Then override only cold-dependent criteria (cold_p50, cold_p90, cold_over_10s) **after** they are initially computed:

```python
    if cold_skipped:
        skip_reason = cold_results[0].state.get("skip_reason", "unknown")
        for key in ["cold_p50_lt_5s", "cold_p90_lt_8s", "cold_over_10s_lt_15pct"]:
            original = criteria[key]
            criteria[key] = {
                "target": original["target"],
                "actual": f"SKIPPED ({skip_reason})",
                "passed": True,
                "dep_unavailable": True,
            }
    # ... non-cold criteria remain unchanged
```

**Step 4: Update report rendering**

In `generate_report`, update the Go/No-Go table rendering to show `[!] DEP_UNAVAIL` status:

```python
            if c.get("dep_unavailable"):
                status = "[!] DEP_UNAVAIL"
            elif c.get("skipped"):
                status = "[-] SKIP"
            elif c["passed"]:
                status = "[x] PASS"
            else:
                status = "[ ] **FAIL**"
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validate_aggregates.py::TestEvaluateGoNoGo -v`
Expected: all PASS

**Step 6: Commit**

```bash
git add scripts/validate_traces.py tests/unit/test_validate_aggregates.py
git commit -m "fix(validation): add EXTERNAL_DEPENDENCY_UNAVAILABLE status to Go/No-Go #166"
```

---

### Task 5: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/test_validate_aggregates.py tests/unit/test_validate_queries.py -v`
Expected: all PASS

**Step 2: Run linter + type check**

Run: `make check`
Expected: no errors

**Step 3: Commit any fixups**

If make check found issues, fix and commit:
```bash
git add -u
git commit -m "fix(validation): lint/type fixes for #166"
```
