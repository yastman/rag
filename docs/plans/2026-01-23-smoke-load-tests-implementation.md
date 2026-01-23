# Smoke + Load Tests Implementation Plan (v2)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement smoke tests (20 queries) and load tests (20-50 parallel chats) to verify routing, caching, quantization A/B, streaming, and p95 latency thresholds.

**Architecture:** Create `tests/smoke/` and `tests/load/` directories with shared fixtures. Smoke tests use live services (Qdrant, Redis). Load tests support live/mock toggle via `LOAD_USE_MOCKS=1`. Metrics collected via `metrics_collector.py` with baseline regression detection.

**Tech Stack:** pytest, pytest-asyncio, numpy (percentiles), redis.asyncio, httpx

---

## Task 0: Create Pre-flight Checks

**Files:**
- Create: `tests/smoke/test_preflight.py`

**Step 1: Write pre-flight test**

```python
# tests/smoke/test_preflight.py
"""Pre-flight checks for Qdrant and Redis configuration.

These tests verify that production features are actually enabled,
not just declared in code. Run before any other smoke/load tests.
"""

import json
import os
from pathlib import Path

import httpx
import pytest
import redis.asyncio as redis


REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


@pytest.fixture(scope="module")
def qdrant_url():
    return os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.fixture(scope="module")
def redis_url():
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture(scope="module")
def collection_name():
    return os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4")


class TestPreflightQdrant:
    """Verify Qdrant configuration before tests."""

    def test_qdrant_collection_exists(self, qdrant_url, collection_name):
        """Collection should exist and be green."""
        resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
        assert resp.status_code == 200, f"Collection {collection_name} not found"

        data = resp.json()
        status = data["result"]["status"]
        assert status == "green", f"Collection status: {status}, expected green"

    def test_qdrant_binary_quantization_enabled(self, qdrant_url, collection_name):
        """Binary quantization should be enabled with always_ram=true."""
        resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
        data = resp.json()

        quant_config = data["result"]["config"].get("quantization_config", {})
        binary_config = quant_config.get("binary", {})

        assert binary_config, f"Binary quantization not configured. Got: {quant_config}"
        assert binary_config.get("always_ram") is True, (
            f"always_ram should be true, got: {binary_config}"
        )

    def test_qdrant_optimizer_idle(self, qdrant_url, collection_name):
        """Optimizer should be idle (not rebuilding indexes)."""
        resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
        data = resp.json()

        optimizer_status = data["result"].get("optimizer_status")
        assert optimizer_status == "ok", f"Optimizer busy: {optimizer_status}"


class TestPreflightRedis:
    """Verify Redis configuration before tests."""

    @pytest.fixture
    async def redis_client(self, redis_url):
        client = redis.from_url(redis_url, decode_responses=True)
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_redis_connection(self, redis_client):
        """Redis should be reachable."""
        pong = await redis_client.ping()
        assert pong is True

    @pytest.mark.asyncio
    async def test_redis_maxmemory_set(self, redis_client):
        """maxmemory should be configured (not 0)."""
        config = await redis_client.config_get("maxmemory")
        maxmem = int(config.get("maxmemory", 0))
        assert maxmem > 0, "maxmemory not configured (unlimited)"

    @pytest.mark.asyncio
    async def test_redis_lfu_eviction_policy(self, redis_client):
        """Eviction policy should be allkeys-lfu."""
        config = await redis_client.config_get("maxmemory-policy")
        policy = config.get("maxmemory-policy")
        assert policy == "allkeys-lfu", f"Expected allkeys-lfu, got: {policy}"

    @pytest.mark.asyncio
    async def test_redis_semantic_cache_index_exists(self, redis_client):
        """Semantic cache RediSearch index should exist."""
        try:
            # List all FT indexes
            indexes = await redis_client.execute_command("FT._LIST")
            # Check for any rag/llm cache index
            has_cache_index = any("cache" in idx.lower() or "rag" in idx.lower() for idx in indexes)
            if not has_cache_index:
                pytest.skip("No semantic cache index found (may not be configured)")
        except Exception as e:
            pytest.skip(f"RediSearch not available: {e}")


class TestPreflightReport:
    """Generate preflight report."""

    @pytest.mark.asyncio
    async def test_generate_preflight_report(self, qdrant_url, redis_url, collection_name):
        """Generate reports/preflight.json with all config values."""
        report = {
            "qdrant": {},
            "redis": {},
            "status": "unknown",
        }

        # Qdrant info
        try:
            resp = httpx.get(f"{qdrant_url}/collections/{collection_name}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()["result"]
                report["qdrant"] = {
                    "collection": collection_name,
                    "status": data.get("status"),
                    "optimizer_status": data.get("optimizer_status"),
                    "points_count": data.get("points_count"),
                    "quantization_config": data["config"].get("quantization_config"),
                }
        except Exception as e:
            report["qdrant"]["error"] = str(e)

        # Redis info
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            config_mem = await client.config_get("maxmemory")
            config_policy = await client.config_get("maxmemory-policy")
            info_stats = await client.info("stats")

            report["redis"] = {
                "maxmemory": int(config_mem.get("maxmemory", 0)),
                "maxmemory_policy": config_policy.get("maxmemory-policy"),
                "keyspace_hits": info_stats.get("keyspace_hits", 0),
                "keyspace_misses": info_stats.get("keyspace_misses", 0),
                "evicted_keys": info_stats.get("evicted_keys", 0),
            }
            await client.close()
        except Exception as e:
            report["redis"]["error"] = str(e)

        # Overall status
        qdrant_ok = (
            report["qdrant"].get("status") == "green"
            and report["qdrant"].get("quantization_config", {}).get("binary", {}).get("always_ram")
        )
        redis_ok = (
            report["redis"].get("maxmemory", 0) > 0
            and report["redis"].get("maxmemory_policy") == "allkeys-lfu"
        )
        report["status"] = "PASS" if (qdrant_ok and redis_ok) else "FAIL"

        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "preflight.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nPreflight report saved to: {report_path}")
        print(json.dumps(report, indent=2))

        assert report["status"] == "PASS", f"Preflight failed: {report}"
```

**Step 2: Create reports directory**

```bash
mkdir -p reports
echo "reports/" >> .gitignore
```

