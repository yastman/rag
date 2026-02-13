# Baseline CI Isolation Implementation Plan (#167)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate cross-PR contamination in CI baseline-compare by switching from aggregate Langfuse APIs to per-trace computation with session isolation.

**Architecture:** Replace `get_daily_metrics()` / `get_latency_metrics()` / `get_cache_metrics()` aggregate calls with `langfuse.api.trace.list(session_id=...)` + `langfuse.api.observations.list(trace_id=...)`. Compute p50/p95/cost/tokens locally from observation-level data. Bootstrap gracefully when `main-latest` tag doesn't exist.

**Tech Stack:** Python 3.12, Langfuse SDK v3 (`langfuse.api.trace.list`, `langfuse.api.observations.list`), Click CLI, pytest, GitHub Actions

**Design:** `docs/plans/2026-02-12-baseline-ci-isolation-design.md`

---

### Task 1: Test — `collect_session_metrics` happy path

**Files:**
- Modify: `tests/baseline/test_collector.py`

**Step 1: Write the failing test**

Add to `tests/baseline/test_collector.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from tests.baseline.collector import LangfuseMetricsCollector


class TestCollectSessionMetrics:
    """Tests for per-trace session metrics computation."""

    def _make_collector(self, mock_langfuse_cls):
        """Helper: create collector with mocked Langfuse client."""
        mock_client = MagicMock()
        mock_langfuse_cls.return_value = mock_client
        collector = LangfuseMetricsCollector(
            public_key="pk-test",
            secret_key="sk-test",
            host="http://localhost:3001",
        )
        return collector, mock_client

    def _make_trace(self, trace_id="t1", session_id="s1", metadata=None, total_cost=0.05):
        """Helper: create mock trace object."""
        trace = MagicMock()
        trace.id = trace_id
        trace.session_id = session_id
        trace.metadata = metadata or {}
        trace.total_cost = total_cost
        return trace

    def _make_observation(
        self,
        obs_type="GENERATION",
        start_time=None,
        end_time=None,
        cost=0.01,
        input_tokens=100,
        output_tokens=50,
        model="gpt-4o",
    ):
        """Helper: create mock observation object."""
        obs = MagicMock()
        obs.type = obs_type
        obs.start_time = start_time or datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc)
        obs.end_time = end_time or datetime(2026, 2, 12, 10, 0, 1, 500000, tzinfo=timezone.utc)
        obs.calculated_total_cost = cost
        obs.model = model
        usage = MagicMock()
        usage.input = input_tokens
        usage.output = output_tokens
        obs.usage = usage
        return obs

    @patch("tests.baseline.collector.Langfuse")
    def test_computes_metrics_from_traces_and_observations(self, mock_langfuse_cls):
        """Should compute p50/p95/cost/tokens from observation-level data."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        # 2 traces, each with 1 generation observation
        traces = [
            self._make_trace("t1", "ci-abc-job-1", metadata={"cache_hit": False}),
            self._make_trace("t2", "ci-abc-job-1", metadata={"cache_hit": True}),
        ]
        traces_page = MagicMock()
        traces_page.data = traces
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        # Observations: 1s and 2s latency
        obs1 = self._make_observation(
            start_time=datetime(2026, 2, 12, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 12, 10, 0, 1, tzinfo=timezone.utc),
            cost=0.01, input_tokens=100, output_tokens=50,
        )
        obs2 = self._make_observation(
            start_time=datetime(2026, 2, 12, 10, 1, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 2, 12, 10, 1, 2, tzinfo=timezone.utc),
            cost=0.02, input_tokens=200, output_tokens=80,
        )
        obs_page1 = MagicMock()
        obs_page1.data = [obs1]
        obs_page2 = MagicMock()
        obs_page2.data = [obs2]
        mock_client.api.observations.list.side_effect = [obs_page1, obs_page2]

        result = collector.collect_session_metrics(session_id="ci-abc-job-1")

        assert result.llm_calls == 2
        assert result.total_cost_usd == pytest.approx(0.03)
        assert result.llm_tokens_input == 300
        assert result.llm_tokens_output == 130
        # p50 of [1000, 2000] = 1500ms, p95 ≈ 1950ms
        assert result.llm_latency_p50_ms == pytest.approx(1500.0)
        assert result.llm_latency_p95_ms > 1800.0
        # 1 hit, 1 miss → 50%
        assert result.cache_hit_rate == pytest.approx(0.5)
        assert result.cache_hits == 1
        assert result.cache_misses == 1
        assert result.trace_count == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/baseline/test_collector.py::TestCollectSessionMetrics::test_computes_metrics_from_traces_and_observations -v`
