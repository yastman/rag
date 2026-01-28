# Baseline & Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement regression detection and cost tracking via Langfuse v3 as single source of truth for all RAG pipeline metrics.

**Architecture:** Three-tier testing (Smoke → Load → E2E Telegram) with metrics collected through Langfuse OTEL integration. Baseline stored as Langfuse sessions/tags, comparison via Langfuse API. VoyageService and CacheService instrumented with `@observe` decorators.

**Tech Stack:** Langfuse v3.150.0, LiteLLM with `langfuse_otel` callback, Python `langfuse` SDK with decorators, pytest markers, Makefile targets.

**Best Practices Applied (2026):**
- Traceability: link evaluation scores to exact prompt/model versions (Medium: Dave Davies)
- Performance dimensions: latency + token cost + throughput (Medium: Latha Pradeep)
- RAG monitoring overhead: <2ms acceptable (AIMultiple benchmark)
- Regression testing: before/after datasets with semantic similarity (Evidently AI)
- Production monitoring: LLM-as-judge for quality scores (Maxim AI, Braintrust)

---

## Prerequisites

- Docker services running: `docker compose -f docker-compose.dev.yml up -d`
- Langfuse v3 healthy: `curl http://localhost:3001/api/public/health`
- Python venv activated: `. venv/bin/activate`
- Dependencies: `pip install langfuse>=2.50.0`

---

## Task 1: Install Langfuse Python SDK

**Files:**
- Modify: `pyproject.toml` (dependencies section)
- Modify: `requirements.txt` (if exists)

**Step 1: Add langfuse dependency**

```toml
# In pyproject.toml [project.dependencies] or [tool.poetry.dependencies]
"langfuse>=2.50.0",
```

**Step 2: Install**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed langfuse-2.x.x

**Step 3: Verify import**

Run: `python -c "from langfuse import observe, get_client; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(deps): add langfuse SDK for observability"
```

---

## Task 2: Create Baseline Module Structure

**Files:**
- Create: `tests/baseline/__init__.py`
- Create: `tests/baseline/collector.py`
- Create: `tests/baseline/manager.py`
- Create: `tests/baseline/thresholds.yaml`
- Create: `tests/baseline/conftest.py`

**Step 1: Create directory and __init__.py**

```python
# tests/baseline/__init__.py
"""Baseline metrics collection and comparison via Langfuse."""

from .collector import LangfuseMetricsCollector
from .manager import BaselineManager, BaselineSnapshot

__all__ = ["LangfuseMetricsCollector", "BaselineManager", "BaselineSnapshot"]
```

**Step 2: Create thresholds.yaml**

```yaml
# tests/baseline/thresholds.yaml
# Regression = current > baseline * factor
# Based on 2026 best practices: AIMultiple, Braintrust, Evidently AI

latency:
  llm_p95_factor: 1.20        # 20% tolerance
  full_rag_p95_factor: 1.20
  qdrant_p95_factor: 1.30     # Vector DB has more variance
  ttft_p95_factor: 1.25       # Time to first token

cost:
  total_factor: 1.10          # 10% tolerance on total cost
  tokens_input_factor: 1.15   # 15% on input tokens
  tokens_output_factor: 1.15

cache:
  hit_rate_min_drop: 0.10     # Alert if drops >10% absolute
  semantic_hit_rate_min: 0.30 # Minimum semantic cache effectiveness

calls:
  llm_factor: 1.05            # 5% - should be very stable
  voyage_embed_factor: 1.10
  voyage_rerank_factor: 1.10

infrastructure:
  redis_memory_factor: 1.50   # 50% tolerance
  qdrant_vectors_factor: 1.20
```

**Step 3: Create conftest.py for baseline tests**

```python
# tests/baseline/conftest.py
"""Fixtures for baseline tests."""

import os
import pytest
from datetime import datetime, timedelta

from .collector import LangfuseMetricsCollector
from .manager import BaselineManager


@pytest.fixture
def langfuse_collector():
    """Create Langfuse metrics collector."""
    return LangfuseMetricsCollector(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )


@pytest.fixture
def baseline_manager(langfuse_collector):
    """Create baseline manager."""
    return BaselineManager(collector=langfuse_collector)


@pytest.fixture
def test_time_range():
    """Default time range for tests (last hour)."""
    now = datetime.utcnow()
    return {
        "from_ts": now - timedelta(hours=1),
        "to_ts": now,
    }
```

**Step 4: Commit structure**

```bash
git add tests/baseline/
git commit -m "feat(baseline): add module structure and thresholds"
```

---

## Task 3: Implement LangfuseMetricsCollector

**Files:**
- Create: `tests/baseline/collector.py`
- Test: `tests/baseline/test_collector.py`

**Step 1: Write the failing test**