**Step 3: Run preflight**

```bash
pytest tests/smoke/test_preflight.py -v -s
```

Expected: PASS with preflight.json generated

**Step 4: Commit**

```bash
git add tests/smoke/test_preflight.py
git commit -m "test(preflight): add Qdrant/Redis config verification

Checks: binary quantization, always_ram, allkeys-lfu, maxmemory.
Generates reports/preflight.json.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 1: Create Test Directory Structure

**Files:**
- Create: `tests/smoke/__init__.py`
- Create: `tests/smoke/conftest.py`
- Create: `tests/load/__init__.py`
- Create: `tests/load/conftest.py`

**Step 1: Create smoke directory and init**

```python
# tests/smoke/__init__.py
"""Smoke tests for RAG pipeline (20 queries, live services)."""
```

**Step 2: Create smoke conftest with Redis health check**

```python
# tests/smoke/conftest.py
"""Smoke test fixtures - require live Qdrant and Redis."""

import os

import httpx
import pytest
import redis.asyncio as redis

from telegram_bot.services.cache import CacheService
from telegram_bot.services.qdrant import QdrantService
from telegram_bot.services.voyage import VoyageService


@pytest.fixture(scope="module")
def require_live_services():
    """Skip if live services not available. Checks BOTH Qdrant AND Redis."""
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Check Qdrant
    try:
        resp = httpx.get(f"{qdrant_url}/collections", timeout=2)
        if resp.status_code != 200:
            pytest.skip("Qdrant not available")
    except Exception:
        pytest.skip("Qdrant not available")

    # Check Redis
    import asyncio

    async def check_redis():
        try:
            client = redis.from_url(redis_url, socket_connect_timeout=2)
            await client.ping()
            await client.close()
        except Exception:
            pytest.skip("Redis not available")

    asyncio.get_event_loop().run_until_complete(check_redis())


@pytest.fixture(scope="module")
async def voyage_service():
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

    service = QdrantService(
        url=url,
        api_key=api_key or None,
        collection_name=collection,
    )
    yield service
    await service.close()


@pytest.fixture(scope="module")
async def cache_service():
    """CacheService for caching."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    service = CacheService(redis_url=redis_url)
    await service.initialize()
    yield service
    await service.close()
```

**Step 3: Create load directory and init**

```python
# tests/load/__init__.py
"""Load tests for RAG pipeline (parallel chats, p95 metrics)."""
```

**Step 4: Create load conftest**

```python
# tests/load/conftest.py
"""Load test fixtures - support live/mock toggle."""

import os
from unittest.mock import AsyncMock

import pytest


def use_mocks() -> bool:
    """Check if mocks should be used."""
    return os.getenv("LOAD_USE_MOCKS", "0") == "1"


@pytest.fixture
def load_config():
    """Load test configuration from env."""
    return {
        "chat_count": int(os.getenv("LOAD_CHAT_COUNT", "30")),
        "duration_min": int(os.getenv("LOAD_DURATION_MIN", "10")),
        "use_mocks": use_mocks(),
        "eviction_test_mb": int(os.getenv("EVICTION_TEST_MB", "10")),  # Configurable
    }


@pytest.fixture
def mock_voyage_service():
    """Mock VoyageService for CI."""
    service = AsyncMock()
    service.embed_query = AsyncMock(return_value=[0.1] * 1024)
    service.rerank = AsyncMock(return_value=[
        {"index": 0, "score": 0.95},
        {"index": 1, "score": 0.85},
    ])
    return service


@pytest.fixture
def mock_qdrant_service():
    """Mock QdrantService for CI."""
    service = AsyncMock()
    service.hybrid_search_rrf = AsyncMock(return_value=[
        {"id": "1", "score": 0.9, "text": "Mock result 1", "metadata": {}},
        {"id": "2", "score": 0.8, "text": "Mock result 2", "metadata": {}},
    ])
    return service
```

**Step 5: Run import check**

```bash
python -c "from tests.smoke.conftest import *; from tests.load.conftest import *; print('OK')"
```

Expected: `OK`

**Step 6: Commit**

```bash
git add tests/smoke/ tests/load/
git commit -m "test(structure): create smoke and load test directories

Smoke conftest checks BOTH Qdrant AND Redis availability.
Load conftest supports EVICTION_TEST_MB for configurable pressure.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create Query Definitions (Fixed 6/6/8)

**Files:**
- Create: `tests/smoke/queries.py`

**Step 1: Create queries.py with correct 6/6/8 distribution**

```python
# tests/smoke/queries.py
"""Smoke test query definitions by type.