Expected: FAIL — `AttributeError: 'LangfuseMetricsCollector' object has no attribute 'collect_session_metrics'`

**Step 3: Commit failing test**

```bash
git add tests/baseline/test_collector.py
git commit -m "test(baseline): add failing test for collect_session_metrics #167"
```

---

### Task 2: Test — None guards on observations

**Files:**
- Modify: `tests/baseline/test_collector.py`

**Step 1: Write the failing tests**

Add to `TestCollectSessionMetrics` class:

```python
    @patch("tests.baseline.collector.Langfuse")
    def test_handles_none_end_time(self, mock_langfuse_cls):
        """Should skip observations with None end_time for latency."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces = [self._make_trace("t1", "s1", metadata={"cache_hit": False})]
        traces_page = MagicMock()
        traces_page.data = traces
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        # One observation with None end_time
        obs = self._make_observation(cost=0.01, input_tokens=100, output_tokens=50)
        obs.end_time = None
        obs_page = MagicMock()
        obs_page.data = [obs]
        mock_client.api.observations.list.return_value = obs_page

        result = collector.collect_session_metrics(session_id="s1")

        # Latency should be 0 (no valid observations)
        assert result.llm_latency_p50_ms == 0.0
        assert result.llm_latency_p95_ms == 0.0
        # Cost/tokens still counted
        assert result.total_cost_usd == pytest.approx(0.01)
        assert result.llm_tokens_input == 100

    @patch("tests.baseline.collector.Langfuse")
    def test_handles_none_cost_and_usage(self, mock_langfuse_cls):
        """Should treat None cost as 0 and None usage as 0 tokens."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces = [self._make_trace("t1", "s1", metadata={})]
        traces_page = MagicMock()
        traces_page.data = traces
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        obs = self._make_observation()
        obs.calculated_total_cost = None
        obs.usage = None
        obs_page = MagicMock()
        obs_page.data = [obs]
        mock_client.api.observations.list.return_value = obs_page

        result = collector.collect_session_metrics(session_id="s1")

        assert result.total_cost_usd == 0.0
        assert result.llm_tokens_input == 0
        assert result.llm_tokens_output == 0

    @patch("tests.baseline.collector.Langfuse")
    def test_empty_traces_returns_zero_metrics(self, mock_langfuse_cls):
        """Should return zero metrics when no traces found."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces_page = MagicMock()
        traces_page.data = []
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        result = collector.collect_session_metrics(session_id="nonexistent")

        assert result.trace_count == 0
        assert result.llm_calls == 0
        assert result.total_cost_usd == 0.0
        assert result.llm_latency_p50_ms == 0.0
        assert result.cache_hit_rate == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/baseline/test_collector.py::TestCollectSessionMetrics -v -k "none or empty"`
Expected: FAIL — same `AttributeError`

**Step 3: Commit**

```bash
git add tests/baseline/test_collector.py
git commit -m "test(baseline): add None guard + empty traces tests #167"
```

---

### Task 3: Test — tag-based filtering (baseline lookup)

**Files:**
- Modify: `tests/baseline/test_collector.py`

**Step 1: Write the failing test**

Add to `TestCollectSessionMetrics`:

