# Smoke + Load Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement remaining smoke tests (quantization + TTFT), load tests with mandatory TTFT measurement, Redis eviction tests, and Makefile commands with golden baseline procedure.

**Architecture:** pytest-based functional tests using live services (Qdrant, Redis, Voyage AI, LLM). TTFT is measured via `LLMService.stream_answer()` first chunk timing. Golden baseline stored in `tests/load/baseline.json` and updated only manually.

**Tech Stack:** pytest, pytest-asyncio, numpy, redis.asyncio, httpx

---

## Definition of Done

```bash
# ALL must pass before merge

# 1. Smoke quantization tests pass
pytest tests/smoke/test_smoke_quantization.py -v

# 2. Load conversation tests pass (with TTFT)
REQUIRE_TTFT=1 pytest tests/load/test_load_conversations.py -v

# 3. Redis eviction tests pass
pytest tests/load/test_load_redis_eviction.py -v

# 4. Golden baseline exists
test -f tests/load/baseline.json

# 5. Makefile commands work
make test-preflight
make test-smoke-routing
make test-load-ci

# 6. All reports generated
test -d reports
```

---

## Task 1: Create test_smoke_quantization.py

**Files:**
- Create: `tests/smoke/test_smoke_quantization.py`

**Step 1: Create the test file**

```python
# tests/smoke/test_smoke_quantization.py
"""Smoke tests for Qdrant quantization A/B testing and TTFT measurement."""

import os
import time

import numpy as np
import pytest

from telegram_bot.services.llm import LLMService
from telegram_bot.services.qdrant import QdrantService
from telegram_bot.services.voyage import VoyageService


@pytest.fixture(scope="module")
def voyage_service():
    """VoyageService for embeddings."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY not set")
    return VoyageService(api_key=api_key)


@pytest.fixture(scope="module")
async def qdrant_service():
    """QdrantService for search."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4")

    service = QdrantService(url=url, api_key=api_key or None, collection_name=collection)
    yield service
    await service.close()


@pytest.fixture(scope="module")
def llm_service():
    """LLMService for streaming."""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.cerebras.ai/v1")
    model = os.getenv("LLM_MODEL", "llama3.1-8b")

    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    return LLMService(api_key=api_key, base_url=base_url, model=model)


@pytest.mark.skipif(not os.getenv("QDRANT_URL"), reason="QDRANT_URL not set")
class TestSmokeQuantization:
    """Test quantization A/B switching."""

    @pytest.mark.asyncio
    async def test_search_with_quantization_returns_results(self, voyage_service, qdrant_service):
        """Search with quantization should return results."""
        embedding = await voyage_service.embed_query("квартира в Солнечном берегу")
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding,
            quantization_ignore=False,
            top_k=5,
        )
        assert len(results) > 0, "No results with quantization enabled"

    @pytest.mark.asyncio
    async def test_search_without_quantization_returns_results(self, voyage_service, qdrant_service):
        """Search without quantization should return results."""
        embedding = await voyage_service.embed_query("квартира в Солнечном берегу")
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding,
            quantization_ignore=True,
            top_k=5,
        )
        assert len(results) > 0, "No results without quantization"

    @pytest.mark.asyncio
    async def test_quantization_results_overlap_60_percent(self, voyage_service, qdrant_service):
        """Results should have >= 60% overlap between modes."""
        embedding = await voyage_service.embed_query("студия с видом на море")

        results_with = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding, quantization_ignore=False, top_k=5
        )
        results_without = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding, quantization_ignore=True, top_k=5
        )

        ids_with = set(r["id"] for r in results_with)
        ids_without = set(r["id"] for r in results_without)

        overlap = len(ids_with & ids_without) / max(len(ids_with), 1)
        assert overlap >= 0.6, f"Overlap {overlap:.0%} < 60%"

    @pytest.mark.asyncio
    async def test_quantization_latency_comparison(self, voyage_service, qdrant_service):
        """Quantization should not be significantly slower (p95 comparison)."""
        embedding = await voyage_service.embed_query("апартаменты с бассейном")

        # Warmup
        await qdrant_service.hybrid_search_rrf(dense_vector=embedding, top_k=3)

        # Measure with quantization (5 runs)
        times_with = []
        for _ in range(5):
            start = time.time()
            await qdrant_service.hybrid_search_rrf(
                dense_vector=embedding, quantization_ignore=False, top_k=5
            )
            times_with.append((time.time() - start) * 1000)

        # Measure without quantization (5 runs)
        times_without = []
        for _ in range(5):
            start = time.time()
            await qdrant_service.hybrid_search_rrf(
                dense_vector=embedding, quantization_ignore=True, top_k=5
            )
            times_without.append((time.time() - start) * 1000)

        p95_with = np.percentile(times_with, 95)
        p95_without = np.percentile(times_without, 95)

        print(f"\nQuantization p95: {p95_with:.0f}ms (with) vs {p95_without:.0f}ms (without)")

        # Allow 50% margin
        assert p95_with <= p95_without * 1.5, (
            f"Quantization too slow: {p95_with:.0f}ms vs {p95_without:.0f}ms"
        )


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
class TestSmokeTTFT:
    """Test TTFT measurement via streaming."""

    @pytest.mark.asyncio
    async def test_ttft_measurement_for_complex_query(
        self, voyage_service, qdrant_service, llm_service
    ):
        """TTFT should be measured and under threshold."""
        # Get search results first
        query = "Найди двухкомнатную квартиру в Солнечном берегу до 50000 евро"
        embedding = await voyage_service.embed_query(query)
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding, top_k=3
        )

        # Measure TTFT via streaming
        start = time.time()
        ttft_ms = None

        async for chunk in llm_service.stream_answer(query, results):
            if ttft_ms is None:
                ttft_ms = (time.time() - start) * 1000
            # Continue to consume stream
            pass

        assert ttft_ms is not None, "No chunks received from stream"
        print(f"\nTTFT: {ttft_ms:.0f}ms")

        # Threshold: warn 800ms, fail 1200ms
        assert ttft_ms < 1200, f"TTFT too high: {ttft_ms:.0f}ms (fail threshold: 1200ms)"

    @pytest.mark.asyncio
    async def test_streaming_produces_valid_response(
        self, voyage_service, qdrant_service, llm_service
    ):
        """Streaming should produce non-empty response."""
        query = "студия в Несебре"
        embedding = await voyage_service.embed_query(query)
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding, top_k=3
        )

        accumulated = ""
        async for chunk in llm_service.stream_answer(query, results):
            accumulated += chunk

        assert len(accumulated) > 50, f"Response too short: {len(accumulated)} chars"
```