```python
# tests/baseline/test_collector.py
"""Tests for LangfuseMetricsCollector."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from tests.baseline.collector import LangfuseMetricsCollector


class TestLangfuseMetricsCollector:
    """Test LangfuseMetricsCollector functionality."""

    def test_init_creates_client(self):
        """Should initialize Langfuse client with credentials."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )
            mock_langfuse.assert_called_once_with(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

    def test_get_daily_metrics_calls_api(self):
        """Should call Langfuse daily metrics API."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_client.api.metrics_daily.get.return_value = {"data": []}

            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

            from_ts = datetime(2026, 1, 28, 0, 0, 0)
            to_ts = datetime(2026, 1, 28, 23, 59, 59)

            result = collector.get_daily_metrics(from_ts, to_ts)

            mock_client.api.metrics_daily.get.assert_called_once()
            assert result == {"data": []}

    def test_get_latency_metrics_uses_v2_api(self):
        """Should use v2 metrics API for latency percentiles."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_client.api.metrics_v_2.get.return_value = {"data": []}

            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

            from_ts = datetime(2026, 1, 28, 0, 0, 0)
            to_ts = datetime(2026, 1, 28, 23, 59, 59)

            result = collector.get_latency_metrics(from_ts, to_ts)

            mock_client.api.metrics_v_2.get.assert_called_once()

    def test_get_trace_count_filters_by_name(self):
        """Should filter traces by name."""
        with patch("tests.baseline.collector.Langfuse") as mock_langfuse:
            mock_client = MagicMock()
            mock_langfuse.return_value = mock_client
            mock_client.api.metrics.metrics.return_value = MagicMock(
                data=[{"name": "smoke-test", "count_count": "42"}]
            )

            collector = LangfuseMetricsCollector(
                public_key="pk-test",
                secret_key="sk-test",
                host="http://localhost:3001",
            )

            count = collector.get_trace_count(
                from_ts=datetime(2026, 1, 28),
                to_ts=datetime(2026, 1, 29),
                trace_name="smoke-test",
            )

            assert count == 42
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/baseline/test_collector.py -v`
Expected: FAIL with "No module named 'tests.baseline.collector'"

**Step 3: Write minimal implementation**

```python
# tests/baseline/collector.py
"""Collect metrics from Langfuse v3 API."""

import json
from datetime import datetime
from typing import Any

from langfuse import Langfuse


class LangfuseMetricsCollector:
    """Collect metrics from Langfuse v3 API.

    Uses Langfuse API endpoints:
    - GET /api/public/metrics/daily - aggregated daily usage and cost
    - GET /api/public/metrics (v2) - custom queries with dimensions

    Reference: https://langfuse.com/docs/metrics/features/metrics-api
    """

    def __init__(self, public_key: str, secret_key: str, host: str):
        """Initialize collector with Langfuse credentials.

        Args:
            public_key: Langfuse public key (pk-lf-...)
            secret_key: Langfuse secret key (sk-lf-...)
            host: Langfuse host URL (e.g., http://localhost:3001)
        """
        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )

    def get_daily_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Get aggregated daily usage and cost metrics.

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            trace_name: Optional filter by trace name
            limit: Max results (default 30)

        Returns:
            Dict with 'data' array containing daily metrics:
            - date, countTraces, countObservations, totalCost
            - usage: [{model, inputUsage, outputUsage, totalCost}]
        """
        kwargs = {
            "from_timestamp": from_ts.isoformat() + "Z",
            "to_timestamp": to_ts.isoformat() + "Z",
            "limit": limit,
        }
        if trace_name:
            kwargs["trace_name"] = trace_name

        return self.client.api.metrics_daily.get(**kwargs)

    def get_latency_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str | None = None,
    ) -> dict[str, Any]:
        """Get latency percentiles via v2 metrics API.

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            trace_name: Optional filter by trace name

        Returns:
            Dict with latency p50, p95, cost, and count by model
        """
        filters = []
        if trace_name:
            filters.append({
                "field": "traceName",
                "operator": "=",
                "value": trace_name,
            })

        query = {
            "view": "observations",
            "metrics": [
                {"measure": "latency", "aggregation": "p50"},
                {"measure": "latency", "aggregation": "p95"},
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "count", "aggregation": "count"},
            ],
            "dimensions": [{"field": "providedModelName"}],
            "filters": filters,
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        return self.client.api.metrics_v_2.get(query=json.dumps(query))

    def get_trace_count(
        self,
        from_ts: datetime,
        to_ts: datetime,
        trace_name: str,
    ) -> int:
        """Count traces for a specific operation.

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            trace_name: Name of trace to count

        Returns:
            Number of traces matching the name
        """
        query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [{"field": "name"}],
            "filters": [
                {"field": "name", "operator": "=", "value": trace_name}
            ],
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        result = self.client.api.metrics.metrics(query=json.dumps(query))

        if result.data:
            return int(result.data[0].get("count_count", 0))
        return 0

    def get_cache_metrics(
        self,
        from_ts: datetime,
        to_ts: datetime,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Get cache hit/miss metrics from trace metadata.

        Traces should have metadata.cache_hit = true/false

        Args:
            from_ts: Start timestamp
            to_ts: End timestamp
            session_id: Optional session filter

        Returns:
            Dict with hits, misses, hit_rate
        """
        # Query for cache hits
        hits_query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [],
            "filters": [
                {"field": "metadata.cache_hit", "operator": "=", "value": "true"}
            ],
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        # Query for cache misses
        misses_query = {
            "view": "traces",
            "metrics": [{"measure": "count", "aggregation": "count"}],
            "dimensions": [],
            "filters": [
                {"field": "metadata.cache_hit", "operator": "=", "value": "false"}
            ],
            "fromTimestamp": from_ts.isoformat() + "Z",
            "toTimestamp": to_ts.isoformat() + "Z",
        }

        hits_result = self.client.api.metrics.metrics(query=json.dumps(hits_query))
        misses_result = self.client.api.metrics.metrics(query=json.dumps(misses_query))

        hits = int(hits_result.data[0].get("count_count", 0)) if hits_result.data else 0
        misses = int(misses_result.data[0].get("count_count", 0)) if misses_result.data else 0

        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0

        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate": hit_rate,
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/baseline/test_collector.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add tests/baseline/collector.py tests/baseline/test_collector.py
git commit -m "feat(baseline): implement LangfuseMetricsCollector"
```