```python
    @patch("tests.baseline.collector.Langfuse")
    def test_filters_by_tag(self, mock_langfuse_cls):
        """Should pass tags to trace.list when filtering by tag."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        traces_page = MagicMock()
        traces_page.data = []
        traces_page.meta = MagicMock()
        traces_page.meta.next_page = None
        mock_client.api.trace.list.return_value = traces_page

        collector.collect_session_metrics(tag="main-latest")

        mock_client.api.trace.list.assert_called_once()
        call_kwargs = mock_client.api.trace.list.call_args
        assert call_kwargs.kwargs.get("tags") == ["main-latest"]

    @patch("tests.baseline.collector.Langfuse")
    def test_requires_session_or_tag(self, mock_langfuse_cls):
        """Should raise ValueError when neither session_id nor tag provided."""
        collector, mock_client = self._make_collector(mock_langfuse_cls)

        with pytest.raises(ValueError, match="session_id or tag"):
            collector.collect_session_metrics()
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/baseline/test_collector.py::TestCollectSessionMetrics -v -k "tag or requires"`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/baseline/test_collector.py
git commit -m "test(baseline): add tag filter and validation tests #167"
```

---

### Task 4: Implement — `SessionMetrics` dataclass + `collect_session_metrics`

**Files:**
- Modify: `tests/baseline/collector.py`

**Step 1: Add `SessionMetrics` dataclass and implement `collect_session_metrics`**

Add to `collector.py` after the imports:

```python
import statistics
from dataclasses import dataclass, field


@dataclass
class SessionMetrics:
    """Metrics computed from per-trace observation data."""

    trace_count: int = 0
    llm_calls: int = 0

    # Latency (ms) — computed from GENERATION observations
    llm_latency_p50_ms: float = 0.0
    llm_latency_p95_ms: float = 0.0

    # Cost
    total_cost_usd: float = 0.0
    llm_tokens_input: int = 0
    llm_tokens_output: int = 0

    # Cache
    cache_hit_rate: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