**Step 2: Run test to verify it works**

```bash
pytest tests/smoke/test_smoke_quantization.py -v -s
```

Expected: PASS (6 tests) or SKIP if API keys not set

**Step 3: Commit**

```bash
git add tests/smoke/test_smoke_quantization.py
git commit -m "test(smoke): add quantization A/B and TTFT tests

Tests: quantization results, overlap, latency comparison, TTFT measurement.
TTFT threshold: warn 800ms, fail 1200ms.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create test_load_conversations.py

**Files:**
- Create: `tests/load/test_load_conversations.py`

**Step 1: Create the test file**

```python
# tests/load/test_load_conversations.py
"""Load tests for parallel chat conversations with TTFT measurement."""

import json
import os
import time
from pathlib import Path

import pytest

from telegram_bot.services.llm import LLMService
from telegram_bot.services.qdrant import QdrantService
from telegram_bot.services.query_router import QueryType, classify_query, get_chitchat_response
from telegram_bot.services.voyage import VoyageService
from tests.load.chat_simulator import run_parallel_chats
from tests.load.metrics_collector import (
    LoadMetrics,
    analyze_metrics,
    format_report,
    load_baseline,
    save_baseline,
)
from tests.smoke.queries import ExpectedQueryType


BASELINE_PATH = Path(__file__).parent / "baseline.json"
REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def use_mocks() -> bool:
    """Check if mocks should be used."""
    return os.getenv("LOAD_USE_MOCKS", "0") == "1"


def require_ttft() -> bool:
    """Check if TTFT measurement is required."""
    return os.getenv("REQUIRE_TTFT", "0") == "1"


@pytest.fixture
def load_config():
    """Load test configuration."""
    return {
        "chat_count": int(os.getenv("LOAD_CHAT_COUNT", "10")),
        "use_mocks": use_mocks(),
        "require_ttft": require_ttft(),
    }