Distribution: 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX = 20 total
"""

from dataclasses import dataclass
from enum import Enum


class ExpectedQueryType(Enum):
    """Expected query classification."""
    CHITCHAT = "CHITCHAT"
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"


@dataclass
class SmokeQuery:
    """Smoke test query with expected behavior."""
    text: str
    expected_type: ExpectedQueryType
    expect_cache_write: bool = False
    expect_rerank: bool = False


# 20 queries: 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX (STRICT)
SMOKE_QUERIES: list[SmokeQuery] = [
    # === CHITCHAT (6) - skip RAG entirely ===
    SmokeQuery("Привет!", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Добрый день", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Спасибо за помощь", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Кто ты?", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Что ты умеешь?", ExpectedQueryType.CHITCHAT),
    SmokeQuery("Пока, до свидания", ExpectedQueryType.CHITCHAT),

    # === SIMPLE (6) - light RAG, skip rerank ===
    # These match SIMPLE_PATTERNS in query_router.py
    SmokeQuery("Сколько стоит квартира?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Какая цена на студию?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Сколько стоит дом?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Какая цена аренды?", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Двухкомнатная квартира", ExpectedQueryType.SIMPLE, expect_cache_write=True),
    SmokeQuery("Трёхкомнатная квартира", ExpectedQueryType.SIMPLE, expect_cache_write=True),

    # === COMPLEX (8) - full RAG + rerank + quantization A/B ===
    SmokeQuery(
        "Найди двухкомнатную квартиру в Солнечном берегу до 50000 евро с видом на море",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Квартиры в комплексе Harmony Suites корпус 3 с мебелью",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Сравни цены на студии в Несебре и Равде",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Апартаменты с двумя спальнями рядом с пляжем, первая линия",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Что лучше: Sunny Beach или Sveti Vlas для инвестиций?",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Новостройки с рассрочкой платежа на 2 года",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Квартира с паркингом и кладовой в закрытом комплексе",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
    SmokeQuery(
        "Покажи варианты до 70000 евро с ремонтом под ключ",
        ExpectedQueryType.COMPLEX,
        expect_cache_write=True,
        expect_rerank=True,
    ),
]


def get_queries_by_type(query_type: ExpectedQueryType) -> list[SmokeQuery]:
    """Get queries filtered by type."""
    return [q for q in SMOKE_QUERIES if q.expected_type == query_type]


def validate_distribution():
    """Validate 6/6/8 distribution."""
    chitchat = len(get_queries_by_type(ExpectedQueryType.CHITCHAT))
    simple = len(get_queries_by_type(ExpectedQueryType.SIMPLE))
    complex_ = len(get_queries_by_type(ExpectedQueryType.COMPLEX))

    assert chitchat == 6, f"CHITCHAT should be 6, got {chitchat}"
    assert simple == 6, f"SIMPLE should be 6, got {simple}"
    assert complex_ == 8, f"COMPLEX should be 8, got {complex_}"
    assert len(SMOKE_QUERIES) == 20, f"Total should be 20, got {len(SMOKE_QUERIES)}"


# Validate on import
validate_distribution()
```

**Step 2: Run import check**

```bash
python -c "from tests.smoke.queries import SMOKE_QUERIES, get_queries_by_type, ExpectedQueryType; print(f'CHITCHAT: {len(get_queries_by_type(ExpectedQueryType.CHITCHAT))}'); print(f'SIMPLE: {len(get_queries_by_type(ExpectedQueryType.SIMPLE))}'); print(f'COMPLEX: {len(get_queries_by_type(ExpectedQueryType.COMPLEX))}')"
```

Expected:
```
CHITCHAT: 6
SIMPLE: 6
COMPLEX: 8
```

**Step 3: Commit**

```bash
git add tests/smoke/queries.py
git commit -m "test(smoke): add 20 query definitions (strict 6/6/8)

6 CHITCHAT, 6 SIMPLE, 8 COMPLEX with validation on import.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create Metrics Collector (with TTFT optional)

**Files:**
- Create: `tests/load/metrics_collector.py`
- Create: `tests/load/thresholds.py`

**Step 1: Create thresholds.py**

```python
# tests/load/thresholds.py
"""P95 latency thresholds for load tests."""

from dataclasses import dataclass


@dataclass
class Thresholds:
    """Warn and fail thresholds in milliseconds."""
    warn_ms: int
    fail_ms: int


# Component-level thresholds
THRESHOLDS = {
    "routing": Thresholds(warn_ms=20, fail_ms=30),
    "cache_hit": Thresholds(warn_ms=20, fail_ms=30),
    "qdrant": Thresholds(warn_ms=120, fail_ms=200),
    "full_rag": Thresholds(warn_ms=3000, fail_ms=4000),
    # TTFT only checked if actually measured (streaming enabled)
    "ttft": Thresholds(warn_ms=800, fail_ms=1200),
}

# Regression threshold (fail if p95 > baseline * 1.20)
REGRESSION_THRESHOLD = 1.20

# Minimum cache hit rate
MIN_CACHE_HIT_RATE = 0.60
```

**Step 2: Create metrics_collector.py with optional TTFT**

```python
# tests/load/metrics_collector.py
"""Metrics collection and analysis for load tests."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .thresholds import MIN_CACHE_HIT_RATE, REGRESSION_THRESHOLD, THRESHOLDS


@dataclass
class LoadMetrics:
    """Collected metrics from load test run."""

    # Latency samples (ms)
    routing_latencies: list[float] = field(default_factory=list)
    cache_hit_latencies: list[float] = field(default_factory=list)
    qdrant_latencies: list[float] = field(default_factory=list)
    full_rag_latencies: list[float] = field(default_factory=list)
    ttft_latencies: list[float] = field(default_factory=list)  # Only if streaming

    # Counters
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    errors: int = 0

    # Redis stats snapshots
    redis_stats_start: dict = field(default_factory=dict)
    redis_stats_end: dict = field(default_factory=dict)
    redis_stats_timeseries: list[dict] = field(default_factory=list)

    def record_routing(self, latency_ms: float):
        self.routing_latencies.append(latency_ms)

    def record_cache_hit(self, latency_ms: float):
        self.cache_hit_latencies.append(latency_ms)
        self.cache_hits += 1

    def record_cache_miss(self):
        self.cache_misses += 1

    def record_qdrant(self, latency_ms: float):
        self.qdrant_latencies.append(latency_ms)

    def record_full_rag(self, latency_ms: float):
        self.full_rag_latencies.append(latency_ms)
        self.total_requests += 1

    def record_ttft(self, latency_ms: float):
        """Record time-to-first-token (only if streaming is used)."""
        self.ttft_latencies.append(latency_ms)

    def record_error(self):
        self.errors += 1
        self.total_requests += 1

    def record_redis_snapshot(self, stats: dict):
        """Record Redis INFO stats snapshot."""
        self.redis_stats_timeseries.append({
            "timestamp": time.time(),
            **stats,
        })


def percentile(values: list[float], p: int) -> float:
    """Calculate percentile. Returns 0 if no values."""
    if not values:
        return 0.0
    return float(np.percentile(values, p))


@dataclass
class MetricsResult:
    """Analyzed metrics result."""

    routing_p95: float
    cache_hit_p95: float
    qdrant_p95: float
    full_rag_p95: float
    ttft_p95: float  # 0 if not measured

    cache_hit_rate: float
    error_rate: float

    warnings: list[str]
    failures: list[str]
    passed: bool