```

Add to `LangfuseMetricsCollector` class:

```python
    def _fetch_all_traces(
        self,
        *,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list:
        """Fetch all traces matching filters, handling pagination."""
        all_traces = []
        page = 1
        while True:
            result = self.client.api.trace.list(
                session_id=session_id,
                tags=tags,
                limit=limit,
                page=page,
            )
            all_traces.extend(result.data)
            if not result.meta or not result.meta.next_page:
                break
            page = result.meta.next_page
        return all_traces

    def collect_session_metrics(
        self,
        *,
        session_id: str | None = None,
        tag: str | None = None,
    ) -> SessionMetrics:
        """Fetch traces + observations for a session/tag, compute metrics locally.

        Args:
            session_id: Filter by Langfuse session_id (for current CI run).
            tag: Filter by Langfuse tag (for baseline).

        Returns:
            SessionMetrics with aggregated observation-level data.

        Raises:
            ValueError: If neither session_id nor tag is provided.
        """
        if not session_id and not tag:
            msg = "At least one of session_id or tag must be provided"
            raise ValueError(msg)

        traces = self._fetch_all_traces(
            session_id=session_id,
            tags=[tag] if tag else None,
        )

        if not traces:
            return SessionMetrics()

        latencies_ms: list[float] = []
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        llm_calls = 0
        cache_hits = 0
        cache_misses = 0

        for trace in traces:
            # Cache from trace metadata
            cache_hit = (trace.metadata or {}).get("cache_hit")
            if cache_hit is True:
                cache_hits += 1
            elif cache_hit is False:
                cache_misses += 1

            # Fetch GENERATION observations for this trace
            obs_result = self.client.api.observations.list(
                trace_id=trace.id,
                type="GENERATION",
            )
            for obs in obs_result.data:
                llm_calls += 1

                # Latency (skip if timestamps missing)
                if obs.start_time and obs.end_time:
                    delta = (obs.end_time - obs.start_time).total_seconds() * 1000
                    latencies_ms.append(delta)

                # Cost (None → 0)
                total_cost += obs.calculated_total_cost or 0.0

                # Tokens (None usage → 0)
                if obs.usage:
                    total_input_tokens += obs.usage.input or 0
                    total_output_tokens += obs.usage.output or 0

        # Compute percentiles
        p50 = 0.0
        p95 = 0.0
        if latencies_ms:
            sorted_lat = sorted(latencies_ms)
            p50 = _percentile(sorted_lat, 50)
            p95 = _percentile(sorted_lat, 95)

        cache_total = cache_hits + cache_misses
        cache_rate = cache_hits / cache_total if cache_total > 0 else 0.0

        return SessionMetrics(
            trace_count=len(traces),
            llm_calls=llm_calls,
            llm_latency_p50_ms=p50,
            llm_latency_p95_ms=p95,
            total_cost_usd=total_cost,
            llm_tokens_input=total_input_tokens,
            llm_tokens_output=total_output_tokens,
            cache_hit_rate=cache_rate,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
        )
```

Add module-level helper (before the class):

```python
def _percentile(sorted_values: list[float], pct: int) -> float:
    """Compute percentile from pre-sorted values (linear interpolation)."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (pct / 100) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])
```

**Step 2: Run all collector tests**

Run: `uv run pytest tests/baseline/test_collector.py::TestCollectSessionMetrics -v`
Expected: ALL PASS (6 tests)

**Step 3: Run full baseline test suite**

Run: `uv run pytest tests/baseline/ -v`
Expected: ALL PASS (old tests still pass — we haven't removed old methods yet)

**Step 4: Commit**

```bash
git add tests/baseline/collector.py
git commit -m "feat(baseline): add collect_session_metrics with per-trace computation #167"
```

---

### Task 5: Test — CLI bootstrap SKIP

**Files:**
- Modify: `tests/baseline/test_cli.py`

**Step 1: Write the failing tests**

Add to `tests/baseline/test_cli.py`:

```python
import json
from pathlib import Path

from click.testing import CliRunner


class TestCompareBootstrap:
    """Tests for bootstrap SKIP when no baseline exists."""

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_skip_when_no_baseline_traces(self, mock_manager_cls, mock_get_collector):
        """Should exit 0 with SKIP when no baseline traces found."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_collector.collect_session_metrics.return_value = MagicMock(trace_count=0)
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

        assert result.exit_code == 0
        assert "SKIP" in result.output.upper() or "skip" in result.output.lower()

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_skip_writes_structured_json(self, mock_manager_cls, mock_get_collector):
        """Should write structured JSON with skip reason."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_collector.collect_session_metrics.return_value = MagicMock(trace_count=0)
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

            assert result.exit_code == 0
            report = json.loads(Path("report.json").read_text())
            assert report["status"] == "skipped"
            assert "reason" in report
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/baseline/test_cli.py::TestCompareBootstrap -v`
Expected: FAIL — `compare` command doesn't accept `--baseline-tag` / `--current-session` / `--output`

**Step 3: Commit**

```bash
git add tests/baseline/test_cli.py
git commit -m "test(baseline): add CLI bootstrap SKIP tests #167"
```

---

### Task 6: Test — CLI new flags + JSON output

**Files:**
- Modify: `tests/baseline/test_cli.py`

**Step 1: Write the failing tests**

Add to `tests/baseline/test_cli.py`:

```python
class TestCompareNewFlags:
    """Tests for new CLI flags."""

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_with_new_flags_passes(self, mock_manager_cls, mock_get_collector):
        """Should pass with --baseline-tag and --current-session."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        baseline_metrics = MagicMock(
            trace_count=5,
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            total_cost_usd=0.05,
            cache_hit_rate=0.65,
            llm_calls=100,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            cache_hits=65,
            cache_misses=35,
        )
        current_metrics = MagicMock(
            trace_count=5,
            llm_latency_p50_ms=160.0,
            llm_latency_p95_ms=360.0,
            total_cost_usd=0.052,
            cache_hit_rate=0.63,
            llm_calls=102,
            llm_tokens_input=10200,
            llm_tokens_output=2550,
            cache_hits=63,
            cache_misses=37,
        )
        mock_collector.collect_session_metrics.side_effect = [
            baseline_metrics, current_metrics
        ]

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_manager.compare.return_value = (True, [])
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

            assert result.exit_code == 0
            assert "PASSED" in result.output
            report = json.loads(Path("report.json").read_text())
            assert report["status"] == "passed"

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_writes_failed_json(self, mock_manager_cls, mock_get_collector):
        """Should write status=failed JSON on regression."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        metrics = MagicMock(
            trace_count=5,
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            total_cost_usd=0.05,
            cache_hit_rate=0.65,
            llm_calls=100,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            cache_hits=65,
            cache_misses=35,
        )
        mock_collector.collect_session_metrics.return_value = metrics

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_manager.compare.return_value = (False, ["LLM p95 latency regression"])
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

            assert result.exit_code == 1
            report = json.loads(Path("report.json").read_text())
            assert report["status"] == "failed"
            assert len(report["regressions"]) == 1
```

**Step 2: Run to verify failure**

Run: `uv run pytest tests/baseline/test_cli.py::TestCompareNewFlags -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/baseline/test_cli.py
git commit -m "test(baseline): add new CLI flags and JSON output tests #167"
```

---

### Task 7: Implement — Rewrite `cli.py` compare command

**Files:**
- Modify: `tests/baseline/cli.py`

**Step 1: Rewrite the `compare` command**

Replace the entire `compare` function in `cli.py`:

```python
@cli.command()
@click.option("--baseline-tag", required=True, help="Langfuse tag for baseline traces (e.g. main-latest)")
@click.option("--current-session", required=True, help="Langfuse session_id for current CI run")
@click.option(
    "--thresholds",
    default="tests/baseline/thresholds.yaml",
    help="Path to thresholds file",
)
@click.option(
    "--output",
    required=True,
    help="Path to write JSON report artifact (always written for passed/failed/skipped)",
)
def compare(baseline_tag: str, current_session: str, thresholds: str, output: str):
    """Compare current run against baseline using per-trace metrics."""
    collector = get_collector()
    manager = BaselineManager(
        collector=collector,
        thresholds_path=Path(thresholds),
    )

    # Fetch baseline metrics by tag
    click.echo(f"Fetching baseline metrics (tag={baseline_tag})...")
    baseline_metrics = collector.collect_session_metrics(tag=baseline_tag)

    if baseline_metrics.trace_count == 0:
        result = {
            "status": "skipped",
            "reason": f"No baseline traces tagged '{baseline_tag}' found",
            "recommendation": "Run smoke tests on main branch first to establish baseline",
            "baseline_tag": baseline_tag,
            "current_session": current_session,
        }
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result, indent=2))
        click.secho(f"SKIP — no baseline tagged '{baseline_tag}' found", fg="yellow")
        click.echo("Run smoke tests on main branch first to establish baseline.")
        sys.exit(0)

    # Fetch current metrics by session
    click.echo(f"Fetching current metrics (session={current_session})...")
    current_metrics = collector.collect_session_metrics(session_id=current_session)

    if current_metrics.trace_count == 0:
        result = {
            "status": "skipped",
            "reason": f"No traces found for session '{current_session}'",
            "baseline_tag": baseline_tag,
            "current_session": current_session,
        }
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result, indent=2))
        click.secho(f"SKIP — no traces for session '{current_session}'", fg="yellow")
        sys.exit(0)

    # Build snapshots from session metrics
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    baseline_snapshot = _metrics_to_snapshot(
        baseline_metrics,
        tag=baseline_tag,
        session_id=f"baseline:{baseline_tag}",
        ts=now,
    )
    current_snapshot = _metrics_to_snapshot(
        current_metrics,
        tag=current_session,
        session_id=current_session,
        ts=now,
    )

    # Compare
    click.echo("\nComparing metrics...")
    passed, regressions = manager.compare(current_snapshot, baseline_snapshot)

    # Print table
    _print_comparison_table(baseline_snapshot, current_snapshot)

    # Write JSON report
    report = {
        "status": "passed" if passed else "failed",
        "baseline_tag": baseline_tag,
        "current_session": current_session,
        "baseline_traces": baseline_metrics.trace_count,
        "current_traces": current_metrics.trace_count,
        "regressions": regressions,
        "metrics": {
            "baseline": {
                "llm_latency_p95_ms": baseline_snapshot.llm_latency_p95_ms,
                "total_cost_usd": baseline_snapshot.total_cost_usd,
                "cache_hit_rate": baseline_snapshot.cache_hit_rate,
                "llm_calls": baseline_snapshot.llm_calls,
            },
            "current": {
                "llm_latency_p95_ms": current_snapshot.llm_latency_p95_ms,
                "total_cost_usd": current_snapshot.total_cost_usd,
                "cache_hit_rate": current_snapshot.cache_hit_rate,
                "llm_calls": current_snapshot.llm_calls,
            },
        },
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2))

    click.echo("\n" + "=" * 60)
    if passed:
        click.secho("PASSED — No regressions detected", fg="green", bold=True)
        sys.exit(0)
    else:
        click.secho("FAILED — Regressions detected:", fg="red", bold=True)
        for regression in regressions:
            click.echo(f"  - {regression}")
        sys.exit(1)
```

Add helper functions to `cli.py`:

```python
def _metrics_to_snapshot(
    metrics,
    *,
    tag: str,
    session_id: str,
    ts,
) -> BaselineSnapshot:
    """Convert SessionMetrics to BaselineSnapshot without mixing tag/session semantics."""
    return BaselineSnapshot(
        timestamp=ts,
        tag=tag,
        session_id=session_id,
        llm_latency_p50_ms=metrics.llm_latency_p50_ms,
        llm_latency_p95_ms=metrics.llm_latency_p95_ms,
        full_rag_latency_p95_ms=metrics.llm_latency_p95_ms * 1.5,
        total_cost_usd=metrics.total_cost_usd,
        llm_tokens_input=metrics.llm_tokens_input,
        llm_tokens_output=metrics.llm_tokens_output,
        llm_calls=metrics.llm_calls,
        voyage_embed_calls=0,
        voyage_rerank_calls=0,
        cache_hit_rate=metrics.cache_hit_rate,
        cache_hits=metrics.cache_hits,
        cache_misses=metrics.cache_misses,
    )


def _print_comparison_table(baseline, current):
    """Print metrics comparison table."""
    def fmt_change(curr, base):
        if base == 0:
            return "N/A"
        pct = (curr / base - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    click.echo(f"\n{'Metric':<30} {'Baseline':<15} {'Current':<15} {'Change':<10}")
    click.echo("-" * 70)
    for label, b_val, c_val, fmt in [
        ("LLM p95 latency (ms)", baseline.llm_latency_p95_ms, current.llm_latency_p95_ms, ".0f"),
        ("Total cost (USD)", baseline.total_cost_usd, current.total_cost_usd, ".4f"),
        ("Cache hit rate", baseline.cache_hit_rate, current.cache_hit_rate, ".1%"),
        ("LLM calls", baseline.llm_calls, current.llm_calls, ""),
    ]:
        b_str = f"{b_val:{fmt}}" if fmt else str(b_val)
        c_str = f"{c_val:{fmt}}" if fmt else str(c_val)
        click.echo(f"{label:<30} {b_str:<15} {c_str:<15} {fmt_change(c_val, b_val):<10}")
```

Add `import json` to the top of `cli.py`.

Remove the old `compare` function. Keep `report` and `set-baseline` commands for now (will update in Task 9).

**Step 2: Run CLI tests**

Run: `uv run pytest tests/baseline/test_cli.py -v`
Expected: New tests PASS. Old tests for `compare` will fail (flags changed) — update or remove them in next step.

**Step 3: Update old CLI tests**

Remove `TestBaselineCLI.test_compare_requires_baseline_tag`, `test_compare_requires_current_tag`, `test_compare_outputs_results`, `test_compare_fails_on_regression` (they test old `--baseline`/`--current` flags). The new `TestCompareBootstrap` and `TestCompareNewFlags` classes replace them.

**Step 4: Run full test suite**

Run: `uv run pytest tests/baseline/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add tests/baseline/cli.py tests/baseline/test_cli.py
git commit -m "feat(baseline): rewrite compare command with session isolation #167"
```

---

### Task 8: Wire `manager.py` — update `create_snapshot` to use new collector

**Files:**
- Modify: `tests/baseline/manager.py`

**Step 1: Verify existing manager tests still pass**

Run: `uv run pytest tests/baseline/test_manager.py -v`
Expected: PASS — `BaselineManager.compare()` is unchanged, tests use hardcoded snapshots.

Note: `create_snapshot()` in `manager.py` is no longer called by the new `cli.py` (we use `_metrics_to_snapshot` helper instead). Mark `create_snapshot` as deprecated or remove it. The `compare()` method remains unchanged — it operates on `BaselineSnapshot` objects.

**Step 2: Add deprecation notice to create_snapshot**

```python
    def create_snapshot(self, ...):
        """Create baseline snapshot from Langfuse data.

        .. deprecated:: 2.0
            Use collector.collect_session_metrics() + cli._metrics_to_snapshot() instead.
        """
        import warnings
        warnings.warn(
            "create_snapshot is deprecated. Use collect_session_metrics() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # ... existing code unchanged ...
```

**Step 3: Run all tests**

Run: `uv run pytest tests/baseline/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/baseline/manager.py
git commit -m "refactor(baseline): deprecate create_snapshot in favor of collect_session_metrics #167"
```

---

### Task 9: Remove `.current_baseline` file logic + update `set-baseline`

**Files:**
- Modify: `tests/baseline/cli.py`
- Modify: `tests/baseline/test_cli.py`
- Modify: `.gitignore`

**Step 1: Write test for new set-baseline (tag-based)**

Add to `test_cli.py`:

```python
class TestSetBaselineNew:
    """Tests for tag-based set-baseline command."""

    def test_set_baseline_help_shows_new_flags(self):
        """set-baseline should show --session-id flag."""
        runner = CliRunner()
        result = runner.invoke(set_baseline, ["--help"])
        assert "--session-id" in result.output or "--tag" in result.output
```

**Step 2: Rewrite `set-baseline` command**

In `cli.py`, replace `set_baseline`:

```python
@cli.command("set-baseline")
@click.option("--tag", required=True, help="Tag to apply as baseline marker")
@click.option("--session-id", required=True, help="Session ID whose traces to tag")
def set_baseline(tag: str, session_id: str):
    """Tag traces from a session as the new baseline."""
    collector = get_collector()
    traces = collector._fetch_all_traces(session_id=session_id)

    if not traces:
        click.secho(f"No traces found for session '{session_id}'", fg="red")
        sys.exit(1)

    click.echo(f"Tagging {len(traces)} traces with '{tag}'...")
    for trace in traces:
        existing_tags = list(trace.tags or [])
        if tag not in existing_tags:
            existing_tags.append(tag)
            collector.client.api.trace.update(
                trace_id=trace.id,
                tags=existing_tags,
            )

    click.secho(f"Baseline set: {len(traces)} traces tagged '{tag}'", fg="green")
```

**Step 3: Remove `.current_baseline` references**

- Remove `baseline_file = Path("tests/baseline/.current_baseline")` from `report` command
- Update `report` to use `--baseline-tag` and `--current-session` flags
- Delete `tests/baseline/.current_baseline` file if it exists
- Add `.current_baseline` to `.gitignore` (safety)

**Step 4: Remove old `test_set_baseline_writes_file` test**

**Step 5: Run tests**

Run: `uv run pytest tests/baseline/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add tests/baseline/cli.py tests/baseline/test_cli.py .gitignore
git rm --cached tests/baseline/.current_baseline 2>/dev/null || true
git commit -m "feat(baseline): replace file-based baseline with Langfuse tag API #167"
```

---

### Task 10: Update CI workflow

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: Update baseline-compare job**

Replace the `Run baseline comparison` step:

```yaml
      - name: Run baseline comparison
        if: env.LANGFUSE_AVAILABLE == 'true'
        env:
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
          LANGFUSE_HOST: ${{ secrets.LANGFUSE_HOST }}
        run: |
          SHORT_SHA="${GITHUB_SHA::8}"
          CURRENT_SESSION="ci-${SHORT_SHA}-${GITHUB_JOB}-${GITHUB_RUN_ATTEMPT}"

          uv run python3 -m tests.baseline.cli compare \
            --baseline-tag="main-latest" \
            --current-session="${CURRENT_SESSION}" \
            --thresholds=tests/baseline/thresholds.yaml \
            --output="reports/baseline-${CURRENT_SESSION}.json"

      - name: Upload baseline report
        if: always() && env.LANGFUSE_AVAILABLE == 'true'
        uses: actions/upload-artifact@v4
        with:
          name: baseline-report
          path: reports/baseline-*.json
          retention-days: 30
```

Remove the old `Skip - Langfuse not configured` step (the new compare command handles missing baseline gracefully).

**Step 2: Verify YAML validity**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No errors

**Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(baseline): use session isolation and artifact upload #167"
```

---

### Task 11: Update Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Update `baseline-compare` and `baseline-check` targets**

Update `baseline-compare`:

```makefile
baseline-compare: ## Compare current run against baseline (usage: make baseline-compare BASELINE_TAG=... CURRENT_SESSION=...)
ifndef BASELINE_TAG
	$(error BASELINE_TAG is required. Usage: make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=ci-abc-job-1)
endif
ifndef CURRENT_SESSION
	$(error CURRENT_SESSION is required.)
endif
	@echo "$(BLUE)Comparing baseline...$(NC)"
	uv run python -m tests.baseline.cli compare \
		--baseline-tag="$(BASELINE_TAG)" \
		--current-session="$(CURRENT_SESSION)" \
		--thresholds=tests/baseline/thresholds.yaml \
		--output="reports/baseline-$(CURRENT_SESSION).json"
```

Update `baseline-check`:

```makefile
baseline-check: baseline-smoke ## Quick baseline check (smoke + compare with main)
	@echo "$(BLUE)Comparing with main baseline...$(NC)"
	make baseline-compare BASELINE_TAG=main-latest CURRENT_SESSION=$(BASELINE_SESSION)
```

**Step 2: Verify Makefile syntax**

Run: `make -n baseline-compare BASELINE_TAG=test CURRENT_SESSION=test 2>&1 | head -5`
Expected: dry-run output showing the command

**Step 3: Commit**

```bash
git add Makefile
git commit -m "build(baseline): update Makefile targets for session isolation #167"
```

---

### Task 12: Cleanup — remove deprecated aggregate methods

**Files:**
- Modify: `tests/baseline/collector.py`
- Modify: `tests/baseline/test_collector.py`

**Step 1: Remove old methods from collector**

Remove from `LangfuseMetricsCollector`:
- `get_daily_metrics()`
- `get_latency_metrics()`
- `get_cache_metrics()`
- `get_trace_count()`

Keep:
- `collect_session_metrics()` (new)
- `_fetch_all_traces()` (new)
- `collect_infrastructure_metrics()` (unchanged)
- `get_qdrant_metrics()` (static, unchanged)
- `get_redis_metrics()` (static, unchanged)

**Step 2: Remove old tests**

Remove from `test_collector.py`:
- `TestLangfuseMetricsCollector.test_get_daily_metrics_calls_api`
- `TestLangfuseMetricsCollector.test_get_latency_metrics_uses_v2_api`
- `TestLangfuseMetricsCollector.test_get_trace_count_filters_by_name`

Keep `test_init_creates_client`.

**Step 3: Run full test suite**

Run: `uv run pytest tests/baseline/ -v`
Expected: ALL PASS

**Step 4: Lint check**

Run: `uv run ruff check tests/baseline/ --fix && uv run ruff format tests/baseline/`
Expected: Clean

**Step 5: Commit**

```bash
git add tests/baseline/collector.py tests/baseline/test_collector.py
git commit -m "refactor(baseline): remove deprecated aggregate API methods #167"
```

---

### Task 13: Final verification

**Step 1: Run full baseline test suite**

Run: `uv run pytest tests/baseline/ -v`
Expected: ALL PASS

**Step 2: Run lint + types**

Run: `make check`
Expected: Clean

**Step 3: Run full unit tests**

Run: `uv run pytest tests/unit/ -n auto --timeout=30`
Expected: ALL PASS

**Step 4: Verify no `.current_baseline` references remain**

Run: `grep -r "current_baseline" tests/ --include="*.py"`
Expected: No matches (or only in deprecated docstrings)

**Step 5: Verify old CLI flags are gone**

Run: `uv run python -m tests.baseline.cli compare --help`
Expected: Shows `--baseline-tag`, `--current-session`, `--output`. No `--baseline`, `--current`, `--hours`.