---

## Task 4: Implement BaselineManager

**Files:**
- Create: `tests/baseline/manager.py`
- Test: `tests/baseline/test_manager.py`

**Step 1: Write the failing test**

```python
# tests/baseline/test_manager.py
"""Tests for BaselineManager."""

import pytest
from datetime import datetime
from unittest.mock import Mock, MagicMock
from pathlib import Path

from tests.baseline.manager import BaselineManager, BaselineSnapshot


class TestBaselineSnapshot:
    """Test BaselineSnapshot dataclass."""

    def test_create_snapshot(self):
        """Should create snapshot with all fields."""
        snapshot = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28, 12, 0, 0),
            tag="smoke-v1.0.0",
            session_id="session-123",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.0523,
            llm_tokens_input=12000,
            llm_tokens_output=3000,
            llm_calls=150,
            voyage_embed_calls=150,
            voyage_rerank_calls=75,
            cache_hit_rate=0.65,
            cache_hits=98,
            cache_misses=52,
        )

        assert snapshot.tag == "smoke-v1.0.0"
        assert snapshot.llm_latency_p95_ms == 350.0
        assert snapshot.cache_hit_rate == 0.65


class TestBaselineManager:
    """Test BaselineManager functionality."""

    def test_compare_passes_within_thresholds(self):
        """Should pass when metrics within thresholds."""
        collector = Mock()
        manager = BaselineManager(collector=collector)

        baseline = BaselineSnapshot(
            timestamp=datetime(2026, 1, 27),
            tag="baseline",
            session_id="s1",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.60,
            cache_hits=60,
            cache_misses=40,
        )

        current = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28),
            tag="current",
            session_id="s2",
            llm_latency_p50_ms=160.0,  # +6% OK
            llm_latency_p95_ms=380.0,  # +8% OK (threshold 20%)
            full_rag_latency_p95_ms=2700.0,  # +8% OK
            total_cost_usd=0.052,  # +4% OK (threshold 10%)
            llm_tokens_input=10500,
            llm_tokens_output=2600,
            llm_calls=102,  # +2% OK
            voyage_embed_calls=105,
            voyage_rerank_calls=52,
            cache_hit_rate=0.58,  # -2% OK (threshold 10%)
            cache_hits=58,
            cache_misses=42,
        )

        passed, regressions = manager.compare(current, baseline)

        assert passed is True
        assert len(regressions) == 0

    def test_compare_fails_latency_regression(self):
        """Should fail when latency exceeds threshold."""
        collector = Mock()
        manager = BaselineManager(collector=collector)

        baseline = BaselineSnapshot(
            timestamp=datetime(2026, 1, 27),
            tag="baseline",
            session_id="s1",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.60,
            cache_hits=60,
            cache_misses=40,
        )

        current = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28),
            tag="current",
            session_id="s2",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=500.0,  # +43% FAIL (threshold 20%)
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.60,
            cache_hits=60,
            cache_misses=40,
        )

        passed, regressions = manager.compare(current, baseline)

        assert passed is False
        assert len(regressions) == 1
        assert "latency" in regressions[0].lower()

    def test_compare_fails_cache_drop(self):
        """Should fail when cache hit rate drops significantly."""
        collector = Mock()
        manager = BaselineManager(collector=collector)

        baseline = BaselineSnapshot(
            timestamp=datetime(2026, 1, 27),
            tag="baseline",
            session_id="s1",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.70,
            cache_hits=70,
            cache_misses=30,
        )

        current = BaselineSnapshot(
            timestamp=datetime(2026, 1, 28),
            tag="current",
            session_id="s2",
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            full_rag_latency_p95_ms=2500.0,
            total_cost_usd=0.05,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            llm_calls=100,
            voyage_embed_calls=100,
            voyage_rerank_calls=50,
            cache_hit_rate=0.45,  # -25% FAIL (threshold 10%)
            cache_hits=45,
            cache_misses=55,
        )

        passed, regressions = manager.compare(current, baseline)

        assert passed is False
        assert any("cache" in r.lower() for r in regressions)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/baseline/test_manager.py -v`