def analyze_metrics(
    metrics: LoadMetrics,
    baseline: Optional[dict] = None,
    skip_ttft: bool = True,  # Skip TTFT check if not measured
) -> MetricsResult:
    """Analyze collected metrics against thresholds."""
    warnings = []
    failures = []

    # Calculate p95 values
    routing_p95 = percentile(metrics.routing_latencies, 95)
    cache_hit_p95 = percentile(metrics.cache_hit_latencies, 95)
    qdrant_p95 = percentile(metrics.qdrant_latencies, 95)
    full_rag_p95 = percentile(metrics.full_rag_latencies, 95)
    ttft_p95 = percentile(metrics.ttft_latencies, 95)

    # Calculate rates
    total_cache_ops = metrics.cache_hits + metrics.cache_misses
    cache_hit_rate = metrics.cache_hits / total_cache_ops if total_cache_ops > 0 else 0.0
    error_rate = metrics.errors / metrics.total_requests if metrics.total_requests > 0 else 0.0

    # Check absolute thresholds
    checks = [
        ("routing", routing_p95, THRESHOLDS["routing"]),
        ("cache_hit", cache_hit_p95, THRESHOLDS["cache_hit"]),
        ("qdrant", qdrant_p95, THRESHOLDS["qdrant"]),
        ("full_rag", full_rag_p95, THRESHOLDS["full_rag"]),
    ]

    # Only check TTFT if we have measurements
    if metrics.ttft_latencies and not skip_ttft:
        checks.append(("ttft", ttft_p95, THRESHOLDS["ttft"]))

    for name, value, threshold in checks:
        if value > 0:  # Only check if we have data
            if value > threshold.fail_ms:
                failures.append(f"{name} p95 {value:.0f}ms > fail {threshold.fail_ms}ms")
            elif value > threshold.warn_ms:
                warnings.append(f"{name} p95 {value:.0f}ms > warn {threshold.warn_ms}ms")

    # Check cache hit rate (only if we have cache operations)
    if total_cache_ops > 0 and cache_hit_rate < MIN_CACHE_HIT_RATE:
        failures.append(f"cache hit rate {cache_hit_rate:.1%} < min {MIN_CACHE_HIT_RATE:.1%}")

    # Check regression against baseline
    if baseline:
        p95_values = {
            "routing": routing_p95,
            "cache_hit": cache_hit_p95,
            "qdrant": qdrant_p95,
            "full_rag": full_rag_p95,
        }
        if metrics.ttft_latencies:
            p95_values["ttft"] = ttft_p95

        for name, current in p95_values.items():
            if name in baseline and current > 0 and baseline[name] > 0:
                if current > baseline[name] * REGRESSION_THRESHOLD:
                    failures.append(
                        f"{name} regression: {current:.0f}ms vs baseline {baseline[name]:.0f}ms "
                        f"(+{((current / baseline[name]) - 1) * 100:.0f}%)"
                    )

    return MetricsResult(
        routing_p95=routing_p95,
        cache_hit_p95=cache_hit_p95,
        qdrant_p95=qdrant_p95,
        full_rag_p95=full_rag_p95,
        ttft_p95=ttft_p95,
        cache_hit_rate=cache_hit_rate,
        error_rate=error_rate,
        warnings=warnings,
        failures=failures,
        passed=len(failures) == 0,
    )