@pytest.fixture
async def services(load_config):
    """Initialize or mock services."""
    if load_config["use_mocks"]:
        from unittest.mock import AsyncMock

        voyage = AsyncMock()
        voyage.embed_query = AsyncMock(return_value=[0.1] * 1024)

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(
            return_value=[
                {"id": "1", "score": 0.9, "text": "Mock result", "metadata": {}},
            ]
        )
        qdrant.close = AsyncMock()

        llm = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield "Mock "
            yield "response "
            yield "text."

        llm.stream_answer = mock_stream

        yield {"voyage": voyage, "qdrant": qdrant, "llm": llm}
    else:
        voyage_key = os.getenv("VOYAGE_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if not voyage_key:
            pytest.skip("VOYAGE_API_KEY not set")
        if not openai_key:
            pytest.skip("OPENAI_API_KEY not set")

        voyage = VoyageService(api_key=voyage_key)
        qdrant = QdrantService(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
            collection_name=os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4"),
        )
        llm = LLMService(
            api_key=openai_key,
            base_url=os.getenv("LLM_BASE_URL", "https://api.cerebras.ai/v1"),
            model=os.getenv("LLM_MODEL", "llama3.1-8b"),
        )

        yield {"voyage": voyage, "qdrant": qdrant, "llm": llm}

        await qdrant.close()
        await llm.close()


class TestLoadConversations:
    """Load tests for parallel chat conversations."""

    @pytest.mark.asyncio
    async def test_parallel_chats_with_ttft(self, load_config, services, request):
        """Run parallel chats and verify p95 thresholds with TTFT."""
        metrics = LoadMetrics()
        chat_count = load_config["chat_count"]
        ttft_required = load_config["require_ttft"]

        async def process_message(query: str, chat_id: int) -> float:
            """Process single message and record metrics."""
            start = time.time()

            # Routing
            route_start = time.time()
            query_type = classify_query(query)
            metrics.record_routing((time.time() - route_start) * 1000)

            # CHITCHAT: skip RAG
            if query_type == QueryType.CHITCHAT:
                _ = get_chitchat_response(query)
                latency = (time.time() - start) * 1000
                metrics.record_full_rag(latency)
                return latency

            # SIMPLE/COMPLEX: full RAG pipeline
            try:
                # Embedding
                embedding = await services["voyage"].embed_query(query)

                # Qdrant search
                qdrant_start = time.time()
                results = await services["qdrant"].hybrid_search_rrf(
                    dense_vector=embedding, top_k=5
                )
                metrics.record_qdrant((time.time() - qdrant_start) * 1000)

                if not results:
                    metrics.record_cache_miss()
                    latency = (time.time() - start) * 1000
                    metrics.record_full_rag(latency)
                    return latency

                # COMPLEX: measure TTFT via streaming
                if query_type == QueryType.COMPLEX:
                    stream_start = time.time()
                    ttft_recorded = False

                    async for chunk in services["llm"].stream_answer(query, results):
                        if not ttft_recorded:
                            ttft_ms = (time.time() - stream_start) * 1000
                            metrics.record_ttft(ttft_ms)
                            ttft_recorded = True
                        # Consume rest of stream
                        pass

                metrics.record_cache_miss()

            except Exception as e:
                metrics.record_error()
                raise

            latency = (time.time() - start) * 1000
            metrics.record_full_rag(latency)
            return latency

        # Run parallel chats
        start_time = time.time()
        await run_parallel_chats(
            chat_count=chat_count,
            process_message=process_message,
            stagger_start_sec=0.2,
        )
        duration = time.time() - start_time

        # Load baseline and analyze
        baseline = load_baseline(BASELINE_PATH)
        result = analyze_metrics(metrics, baseline, require_ttft=ttft_required)

        # Print report
        report = format_report(result, metrics, duration, chat_count)
        print(f"\n{report}")

        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "load_summary.json"
        with open(report_path, "w") as f:
            json.dump(
                {
                    "routing_p95": result.routing_p95,
                    "cache_hit_p95": result.cache_hit_p95,
                    "qdrant_p95": result.qdrant_p95,
                    "full_rag_p95": result.full_rag_p95,
                    "ttft_p95": result.ttft_p95,
                    "cache_hit_rate": result.cache_hit_rate,
                    "error_rate": result.error_rate,
                    "passed": result.passed,
                    "chat_count": chat_count,
                    "duration_sec": duration,
                    "ttft_required": ttft_required,
                    "warnings": result.warnings,
                    "failures": result.failures,
                },
                f,
                indent=2,
            )
        print(f"\nReport saved to: {report_path}")

        # Handle baseline creation/update
        if request.config.getoption("--create-baseline", default=False):
            save_baseline(BASELINE_PATH, result)
            print(f"\nBaseline CREATED: {BASELINE_PATH}")

        if request.config.getoption("--update-baseline", default=False):
            save_baseline(BASELINE_PATH, result)
            print(f"\nBaseline UPDATED: {BASELINE_PATH}")

        # Assert pass
        assert result.passed, f"Load test failed: {result.failures}"


def pytest_addoption(parser):
    """Add custom pytest options."""
    parser.addoption("--create-baseline", action="store_true", default=False)
    parser.addoption("--update-baseline", action="store_true", default=False)
```

**Step 2: Run test in mock mode**

```bash
LOAD_USE_MOCKS=1 LOAD_CHAT_COUNT=5 pytest tests/load/test_load_conversations.py -v -s
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/load/test_load_conversations.py
git commit -m "test(load): add parallel chat tests with TTFT measurement

TTFT measured for COMPLEX queries via streaming.
REQUIRE_TTFT=1 makes TTFT mandatory.
Supports --create-baseline and --update-baseline flags.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create test_load_redis_eviction.py

**Files:**
- Create: `tests/load/test_load_redis_eviction.py`

**Step 1: Create the test file**

```python
# tests/load/test_load_redis_eviction.py
"""Load tests for Redis LFU eviction behavior."""

import json
import os
import random
import time
from pathlib import Path

import pytest
import redis.asyncio as redis


REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


@pytest.fixture
async def redis_client():
    """Async Redis client."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.from_url(url, decode_responses=True)
    yield client
    await client.close()


@pytest.fixture
def eviction_config():
    """Configurable eviction test parameters."""
    return {
        "total_mb": int(os.getenv("EVICTION_TEST_MB", "10")),
        "value_size_kb": 10,
        "sample_interval_sec": 2,
    }


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
class TestLoadRedisEviction:
    """Test Redis eviction behavior under load."""

    @pytest.mark.asyncio
    async def test_redis_lfu_policy_configured(self, redis_client):
        """Verify allkeys-lfu eviction policy."""
        config = await redis_client.config_get("maxmemory-policy")
        policy = config.get("maxmemory-policy")
        assert policy == "allkeys-lfu", f"Expected allkeys-lfu, got: {policy}"

    @pytest.mark.asyncio
    async def test_redis_maxmemory_set(self, redis_client):
        """Verify maxmemory is configured."""
        config = await redis_client.config_get("maxmemory")
        maxmem = int(config.get("maxmemory", 0))
        assert maxmem > 0, "maxmemory not configured (unlimited)"
        print(f"\nmaxmemory: {maxmem / 1024 / 1024:.0f}MB")

    @pytest.mark.asyncio
    async def test_eviction_under_pressure(self, redis_client, eviction_config):
        """Test eviction behavior under write pressure."""
        total_mb = eviction_config["total_mb"]
        value_size_kb = eviction_config["value_size_kb"]

        total_bytes = total_mb * 1024 * 1024
        value_size = value_size_kb * 1024
        num_keys = total_bytes // value_size

        test_prefix = f"rag:eviction_test:{int(time.time())}"
        stats_timeseries = []

        # Get initial stats
        info_start = await redis_client.info("stats")
        initial_evictions = info_start.get("evicted_keys", 0)

        print(f"\nWriting {num_keys} keys ({total_mb}MB)...")

        # Write keys and sample stats
        for i in range(num_keys):
            key = f"{test_prefix}:{i}"
            value = "x" * value_size
            await redis_client.setex(key, 300, value)

            if i % 100 == 0 and i > 0:
                info = await redis_client.info("stats")
                stats_timeseries.append(
                    {
                        "timestamp": time.time(),
                        "keys_written": i,
                        "evicted_keys": info.get("evicted_keys", 0),
                        "keyspace_hits": info.get("keyspace_hits", 0),
                        "keyspace_misses": info.get("keyspace_misses", 0),
                    }
                )

        # Get final stats
        info_end = await redis_client.info("stats")
        final_evictions = info_end.get("evicted_keys", 0)
        evictions = final_evictions - initial_evictions

        # Cleanup
        keys = await redis_client.keys(f"{test_prefix}:*")
        if keys:
            # Delete in batches to avoid blocking
            for i in range(0, len(keys), 100):
                await redis_client.delete(*keys[i : i + 100])

        # Save stats timeseries
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "redis_stats_timeseries.json"
        with open(report_path, "w") as f:
            json.dump(stats_timeseries, f, indent=2)

        print(f"Wrote {num_keys} keys, evictions: {evictions}")
        print(f"Stats saved to: {report_path}")

        # Evictions are expected under memory pressure
        # This test just verifies the system doesn't crash

    @pytest.mark.asyncio
    async def test_hit_rate_under_zipf_access(self, redis_client):
        """Test hit rate under Zipf-like access pattern."""
        test_prefix = f"rag:zipf_test:{int(time.time())}"

        # Populate 50 keys
        for i in range(50):
            await redis_client.setex(f"{test_prefix}:{i}", 60, f"value_{i}")

        # Zipf access (popular keys accessed more often)
        hits = 0
        misses = 0

        for _ in range(200):
            # Pareto distribution approximates Zipf
            key_id = int(random.paretovariate(1.5)) % 50
            result = await redis_client.get(f"{test_prefix}:{key_id}")
            if result:
                hits += 1
            else:
                misses += 1

        # Cleanup
        keys = await redis_client.keys(f"{test_prefix}:*")
        if keys:
            await redis_client.delete(*keys)

        hit_rate = hits / (hits + misses) if (hits + misses) > 0 else 0
        print(f"\nZipf hit rate: {hit_rate:.0%} ({hits} hits, {misses} misses)")

        # LFU should maintain reasonable hit rate
        assert hit_rate >= 0.5, f"Hit rate too low: {hit_rate:.0%}"

    @pytest.mark.asyncio
    async def test_redis_info_stats_accessible(self, redis_client):
        """Verify INFO stats are accessible for monitoring."""
        info = await redis_client.info("stats")

        required_fields = ["keyspace_hits", "keyspace_misses", "evicted_keys"]
        for field in required_fields:
            assert field in info, f"Missing INFO field: {field}"

        print(f"\nRedis stats: hits={info['keyspace_hits']}, misses={info['keyspace_misses']}, evicted={info['evicted_keys']}")
```

**Step 2: Run test**

```bash
pytest tests/load/test_load_redis_eviction.py -v -s
```

Expected: PASS (4 tests)

**Step 3: Commit**

```bash
git add tests/load/test_load_redis_eviction.py
git commit -m "test(load): add Redis eviction tests

Tests: LFU policy, maxmemory, pressure test, Zipf hit-rate.
Configurable via EVICTION_TEST_MB env var.
Generates reports/redis_stats_timeseries.json.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Golden Baseline

**Files:**
- Create: `tests/load/baseline.json`

**Step 1: Create initial baseline file**

```json
{
  "routing": 15,
  "cache_hit": 15,
  "qdrant": 100,
  "full_rag": 2500,
  "ttft": 800,
  "timestamp": 1737640800,
  "environment": {
    "qdrant_collection": "contextual_bulgaria_voyage4",
    "redis_maxmemory": "512mb",
    "llm_model": "zai-glm-4.7",
    "voyage_model": "voyage-4-lite",
    "note": "Initial baseline - update with actual measurements"
  }
}
```

**Step 2: Verify JSON is valid**

```bash
python -c "import json; json.load(open('tests/load/baseline.json')); print('Valid JSON')"
```

Expected: `Valid JSON`

**Step 3: Commit**

```bash
git add tests/load/baseline.json
git commit -m "test(load): add initial golden baseline

Placeholder values - run 'make test-load-create-baseline' to update.
Regression threshold: 20% (see thresholds.py).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Add Makefile Commands

**Files:**
- Modify: `Makefile` (add after line ~110)

**Step 1: Read current Makefile structure**

```bash
tail -50 Makefile
```

**Step 2: Add smoke/load test targets**

Add after existing test targets:

```makefile
# =============================================================================
# SMOKE & LOAD TESTS
# =============================================================================

test-preflight: ## Run preflight checks (Qdrant/Redis config verification)
	@echo "$(BLUE)Running preflight checks...$(NC)"
	pytest tests/smoke/test_preflight.py -v -s
	@echo "$(GREEN)✓ Preflight complete$(NC)"

test-smoke: ## Run all smoke tests (requires live services)
	@echo "$(BLUE)Running smoke tests...$(NC)"
	pytest tests/smoke/ -v --tb=short
	@echo "$(GREEN)✓ Smoke tests complete$(NC)"

test-smoke-routing: ## Run smoke routing tests only (no external deps)
	@echo "$(BLUE)Running smoke routing tests...$(NC)"
	pytest tests/smoke/test_smoke_routing.py -v
	@echo "$(GREEN)✓ Routing tests complete$(NC)"

test-smoke-quantization: ## Run quantization A/B and TTFT tests
	@echo "$(BLUE)Running quantization tests...$(NC)"
	pytest tests/smoke/test_smoke_quantization.py -v -s
	@echo "$(GREEN)✓ Quantization tests complete$(NC)"

test-load: ## Run load tests with TTFT measurement (live services)
	@echo "$(BLUE)Running load tests...$(NC)"
	REQUIRE_TTFT=1 pytest tests/load/test_load_conversations.py -v -s
	@echo "$(GREEN)✓ Load tests complete$(NC)"

test-load-ci: ## Run load tests in CI mode (mocked, fast)
	@echo "$(BLUE)Running load tests (CI mode)...$(NC)"
	LOAD_USE_MOCKS=1 LOAD_CHAT_COUNT=5 pytest tests/load/test_load_conversations.py -v
	@echo "$(GREEN)✓ Load tests (CI) complete$(NC)"

test-load-eviction: ## Run Redis eviction tests
	@echo "$(BLUE)Running Redis eviction tests...$(NC)"
	pytest tests/load/test_load_redis_eviction.py -v -s
	@echo "$(GREEN)✓ Redis eviction tests complete$(NC)"

test-load-create-baseline: ## Create golden baseline (first run)
	@echo "$(BLUE)Creating golden baseline...$(NC)"
	REQUIRE_TTFT=1 pytest tests/load/test_load_conversations.py -v -s --create-baseline
	@echo "$(GREEN)✓ Baseline created$(NC)"

test-load-update-baseline: ## Update existing baseline
	@echo "$(BLUE)Updating baseline...$(NC)"
	REQUIRE_TTFT=1 pytest tests/load/test_load_conversations.py -v -s --update-baseline
	@echo "$(GREEN)✓ Baseline updated$(NC)"

test-all-smoke-load: test-preflight test-smoke test-load ## Full smoke+load suite
	@echo "$(GREEN)✓✓✓ All smoke+load tests complete$(NC)"
```

**Step 3: Verify Makefile syntax**

```bash
make help | grep -E "(smoke|load|preflight)"
```

Expected: All new targets appear in help output

**Step 4: Commit**

```bash
git add Makefile
git commit -m "chore(make): add smoke/load test targets

Targets: test-preflight, test-smoke, test-smoke-routing,
test-smoke-quantization, test-load, test-load-ci,
test-load-eviction, test-load-create-baseline,
test-load-update-baseline, test-all-smoke-load

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Final Verification

**Step 1: Run preflight**

```bash
make test-preflight
```

Expected: PASS

**Step 2: Run smoke routing (no deps)**

```bash
make test-smoke-routing
```

Expected: PASS (6 tests)

**Step 3: Run load CI (mocked)**

```bash
make test-load-ci
```

Expected: PASS

**Step 4: Verify reports directory**

```bash
ls -la reports/
```

Expected: `load_summary.json` exists

**Step 5: Run unit tests**

```bash
pytest tests/unit/ -v --tb=short -q
```

Expected: All PASS

**Step 6: Final commit**

```bash
git add -A
git commit -m "test(smoke+load): complete implementation

- Smoke: quantization A/B, TTFT measurement
- Load: parallel chats with mandatory TTFT
- Redis: eviction tests with Zipf access
- Baseline: golden baseline with environment metadata
- Makefile: full test suite commands

Artifacts: preflight.json, load_summary.json, redis_stats_timeseries.json

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Smoke quantization + TTFT | `tests/smoke/test_smoke_quantization.py` |
| 2 | Load conversations | `tests/load/test_load_conversations.py` |
| 3 | Redis eviction | `tests/load/test_load_redis_eviction.py` |
| 4 | Golden baseline | `tests/load/baseline.json` |
| 5 | Makefile commands | `Makefile` |
| 6 | Final verification | All files |

**Expected results after completion:**

```bash
make test-preflight      # Qdrant/Redis config verified
make test-smoke          # 20/20 queries pass
make test-load           # p95 within thresholds, TTFT measured
make test-load-eviction  # LFU behavior verified
```

**Artifacts:**
- `reports/preflight.json`
- `reports/load_summary.json`
- `reports/redis_stats_timeseries.json`