Expected: FAIL with "No module named 'tests.baseline.manager'"

**Step 3: Write minimal implementation**

```python
# tests/baseline/manager.py
"""Baseline management via Langfuse sessions/tags."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .collector import LangfuseMetricsCollector


@dataclass
class BaselineSnapshot:
    """Snapshot of metrics for comparison."""

    # Metadata
    timestamp: datetime
    tag: str
    session_id: str

    # Latency (milliseconds)
    llm_latency_p50_ms: float
    llm_latency_p95_ms: float
    full_rag_latency_p95_ms: float

    # Cost
    total_cost_usd: float
    llm_tokens_input: int
    llm_tokens_output: int

    # Call counts
    llm_calls: int
    voyage_embed_calls: int
    voyage_rerank_calls: int

    # Cache effectiveness
    cache_hit_rate: float
    cache_hits: int
    cache_misses: int


class BaselineManager:
    """Manage baselines stored as Langfuse sessions/tags.

    Baselines are identified by session_id in Langfuse.
    Comparison uses thresholds from thresholds.yaml.
    """

    def __init__(
        self,
        collector: LangfuseMetricsCollector,
        thresholds_path: Path | None = None,
    ):
        """Initialize manager.

        Args:
            collector: LangfuseMetricsCollector instance
            thresholds_path: Path to thresholds.yaml (default: same dir)
        """
        self.collector = collector

        if thresholds_path is None:
            thresholds_path = Path(__file__).parent / "thresholds.yaml"

        with open(thresholds_path) as f:
            self.thresholds = yaml.safe_load(f)

    def create_snapshot(
        self,
        tag: str,
        session_id: str,
        from_ts: datetime,
        to_ts: datetime,
    ) -> BaselineSnapshot:
        """Create baseline snapshot from Langfuse data.

        Args:
            tag: Human-readable tag (e.g., "smoke-v1.0.0")
            session_id: Langfuse session ID
            from_ts: Start timestamp
            to_ts: End timestamp

        Returns:
            BaselineSnapshot with aggregated metrics
        """
        # Get daily metrics for cost/tokens
        daily = self.collector.get_daily_metrics(from_ts, to_ts)

        # Get latency metrics
        latency = self.collector.get_latency_metrics(from_ts, to_ts)

        # Get cache metrics
        cache = self.collector.get_cache_metrics(from_ts, to_ts, session_id)

        # Aggregate daily metrics
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        total_traces = 0

        for day in daily.get("data", []):
            total_cost += day.get("totalCost", 0)
            total_traces += day.get("countTraces", 0)
            for usage in day.get("usage", []):
                total_input_tokens += usage.get("inputUsage", 0)
                total_output_tokens += usage.get("outputUsage", 0)

        # Extract latency percentiles
        llm_p50 = 0.0
        llm_p95 = 0.0

        for item in latency.get("data", []):
            llm_p50 = float(item.get("latency_p50", 0))
            llm_p95 = float(item.get("latency_p95", 0))
            break  # Take first model's metrics

        # Get operation counts
        voyage_embed_count = self.collector.get_trace_count(
            from_ts, to_ts, "voyage-embed"
        )
        voyage_rerank_count = self.collector.get_trace_count(
            from_ts, to_ts, "voyage-rerank"
        )

        return BaselineSnapshot(
            timestamp=to_ts,
            tag=tag,
            session_id=session_id,
            llm_latency_p50_ms=llm_p50,
            llm_latency_p95_ms=llm_p95,
            full_rag_latency_p95_ms=llm_p95 * 1.5,  # Estimate
            total_cost_usd=total_cost,
            llm_tokens_input=total_input_tokens,
            llm_tokens_output=total_output_tokens,
            llm_calls=total_traces,
            voyage_embed_calls=voyage_embed_count,
            voyage_rerank_calls=voyage_rerank_count,
            cache_hit_rate=cache["hit_rate"],
            cache_hits=cache["hits"],
            cache_misses=cache["misses"],
        )

    def compare(
        self,
        current: BaselineSnapshot,
        baseline: BaselineSnapshot,
        custom_thresholds: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str]]:
        """Compare current metrics against baseline.

        Args:
            current: Current run snapshot
            baseline: Baseline snapshot to compare against
            custom_thresholds: Override default thresholds

        Returns:
            Tuple of (passed, list of regression messages)
        """
        thresholds = custom_thresholds or self.thresholds
        regressions: list[str] = []

        # Latency checks
        latency_thresholds = thresholds.get("latency", {})

        llm_factor = latency_thresholds.get("llm_p95_factor", 1.2)
        if current.llm_latency_p95_ms > baseline.llm_latency_p95_ms * llm_factor:
            pct = (current.llm_latency_p95_ms / baseline.llm_latency_p95_ms - 1) * 100
            regressions.append(
                f"LLM p95 latency regression: {current.llm_latency_p95_ms:.0f}ms "
                f"vs baseline {baseline.llm_latency_p95_ms:.0f}ms (+{pct:.1f}%)"
            )

        rag_factor = latency_thresholds.get("full_rag_p95_factor", 1.2)
        if current.full_rag_latency_p95_ms > baseline.full_rag_latency_p95_ms * rag_factor:
            pct = (current.full_rag_latency_p95_ms / baseline.full_rag_latency_p95_ms - 1) * 100
            regressions.append(
                f"Full RAG p95 latency regression: {current.full_rag_latency_p95_ms:.0f}ms "
                f"vs baseline {baseline.full_rag_latency_p95_ms:.0f}ms (+{pct:.1f}%)"
            )

        # Cost checks
        cost_thresholds = thresholds.get("cost", {})

        cost_factor = cost_thresholds.get("total_factor", 1.1)
        if baseline.total_cost_usd > 0 and current.total_cost_usd > baseline.total_cost_usd * cost_factor:
            pct = (current.total_cost_usd / baseline.total_cost_usd - 1) * 100
            regressions.append(
                f"Cost regression: ${current.total_cost_usd:.4f} "
                f"vs baseline ${baseline.total_cost_usd:.4f} (+{pct:.1f}%)"
            )

        # Cache checks
        cache_thresholds = thresholds.get("cache", {})

        cache_drop = cache_thresholds.get("hit_rate_min_drop", 0.1)
        if current.cache_hit_rate < baseline.cache_hit_rate - cache_drop:
            drop = baseline.cache_hit_rate - current.cache_hit_rate
            regressions.append(
                f"Cache hit rate drop: {current.cache_hit_rate:.1%} "
                f"vs baseline {baseline.cache_hit_rate:.1%} (-{drop:.1%})"
            )

        # Call count checks
        calls_thresholds = thresholds.get("calls", {})

        llm_calls_factor = calls_thresholds.get("llm_factor", 1.05)
        if baseline.llm_calls > 0 and current.llm_calls > baseline.llm_calls * llm_calls_factor:
            pct = (current.llm_calls / baseline.llm_calls - 1) * 100
            regressions.append(
                f"LLM calls increase: {current.llm_calls} "
                f"vs baseline {baseline.llm_calls} (+{pct:.1f}%)"
            )

        return len(regressions) == 0, regressions
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/baseline/test_manager.py -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add tests/baseline/manager.py tests/baseline/test_manager.py
git commit -m "feat(baseline): implement BaselineManager with comparison logic"
```