def load_baseline(path: Path) -> Optional[dict]:
    """Load baseline from JSON file."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_baseline(path: Path, result: MetricsResult):
    """Save current p95 as new baseline."""
    baseline = {
        "routing": result.routing_p95,
        "cache_hit": result.cache_hit_p95,
        "qdrant": result.qdrant_p95,
        "full_rag": result.full_rag_p95,
        "ttft": result.ttft_p95,
        "timestamp": time.time(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)


def format_report(
    result: MetricsResult,
    metrics: LoadMetrics,
    duration_sec: float,
    chat_count: int,
) -> str:
    """Format metrics report for output."""
    lines = [
        "=" * 60,
        "LOAD TEST RESULTS",
        f"Duration: {duration_sec / 60:.1f} min | Chats: {chat_count} | Requests: {metrics.total_requests}",
        "=" * 60,
        "",
        "LATENCY (p95):",
    ]

    p95_checks = [
        ("routing", result.routing_p95, THRESHOLDS["routing"]),
        ("cache_hit", result.cache_hit_p95, THRESHOLDS["cache_hit"]),
        ("qdrant", result.qdrant_p95, THRESHOLDS["qdrant"]),
        ("full_rag", result.full_rag_p95, THRESHOLDS["full_rag"]),
    ]

    # Only show TTFT if measured
    if result.ttft_p95 > 0:
        p95_checks.append(("ttft", result.ttft_p95, THRESHOLDS["ttft"]))

    for name, value, threshold in p95_checks:
        if value > 0:
            status = "✓" if value <= threshold.warn_ms else ("⚠" if value <= threshold.fail_ms else "✗")
            lines.append(
                f"  {name:12}: {value:6.0f}ms {status} (warn: {threshold.warn_ms}ms, fail: {threshold.fail_ms}ms)"
            )
        else:
            lines.append(f"  {name:12}: (not measured)")

    lines.extend([
        "",
        "CACHE:",
        f"  hit_rate:   {result.cache_hit_rate:.0%}   {'✓' if result.cache_hit_rate >= MIN_CACHE_HIT_RATE else '✗'} (min: {MIN_CACHE_HIT_RATE:.0%})",
        "",
    ])

    if result.warnings:
        lines.append("WARNINGS:")
        for w in result.warnings:
            lines.append(f"  ⚠ {w}")
        lines.append("")

    if result.failures:
        lines.append("FAILURES:")
        for f in result.failures:
            lines.append(f"  ✗ {f}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(f"{'PASSED' if result.passed else 'FAILED'}")
    lines.append("=" * 60)

    return "\n".join(lines)
```

**Step 3: Run import check**

```bash
python -c "from tests.load.metrics_collector import LoadMetrics, analyze_metrics; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add tests/load/metrics_collector.py tests/load/thresholds.py
git commit -m "test(load): add metrics collector with optional TTFT

TTFT only checked if streaming is measured. Redis stats timeseries support.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Create Chat Simulator

**Files:**
- Create: `tests/load/chat_simulator.py`

**Step 1: Create chat_simulator.py**

```python
# tests/load/chat_simulator.py
"""Realistic chat conversation simulator for load tests."""

import asyncio
import random
from dataclasses import dataclass
from typing import Callable

from tests.smoke.queries import ExpectedQueryType


@dataclass
class Message:
    """Chat message."""
    query_type: ExpectedQueryType
    text: str


# Conversation template (6 messages per chat)
CONVERSATION_TEMPLATE = [
    Message(ExpectedQueryType.CHITCHAT, "Привет!"),
    Message(ExpectedQueryType.COMPLEX, "{property_query_1}"),
    Message(ExpectedQueryType.SIMPLE, "Сколько стоит?"),
    Message(ExpectedQueryType.COMPLEX, "{property_query_2}"),
    Message(ExpectedQueryType.SIMPLE, "Какая цена на студию?"),
    Message(ExpectedQueryType.CHITCHAT, "Спасибо, пока!"),
]

# Property queries for template substitution
PROPERTY_QUERIES = [
    "Найди квартиру в Солнечном берегу до 50000 евро",
    "Студии в Несебре с видом на море",
    "Апартаменты в Святом Власе с бассейном",
    "Двухкомнатные квартиры в Бургасе центр",
    "Новостройки в Поморие до 40000 евро",
    "Квартиры на первой линии в Равде",
    "Дома у моря в Созополе",
    "Апартаменты с паркингом в Солнечном берегу",
]


def generate_conversation() -> list[Message]:
    """Generate a realistic conversation sequence."""
    queries = random.sample(PROPERTY_QUERIES, 2)

    conversation = []
    for msg in CONVERSATION_TEMPLATE:
        text = msg.text
        if "{property_query_1}" in text:
            text = queries[0]
        elif "{property_query_2}" in text:
            text = queries[1]
        conversation.append(Message(msg.query_type, text))

    return conversation


@dataclass
class ChatResult:
    """Result of a single chat conversation."""
    chat_id: int
    messages_sent: int
    errors: int
    total_latency_ms: float


async def simulate_chat(
    chat_id: int,
    process_message: Callable[[str, int], float],
    message_delay_range: tuple[float, float] = (2.0, 5.0),
) -> ChatResult:
    """Simulate a single chat conversation."""
    conversation = generate_conversation()
    total_latency = 0.0
    errors = 0

    for i, msg in enumerate(conversation):
        try:
            latency = await process_message(msg.text, chat_id)
            total_latency += latency
        except Exception:
            errors += 1

        if i < len(conversation) - 1:
            delay = random.uniform(*message_delay_range)
            await asyncio.sleep(delay)

    return ChatResult(
        chat_id=chat_id,
        messages_sent=len(conversation),
        errors=errors,
        total_latency_ms=total_latency,
    )


async def run_parallel_chats(
    chat_count: int,
    process_message: Callable[[str, int], float],
    stagger_start_sec: float = 0.5,
) -> list[ChatResult]:
    """Run multiple chats in parallel with staggered start."""
    tasks = []

    for i in range(chat_count):
        task = asyncio.create_task(simulate_chat(i, process_message))
        tasks.append(task)

        if i < chat_count - 1:
            await asyncio.sleep(stagger_start_sec)

    return await asyncio.gather(*tasks)
```

**Step 2: Run import check**

```bash
python -c "from tests.load.chat_simulator import generate_conversation; print(len(generate_conversation()), 'messages')"
```

Expected: `6 messages`

**Step 3: Commit**

```bash
git add tests/load/chat_simulator.py
git commit -m "test(load): add chat simulator with 6-message template

CHITCHAT→COMPLEX→SIMPLE→COMPLEX→SIMPLE→CHITCHAT flow.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement Smoke Test - Query Routing

**Files:**
- Create: `tests/smoke/test_smoke_routing.py`

**Step 1: Write the test**

```python
# tests/smoke/test_smoke_routing.py
"""Smoke tests for query routing."""

import pytest

from telegram_bot.services.query_router import QueryType, classify_query, get_chitchat_response
from tests.smoke.queries import ExpectedQueryType, SMOKE_QUERIES, get_queries_by_type


class TestSmokeRouting:
    """Test query routing for all 20 smoke queries."""

    def test_distribution_is_6_6_8(self):
        """Verify 6 CHITCHAT + 6 SIMPLE + 8 COMPLEX."""
        assert len(get_queries_by_type(ExpectedQueryType.CHITCHAT)) == 6
        assert len(get_queries_by_type(ExpectedQueryType.SIMPLE)) == 6
        assert len(get_queries_by_type(ExpectedQueryType.COMPLEX)) == 8
        assert len(SMOKE_QUERIES) == 20

    def test_chitchat_queries_classified_correctly(self):
        """All CHITCHAT queries should be classified as CHITCHAT."""
        for query in get_queries_by_type(ExpectedQueryType.CHITCHAT):
            result = classify_query(query.text)
            assert result == QueryType.CHITCHAT, f"'{query.text}' should be CHITCHAT, got {result}"

    def test_chitchat_queries_have_responses(self):
        """All CHITCHAT queries should have canned responses."""
        for query in get_queries_by_type(ExpectedQueryType.CHITCHAT):
            response = get_chitchat_response(query.text)
            assert response is not None, f"'{query.text}' should have a canned response"

    def test_simple_queries_not_chitchat(self):
        """SIMPLE queries should not be classified as CHITCHAT."""
        for query in get_queries_by_type(ExpectedQueryType.SIMPLE):
            result = classify_query(query.text)
            assert result != QueryType.CHITCHAT, f"'{query.text}' should not be CHITCHAT"

    def test_complex_queries_classified_as_complex(self):
        """COMPLEX queries should be classified as COMPLEX."""
        for query in get_queries_by_type(ExpectedQueryType.COMPLEX):
            result = classify_query(query.text)
            assert result == QueryType.COMPLEX, f"'{query.text}' should be COMPLEX, got {result}"

    def test_all_queries_routable(self):
        """All 20 queries should be routable without errors."""
        for query in SMOKE_QUERIES:
            result = classify_query(query.text)
            assert result in QueryType
```

**Step 2: Run test**

```bash
pytest tests/smoke/test_smoke_routing.py -v
```

Expected: PASS (6 tests)

**Step 3: Commit**

```bash
git add tests/smoke/test_smoke_routing.py
git commit -m "test(smoke): add query routing tests

Verifies 6/6/8 distribution and correct classification.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement Smoke Test - Cache Operations

**Files:**
- Create: `tests/smoke/test_smoke_cache.py`

**Step 1: Write the test**

```python
# tests/smoke/test_smoke_cache.py
"""Smoke tests for cache operations with live Redis."""

import os
import time

import pytest

from telegram_bot.services.cache import CacheService


@pytest.fixture(scope="module")
async def cache_service():
    """CacheService for testing."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    service = CacheService(redis_url=redis_url)
    await service.initialize()
    yield service
    if service.redis_client:
        keys = await service.redis_client.keys("rag:smoke_test:*")
        if keys:
            await service.redis_client.delete(*keys)
    await service.close()


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
class TestSmokeCache:
    """Test cache operations with live Redis."""

    @pytest.mark.asyncio
    async def test_redis_connection_healthy(self, cache_service):
        """Redis should be reachable."""
        pong = await cache_service.redis_client.ping()
        assert pong is True

    @pytest.mark.asyncio
    async def test_cache_write_and_read(self, cache_service):
        """Basic cache write/read should work."""
        key = f"rag:smoke_test:{int(time.time())}"
        await cache_service.redis_client.setex(key, 60, "test_value")
        result = await cache_service.redis_client.get(key)
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_rerank_cache_roundtrip(self, cache_service):
        """RerankCache should store and retrieve correctly."""
        query_hash = f"smoke_rerank_{int(time.time())}"
        chunk_ids = ["chunk1", "chunk2"]
        results = [{"id": "chunk1", "score": 0.95}]

        await cache_service.store_rerank_results(query_hash, chunk_ids, results)
        cached = await cache_service.get_cached_rerank(query_hash, chunk_ids)

        assert cached is not None
        assert cached[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_cache_metrics_exist(self, cache_service):
        """Cache metrics dict should exist."""
        assert "rerank" in cache_service.metrics
        assert "hits" in cache_service.metrics["rerank"]
```

**Step 2: Run test**

```bash
pytest tests/smoke/test_smoke_cache.py -v
```

Expected: PASS (4 tests) or SKIP

**Step 3: Commit**

```bash
git add tests/smoke/test_smoke_cache.py
git commit -m "test(smoke): add cache operation tests

Tests connection, write/read, RerankCache, metrics.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Implement Smoke Test - Quantization A/B (Fixed)

**Files:**
- Create: `tests/smoke/test_smoke_quantization.py`

**Step 1: Write the test (use p95 instead of hard threshold)**

```python
# tests/smoke/test_smoke_quantization.py
"""Smoke tests for Qdrant quantization A/B testing."""

import os
import time

import numpy as np
import pytest


@pytest.fixture(scope="module")
async def voyage_service():
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY not set")
    from telegram_bot.services.voyage import VoyageService
    return VoyageService(api_key=api_key)


@pytest.fixture(scope="module")
async def qdrant_service():
    from telegram_bot.services.qdrant import QdrantService
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY", "")
    collection = os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4")

    service = QdrantService(url=url, api_key=api_key or None, collection_name=collection)
    yield service
    await service.close()


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
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_without_quantization_returns_results(self, voyage_service, qdrant_service):
        """Search without quantization should return results."""
        embedding = await voyage_service.embed_query("квартира в Солнечном берегу")
        results = await qdrant_service.hybrid_search_rrf(
            dense_vector=embedding,
            quantization_ignore=True,
            top_k=5,
        )
        assert len(results) > 0

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
        """Measure latency with/without quantization (5 runs each, compare p95)."""
        embedding = await voyage_service.embed_query("апартаменты с бассейном")

        # Warmup
        await qdrant_service.hybrid_search_rrf(dense_vector=embedding, top_k=3)

        # Measure with quantization
        times_with = []
        for _ in range(5):
            start = time.time()
            await qdrant_service.hybrid_search_rrf(
                dense_vector=embedding, quantization_ignore=False, top_k=5
            )
            times_with.append((time.time() - start) * 1000)

        # Measure without quantization
        times_without = []
        for _ in range(5):
            start = time.time()
            await qdrant_service.hybrid_search_rrf(
                dense_vector=embedding, quantization_ignore=True, top_k=5
            )
            times_without.append((time.time() - start) * 1000)

        p95_with = np.percentile(times_with, 95)
        p95_without = np.percentile(times_without, 95)

        # Log results (informational)
        print(f"\nQuantization p95: {p95_with:.0f}ms (with) vs {p95_without:.0f}ms (without)")

        # Quantization should not be significantly slower (allow 50% margin)
        assert p95_with <= p95_without * 1.5, (
            f"Quantization too slow: {p95_with:.0f}ms vs {p95_without:.0f}ms"
        )
```

**Step 2: Run test**

```bash
pytest tests/smoke/test_smoke_quantization.py -v -s
```

Expected: PASS (4 tests) with latency comparison output

**Step 3: Commit**

```bash
git add tests/smoke/test_smoke_quantization.py
git commit -m "test(smoke): add quantization A/B tests (p95 comparison)

Uses 5 runs + p95 instead of hard-coded threshold.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Implement Load Test - Conversations

**Files:**
- Create: `tests/load/test_load_conversations.py`
- Create: `tests/load/baseline.json`

**Step 1: Write the test**

```python
# tests/load/test_load_conversations.py
"""Load tests for parallel chat conversations."""

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from tests.load.chat_simulator import run_parallel_chats
from tests.load.metrics_collector import (
    LoadMetrics,
    analyze_metrics,
    format_report,
    load_baseline,
    save_baseline,
)
from telegram_bot.services.query_router import classify_query, QueryType, get_chitchat_response


BASELINE_PATH = Path(__file__).parent / "baseline.json"
REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def use_mocks() -> bool:
    return os.getenv("LOAD_USE_MOCKS", "0") == "1"


@pytest.fixture
def load_config():
    return {
        "chat_count": int(os.getenv("LOAD_CHAT_COUNT", "10")),
        "duration_min": int(os.getenv("LOAD_DURATION_MIN", "2")),
        "use_mocks": use_mocks(),
    }


@pytest.fixture
async def services(load_config):
    if load_config["use_mocks"]:
        from unittest.mock import AsyncMock

        voyage = AsyncMock()
        voyage.embed_query = AsyncMock(return_value=[0.1] * 1024)

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=[
            {"id": "1", "score": 0.9, "text": "Mock", "metadata": {}},
        ])
        qdrant.close = AsyncMock()

        cache = AsyncMock()
        cache.get_cached_search_results = AsyncMock(return_value=None)
        cache.store_search_results = AsyncMock()
        cache.close = AsyncMock()

        yield {"voyage": voyage, "qdrant": qdrant, "cache": cache}
    else:
        from telegram_bot.services.voyage import VoyageService
        from telegram_bot.services.qdrant import QdrantService
        from telegram_bot.services.cache import CacheService

        voyage_key = os.getenv("VOYAGE_API_KEY")
        if not voyage_key:
            pytest.skip("VOYAGE_API_KEY not set")

        voyage = VoyageService(api_key=voyage_key)
        qdrant = QdrantService(
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
            collection_name=os.getenv("QDRANT_COLLECTION", "contextual_bulgaria_voyage4"),
        )
        cache = CacheService(redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"))
        await cache.initialize()

        yield {"voyage": voyage, "qdrant": qdrant, "cache": cache}

        await qdrant.close()
        await cache.close()


class TestLoadConversations:
    """Load tests for parallel chat conversations."""

    @pytest.mark.asyncio
    async def test_parallel_chats(self, load_config, services, request):
        """Run parallel chats and verify p95 thresholds."""
        metrics = LoadMetrics()
        chat_count = load_config["chat_count"]

        async def process_message(query: str, chat_id: int) -> float:
            start = time.time()

            # Routing
            route_start = time.time()
            query_type = classify_query(query)
            metrics.record_routing((time.time() - route_start) * 1000)

            if query_type == QueryType.CHITCHAT:
                _ = get_chitchat_response(query)
                latency = (time.time() - start) * 1000
                metrics.record_full_rag(latency)
                return latency

            try:
                cache_start = time.time()
                cached = await services["cache"].get_cached_search_results(
                    query_hash=str(hash(query))[:16],
                )

                if cached:
                    metrics.record_cache_hit((time.time() - cache_start) * 1000)
                    latency = (time.time() - start) * 1000
                    metrics.record_full_rag(latency)
                    return latency
                else:
                    metrics.record_cache_miss()

                embedding = await services["voyage"].embed_query(query)

                qdrant_start = time.time()
                results = await services["qdrant"].hybrid_search_rrf(
                    dense_vector=embedding, top_k=5
                )
                metrics.record_qdrant((time.time() - qdrant_start) * 1000)

                await services["cache"].store_search_results(
                    query_hash=str(hash(query))[:16], results=results
                )

            except Exception:
                metrics.record_error()
                raise

            latency = (time.time() - start) * 1000
            metrics.record_full_rag(latency)
            return latency

        start_time = time.time()
        await run_parallel_chats(
            chat_count=chat_count,
            process_message=process_message,
            stagger_start_sec=0.2,
        )
        duration = time.time() - start_time

        baseline = load_baseline(BASELINE_PATH)
        result = analyze_metrics(metrics, baseline, skip_ttft=True)

        report = format_report(result, metrics, duration, chat_count)
        print(f"\n{report}")

        # Save report
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / "load_summary.json"
        with open(report_path, "w") as f:
            json.dump({
                "routing_p95": result.routing_p95,
                "cache_hit_p95": result.cache_hit_p95,
                "qdrant_p95": result.qdrant_p95,
                "full_rag_p95": result.full_rag_p95,
                "cache_hit_rate": result.cache_hit_rate,
                "passed": result.passed,
                "chat_count": chat_count,
                "duration_sec": duration,
            }, f, indent=2)

        if request.config.getoption("--update-baseline", default=False):
            save_baseline(BASELINE_PATH, result)
            print(f"\nBaseline updated: {BASELINE_PATH}")

        assert result.passed, f"Load test failed: {result.failures}"


def pytest_addoption(parser):
    parser.addoption("--update-baseline", action="store_true", default=False)
```

**Step 2: Create baseline.json**

```json
{
  "routing": 15,
  "cache_hit": 15,
  "qdrant": 100,
  "full_rag": 2500,
  "ttft": 0,
  "timestamp": 1737619200
}
```

**Step 3: Run test (mocked)**

```bash
LOAD_USE_MOCKS=1 LOAD_CHAT_COUNT=5 pytest tests/load/test_load_conversations.py -v -s
```

Expected: PASS

**Step 4: Commit**

```bash
git add tests/load/test_load_conversations.py tests/load/baseline.json
git commit -m "test(load): add parallel chat load tests

Saves reports/load_summary.json. TTFT skipped (not streaming).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Implement Redis Eviction Test (Configurable)

**Files:**
- Create: `tests/load/test_load_redis_eviction.py`

**Step 1: Write the test with configurable volume**

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


@pytest.mark.skipif(not os.getenv("REDIS_URL"), reason="REDIS_URL not set")
class TestLoadRedisEviction:
    """Test Redis eviction behavior under load."""

    @pytest.fixture
    async def redis_client(self):
        client = redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
        yield client
        await client.close()

    @pytest.fixture
    def eviction_config(self):
        """Configurable eviction test parameters."""
        return {
            "total_mb": int(os.getenv("EVICTION_TEST_MB", "10")),
            "value_size_kb": 10,
            "sample_interval_sec": 2,
        }

    @pytest.mark.asyncio
    async def test_redis_lfu_policy_configured(self, redis_client):
        """Verify allkeys-lfu eviction policy."""
        policy = await redis_client.config_get("maxmemory-policy")
        assert policy.get("maxmemory-policy") == "allkeys-lfu"

    @pytest.mark.asyncio
    async def test_redis_maxmemory_set(self, redis_client):
        """Verify maxmemory is configured."""
        maxmem = await redis_client.config_get("maxmemory")
        assert int(maxmem.get("maxmemory", 0)) > 0

    @pytest.mark.asyncio
    async def test_eviction_under_pressure(self, redis_client, eviction_config):
        """Test eviction behavior under write pressure."""
        total_mb = eviction_config["total_mb"]
        value_size_kb = eviction_config["value_size_kb"]
        sample_interval = eviction_config["sample_interval_sec"]

        total_bytes = total_mb * 1024 * 1024
        value_size = value_size_kb * 1024
        num_keys = total_bytes // value_size

        test_prefix = f"rag:eviction_test:{int(time.time())}"
        stats_timeseries = []

        # Get initial stats
        info_start = await redis_client.info("stats")

        # Write keys and sample stats
        for i in range(num_keys):
            key = f"{test_prefix}:{i}"
            value = "x" * value_size
            await redis_client.setex(key, 300, value)

            if i % 100 == 0:
                info = await redis_client.info("stats")
                stats_timeseries.append({
                    "timestamp": time.time(),
                    "keys_written": i,
                    "evicted_keys": info.get("evicted_keys", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                })

        # Get final stats
        info_end = await redis_client.info("stats")
        evictions = info_end.get("evicted_keys", 0) - info_start.get("evicted_keys", 0)

        # Cleanup
        keys = await redis_client.keys(f"{test_prefix}:*")
        if keys:
            await redis_client.delete(*keys)

        # Save stats timeseries
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(REPORTS_DIR / "redis_stats_timeseries.json", "w") as f:
            json.dump(stats_timeseries, f, indent=2)

        print(f"\nWrote {num_keys} keys ({total_mb}MB), evictions: {evictions}")

    @pytest.mark.asyncio
    async def test_hit_rate_under_zipf_access(self, redis_client):
        """Test hit rate under Zipf-like access pattern."""
        test_prefix = f"rag:zipf_test:{int(time.time())}"

        # Populate 50 keys
        for i in range(50):
            await redis_client.setex(f"{test_prefix}:{i}", 60, f"value_{i}")

        # Zipf access (popular keys accessed more)
        hits = 0
        misses = 0

        for _ in range(200):
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

        hit_rate = hits / (hits + misses)
        print(f"\nZipf hit rate: {hit_rate:.0%}")

        assert hit_rate >= 0.5, f"Hit rate too low: {hit_rate:.0%}"
```

**Step 2: Run test**

```bash
pytest tests/load/test_load_redis_eviction.py -v -s
```

Expected: PASS (4 tests)

**Step 3: Commit**

```bash
git add tests/load/test_load_redis_eviction.py
git commit -m "test(load): add Redis eviction tests (configurable volume)

EVICTION_TEST_MB env for pressure test. Saves redis_stats_timeseries.json.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Add Makefile Commands

**Files:**
- Modify: `Makefile`

**Step 1: Add targets**

```makefile
# =============================================================================
# SMOKE & LOAD TESTS
# =============================================================================

test-preflight: ## Run preflight checks (Qdrant/Redis config)
	@echo "$(BLUE)Running preflight checks...$(NC)"
	pytest tests/smoke/test_preflight.py -v -s
	@echo "$(GREEN)✓ Preflight complete$(NC)"

test-smoke: ## Run smoke tests (requires live services)
	@echo "$(BLUE)Running smoke tests...$(NC)"
	pytest tests/smoke/ -v --tb=short
	@echo "$(GREEN)✓ Smoke tests complete$(NC)"

test-smoke-routing: ## Run smoke routing tests only (no deps)
	@echo "$(BLUE)Running smoke routing tests...$(NC)"
	pytest tests/smoke/test_smoke_routing.py -v
	@echo "$(GREEN)✓ Routing tests complete$(NC)"

test-load: ## Run load tests (live services)
	@echo "$(BLUE)Running load tests...$(NC)"
	pytest tests/load/test_load_conversations.py -v -s
	@echo "$(GREEN)✓ Load tests complete$(NC)"

test-load-ci: ## Run load tests in CI (mocked, fast)
	@echo "$(BLUE)Running load tests (CI mode)...$(NC)"
	LOAD_USE_MOCKS=1 LOAD_CHAT_COUNT=5 \
	pytest tests/load/test_load_conversations.py -v
	@echo "$(GREEN)✓ Load tests (CI) complete$(NC)"

test-load-eviction: ## Run Redis eviction tests
	@echo "$(BLUE)Running Redis eviction tests...$(NC)"
	pytest tests/load/test_load_redis_eviction.py -v -s
	@echo "$(GREEN)✓ Redis eviction tests complete$(NC)"

test-load-update-baseline: ## Update load test baseline
	@echo "$(BLUE)Updating baseline...$(NC)"
	pytest tests/load/test_load_conversations.py -v --update-baseline
	@echo "$(GREEN)✓ Baseline updated$(NC)"

test-all-smoke-load: test-preflight test-smoke test-load ## Full smoke+load suite
	@echo "$(GREEN)✓✓✓ All smoke+load tests complete$(NC)"
```

**Step 2: Verify**

```bash
make help | grep -E "(smoke|load|preflight)"
```

**Step 3: Commit**

```bash
git add Makefile
git commit -m "chore(make): add smoke/load/preflight targets

test-preflight, test-smoke, test-load, test-load-ci, test-all-smoke-load

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Final Verification

**Step 1: Run preflight**

```bash
make test-preflight
```

**Step 2: Run smoke routing (no deps)**

```bash
make test-smoke-routing
```

**Step 3: Run load CI**

```bash
make test-load-ci
```

**Step 4: Run unit tests**

```bash
pytest tests/unit/ -v --tb=short
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "test(smoke+load): complete implementation v2

- Preflight: Qdrant binary quant, Redis LFU verification
- Smoke: 20 queries (6/6/8), routing, cache, quantization A/B
- Load: parallel chats, p95 metrics, baseline regression
- Reports: preflight.json, load_summary.json, redis_stats_timeseries.json

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Key Fix |
|------|-------------|---------|
| 0 | Pre-flight checks | **NEW**: Qdrant/Redis config verification |
| 1 | Directory structure | **FIX**: Redis health check in conftest |
| 2 | Query definitions | **FIX**: Strict 6/6/8 distribution |
| 3 | Metrics collector | **FIX**: TTFT optional |
| 4 | Chat simulator | — |
| 5 | Smoke routing | — |
| 6 | Smoke cache | — |
| 7 | Smoke quantization | **FIX**: p95 comparison, not hard threshold |
| 8 | Load conversations | Saves load_summary.json |
| 9 | Redis eviction | **FIX**: Configurable EVICTION_TEST_MB |
| 10 | Makefile | Added test-preflight |
| 11 | Verification | — |

**Artifacts:**
- `reports/preflight.json`
- `reports/load_summary.json`
- `reports/redis_stats_timeseries.json`