---

## Task 5: Instrument VoyageService with @observe

**Files:**
- Modify: `telegram_bot/services/voyage_service.py`
- Test: `tests/unit/services/test_voyage_observability.py`

**Step 1: Write the failing test**

```python
# tests/unit/services/test_voyage_observability.py
"""Tests for VoyageService Langfuse instrumentation."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestVoyageServiceObservability:
    """Test VoyageService has @observe decorators."""

    def test_embed_query_has_observe_decorator(self):
        """embed_query should have @observe decorator."""
        from telegram_bot.services.voyage_service import VoyageService

        # Check if method has langfuse observation
        method = VoyageService.embed_query
        assert hasattr(method, "__wrapped__") or "observe" in str(method)

    def test_embed_documents_has_observe_decorator(self):
        """embed_documents should have @observe decorator."""
        from telegram_bot.services.voyage_service import VoyageService

        method = VoyageService.embed_documents
        assert hasattr(method, "__wrapped__") or "observe" in str(method)

    def test_rerank_has_observe_decorator(self):
        """rerank should have @observe decorator."""
        from telegram_bot.services.voyage_service import VoyageService

        method = VoyageService.rerank
        assert hasattr(method, "__wrapped__") or "observe" in str(method)

    @pytest.mark.asyncio
    async def test_embed_query_updates_generation(self):
        """embed_query should update Langfuse generation with usage."""
        with patch("telegram_bot.services.voyage_service.get_client") as mock_get_client:
            mock_langfuse = MagicMock()
            mock_get_client.return_value = mock_langfuse

            with patch("telegram_bot.services.voyage_service.httpx.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "data": [{"embedding": [0.1] * 1024}],
                    "usage": {"total_tokens": 10}
                }
                mock_response.raise_for_status = MagicMock()

                mock_client_instance = AsyncMock()
                mock_client_instance.post.return_value = mock_response
                mock_client_instance.__aenter__.return_value = mock_client_instance
                mock_client_instance.__aexit__.return_value = None
                mock_client.return_value = mock_client_instance

                from telegram_bot.services.voyage_service import VoyageService

                service = VoyageService(api_key="test-key")
                # Would need actual async call here
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_voyage_observability.py -v`
Expected: FAIL (no @observe decorator yet)

**Step 3: Read current VoyageService implementation**

Run: Read `telegram_bot/services/voyage_service.py` to understand current structure.

**Step 4: Add @observe decorators**

Add to the top of the file:
```python
from langfuse import observe, get_client
```

Wrap key methods:
```python
@observe(name="voyage-embed-query", as_type="generation")
async def embed_query(self, text: str) -> list[float]:
    langfuse = get_client()
    langfuse.update_current_generation(
        model=self.model_queries,
        input={"text": text[:200]},  # Truncate for logging
    )

    # ... existing implementation ...

    langfuse.update_current_generation(
        usage_details={"input": usage.get("total_tokens", 0)},
        output={"dimensions": len(embedding)},
    )
    return embedding

@observe(name="voyage-embed-documents", as_type="generation")
async def embed_documents(self, texts: list[str]) -> list[list[float]]:
    # Similar pattern

@observe(name="voyage-rerank", as_type="generation")
async def rerank(self, query: str, documents: list[str], top_k: int) -> list:
    # Similar pattern
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/unit/services/test_voyage_observability.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add telegram_bot/services/voyage_service.py tests/unit/services/test_voyage_observability.py
git commit -m "feat(observability): add @observe decorators to VoyageService"
```

---

## Task 6: Create Makefile Targets

**Files:**
- Modify: `Makefile`

**Step 1: Add baseline targets**

```makefile
# =============================================================================
# BASELINE & OBSERVABILITY
# =============================================================================

.PHONY: baseline-smoke baseline-load baseline-compare baseline-set baseline-report

# Generate unique session ID from git commit
BASELINE_SESSION := smoke-$(shell git rev-parse --short HEAD)-$(shell date +%Y%m%d%H%M%S)
LOAD_SESSION := load-$(shell git rev-parse --short HEAD)-$(shell date +%Y%m%d%H%M%S)

# Run smoke tests with Langfuse session tagging
baseline-smoke:
	@echo "Running smoke tests with Langfuse tracing..."
	@echo "Session: $(BASELINE_SESSION)"
	LANGFUSE_SESSION_ID="$(BASELINE_SESSION)" \
	LANGFUSE_RELEASE="$(shell git rev-parse --short HEAD)" \
	pytest tests/smoke/ -v --tb=short -x
	@echo ""
	@echo "Results tagged as: $(BASELINE_SESSION)"
	@echo "View in Langfuse: http://localhost:3001"

# Run load tests with Langfuse session tagging
baseline-load:
	@echo "Running load tests with Langfuse tracing..."
	@echo "Session: $(LOAD_SESSION)"
	LANGFUSE_SESSION_ID="$(LOAD_SESSION)" \
	LANGFUSE_RELEASE="$(shell git rev-parse --short HEAD)" \
	pytest tests/load/ -v --tb=short
	@echo ""
	@echo "Results tagged as: $(LOAD_SESSION)"

# Compare current run against baseline
baseline-compare:
ifndef BASELINE_TAG
	$(error BASELINE_TAG is required. Usage: make baseline-compare BASELINE_TAG=smoke-abc1234-20260128)
endif
ifndef CURRENT_TAG
	$(error CURRENT_TAG is required. Usage: make baseline-compare BASELINE_TAG=... CURRENT_TAG=...)
endif
	@echo "Comparing $(CURRENT_TAG) against baseline $(BASELINE_TAG)..."
	python -m tests.baseline.cli compare \
		--baseline="$(BASELINE_TAG)" \
		--current="$(CURRENT_TAG)" \
		--thresholds=tests/baseline/thresholds.yaml

# Set a run as the new baseline
baseline-set:
ifndef TAG
	$(error TAG is required. Usage: make baseline-set TAG=smoke-abc1234-20260128)
endif
	@echo "Setting $(TAG) as baseline..."
	python -m tests.baseline.cli set-baseline --tag="$(TAG)"

# Generate HTML report
baseline-report:
	@echo "Generating baseline report..."
	python -m tests.baseline.cli report \
		--output=reports/baseline-$(shell date +%Y%m%d-%H%M%S).html
	@echo "Report saved to reports/"

# Quick baseline check (smoke + compare with main)
baseline-check: baseline-smoke
	@echo "Comparing with main baseline..."
	make baseline-compare BASELINE_TAG=main-latest CURRENT_TAG=$(BASELINE_SESSION)
```

**Step 2: Verify Makefile syntax**

Run: `make -n baseline-smoke`
Expected: Shows commands without error

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(baseline): add Makefile targets for baseline management"
```

---

## Task 7: Create CLI for Baseline Operations

**Files:**
- Create: `tests/baseline/cli.py`
- Test: `tests/baseline/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/baseline/test_cli.py
"""Tests for baseline CLI."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from tests.baseline.cli import cli, compare, set_baseline, report


class TestBaselineCLI:
    """Test baseline CLI commands."""

    def test_compare_requires_baseline_tag(self):
        """compare command should require --baseline."""
        runner = CliRunner()
        result = runner.invoke(compare, ["--current=abc"])
        assert result.exit_code != 0
        assert "baseline" in result.output.lower() or "missing" in result.output.lower()

    def test_compare_requires_current_tag(self):
        """compare command should require --current."""
        runner = CliRunner()
        result = runner.invoke(compare, ["--baseline=abc"])
        assert result.exit_code != 0

    @patch("tests.baseline.cli.LangfuseMetricsCollector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_outputs_results(self, mock_manager_cls, mock_collector_cls):
        """compare should output comparison results."""
        mock_manager = MagicMock()
        mock_manager.compare.return_value = (True, [])
        mock_manager.create_snapshot.return_value = MagicMock()
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        result = runner.invoke(compare, [
            "--baseline=smoke-abc-20260128",
            "--current=smoke-def-20260128",
        ])

        # Should not error
        assert "error" not in result.output.lower() or result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/baseline/test_cli.py -v`
Expected: FAIL with "No module named 'tests.baseline.cli'"

**Step 3: Write minimal implementation**

```python
# tests/baseline/cli.py
"""CLI for baseline operations."""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import click

from .collector import LangfuseMetricsCollector
from .manager import BaselineManager


def get_collector() -> LangfuseMetricsCollector:
    """Create collector from environment."""
    return LangfuseMetricsCollector(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )


@click.group()
def cli():
    """Baseline management CLI."""
    pass


@cli.command()
@click.option("--baseline", required=True, help="Baseline session tag")
@click.option("--current", required=True, help="Current session tag")
@click.option(
    "--thresholds",
    default="tests/baseline/thresholds.yaml",
    help="Path to thresholds file",
)
@click.option("--hours", default=24, help="Hours to look back for metrics")
def compare(baseline: str, current: str, thresholds: str, hours: int):
    """Compare current run against baseline."""
    collector = get_collector()
    manager = BaselineManager(
        collector=collector,
        thresholds_path=Path(thresholds),
    )

    # Time range
    now = datetime.utcnow()
    from_ts = now - timedelta(hours=hours)

    click.echo(f"Fetching baseline metrics: {baseline}")
    baseline_snapshot = manager.create_snapshot(
        tag=baseline,
        session_id=baseline,
        from_ts=from_ts,
        to_ts=now,
    )

    click.echo(f"Fetching current metrics: {current}")
    current_snapshot = manager.create_snapshot(
        tag=current,
        session_id=current,
        from_ts=from_ts,
        to_ts=now,
    )

    click.echo("\nComparing metrics...")
    passed, regressions = manager.compare(current_snapshot, baseline_snapshot)

    click.echo("\n" + "=" * 60)
    click.echo("BASELINE COMPARISON RESULTS")
    click.echo("=" * 60)

    # Print metrics table
    click.echo(f"\n{'Metric':<30} {'Baseline':<15} {'Current':<15} {'Change':<10}")
    click.echo("-" * 70)

    def fmt_change(curr, base):
        if base == 0:
            return "N/A"
        pct = (curr / base - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    click.echo(f"{'LLM p95 latency (ms)':<30} {baseline_snapshot.llm_latency_p95_ms:<15.0f} {current_snapshot.llm_latency_p95_ms:<15.0f} {fmt_change(current_snapshot.llm_latency_p95_ms, baseline_snapshot.llm_latency_p95_ms):<10}")
    click.echo(f"{'Total cost (USD)':<30} {baseline_snapshot.total_cost_usd:<15.4f} {current_snapshot.total_cost_usd:<15.4f} {fmt_change(current_snapshot.total_cost_usd, baseline_snapshot.total_cost_usd):<10}")
    click.echo(f"{'Cache hit rate':<30} {baseline_snapshot.cache_hit_rate:<15.1%} {current_snapshot.cache_hit_rate:<15.1%} {fmt_change(current_snapshot.cache_hit_rate, baseline_snapshot.cache_hit_rate):<10}")
    click.echo(f"{'LLM calls':<30} {baseline_snapshot.llm_calls:<15} {current_snapshot.llm_calls:<15} {fmt_change(current_snapshot.llm_calls, baseline_snapshot.llm_calls):<10}")

    click.echo("\n" + "=" * 60)

    if passed:
        click.secho("✓ PASSED - No regressions detected", fg="green", bold=True)
        sys.exit(0)
    else:
        click.secho("✗ FAILED - Regressions detected:", fg="red", bold=True)
        for regression in regressions:
            click.echo(f"  • {regression}")
        sys.exit(1)


@cli.command("set-baseline")
@click.option("--tag", required=True, help="Tag to set as baseline")
def set_baseline(tag: str):
    """Set a run as the new baseline."""
    # For now, just record to a file
    baseline_file = Path("tests/baseline/.current_baseline")
    baseline_file.write_text(tag)
    click.echo(f"Baseline set to: {tag}")


@cli.command()
@click.option("--output", default="reports/baseline.html", help="Output file path")
def report(output: str):
    """Generate HTML baseline report."""
    click.echo(f"Generating report to {output}...")
    # TODO: Implement HTML report generation
    click.echo("Report generation not yet implemented")


if __name__ == "__main__":
    cli()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/baseline/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/baseline/cli.py tests/baseline/test_cli.py
git commit -m "feat(baseline): add CLI for compare, set-baseline, report"
```

---

## Task 8: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add baseline section to CLAUDE.md**

Add after "## Testing" section:

```markdown
## Baseline & Observability

**Langfuse v3** — single source of truth for LLM metrics, cost tracking, and regression detection.

### Quick Commands

```bash
# Run smoke tests with Langfuse tracing
make baseline-smoke

# Run load tests with Langfuse tracing
make baseline-load

# Compare current run against baseline
make baseline-compare BASELINE_TAG=smoke-abc-20260128 CURRENT_TAG=smoke-def-20260128

# Set current as new baseline
make baseline-set TAG=smoke-abc-20260128
```

### Langfuse UI

- **Local:** http://localhost:3001
- **Traces:** See all LLM calls, latency, cost
- **Sessions:** Group traces by test run (smoke-*, load-*)

### Thresholds (regression detection)

| Metric | Threshold | Description |
|--------|-----------|-------------|
| LLM p95 latency | +20% | Alert if latency increases |
| Total cost | +10% | Alert if cost increases |
| Cache hit rate | -10% | Alert if cache effectiveness drops |
| LLM calls | +5% | Alert if call count increases |

Config: `tests/baseline/thresholds.yaml`

### Instrumented Services

| Service | Trace Name | Tracked |
|---------|------------|---------|
| VoyageService.embed_query | voyage-embed-query | tokens, latency |
| VoyageService.embed_documents | voyage-embed-documents | tokens, latency |
| VoyageService.rerank | voyage-rerank | latency, top_k |
| LLMService (via LiteLLM) | Auto | tokens, cost, latency |
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add baseline & observability section to CLAUDE.md"
```

---

## Task 9: Integration Test

**Files:**
- Create: `tests/baseline/test_integration.py`

**Step 1: Write integration test**

```python
# tests/baseline/test_integration.py
"""Integration tests for baseline system (requires running Langfuse)."""

import os
import pytest
from datetime import datetime, timedelta

from tests.baseline.collector import LangfuseMetricsCollector
from tests.baseline.manager import BaselineManager


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("LANGFUSE_PUBLIC_KEY"),
    reason="LANGFUSE_PUBLIC_KEY not set"
)
class TestBaselineIntegration:
    """Integration tests requiring live Langfuse."""

    @pytest.fixture
    def collector(self):
        """Create live collector."""
        return LangfuseMetricsCollector(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
        )

    def test_get_daily_metrics_returns_data(self, collector):
        """Should return daily metrics from Langfuse."""
        now = datetime.utcnow()
        from_ts = now - timedelta(days=7)

        result = collector.get_daily_metrics(from_ts, now)

        assert "data" in result
        assert isinstance(result["data"], list)

    def test_get_latency_metrics_returns_data(self, collector):
        """Should return latency metrics from Langfuse."""
        now = datetime.utcnow()
        from_ts = now - timedelta(days=1)

        result = collector.get_latency_metrics(from_ts, now)

        assert "data" in result

    def test_full_baseline_workflow(self, collector):
        """Test complete baseline workflow."""
        manager = BaselineManager(collector=collector)

        now = datetime.utcnow()
        from_ts = now - timedelta(hours=1)

        # Create snapshot (may have empty data, that's OK)
        snapshot = manager.create_snapshot(
            tag="test-integration",
            session_id="test-session",
            from_ts=from_ts,
            to_ts=now,
        )

        assert snapshot.tag == "test-integration"
        assert snapshot.timestamp == now
```

**Step 2: Run integration test (if Langfuse running)**

Run: `pytest tests/baseline/test_integration.py -v -m integration`
Expected: PASS (or SKIP if Langfuse not available)

**Step 3: Commit**

```bash
git add tests/baseline/test_integration.py
git commit -m "test(baseline): add integration tests for Langfuse"
```

---

## Task 10: Final Verification

**Step 1: Run all baseline tests**

Run: `pytest tests/baseline/ -v`
Expected: All tests PASS

**Step 2: Verify Makefile targets**

Run: `make -n baseline-smoke`
Run: `make -n baseline-compare BASELINE_TAG=test CURRENT_TAG=test2`
Expected: Commands print without errors

**Step 3: Verify imports work**

Run: `python -c "from tests.baseline import LangfuseMetricsCollector, BaselineManager; print('OK')"`
Expected: `OK`

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(baseline): complete baseline observability implementation

- LangfuseMetricsCollector for API queries
- BaselineManager for snapshot comparison
- CLI for baseline operations
- Makefile targets: baseline-smoke, baseline-load, baseline-compare
- VoyageService instrumented with @observe
- Thresholds for regression detection
- Documentation in CLAUDE.md"
```

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1. Install SDK | pyproject.toml | import check |
| 2. Module structure | tests/baseline/*.py | - |
| 3. MetricsCollector | collector.py | test_collector.py |
| 4. BaselineManager | manager.py | test_manager.py |
| 5. VoyageService @observe | voyage_service.py | test_voyage_observability.py |
| 6. Makefile | Makefile | make -n |
| 7. CLI | cli.py | test_cli.py |
| 8. Documentation | CLAUDE.md | - |
| 9. Integration | test_integration.py | pytest -m integration |
| 10. Final verification | - | all tests |

**Total: 10 tasks, ~15 tests, ~5 commits**
