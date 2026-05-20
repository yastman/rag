"""Performance SLO contract tests for observability baselines (***REMOVED***556, ***REMOVED***1638).

These tests exercise the *active* threshold-analysis path that the load CI
gate uses (`tests/load/metrics_collector.analyze_metrics` against
`tests/load/thresholds.THRESHOLDS`). The previous version compared
hand-crafted latency lists against an arbitrary 5s budget unrelated to
the canonical thresholds, so the contract test could pass while the real
gate threshold (full_rag.fail_ms=4000) was violated. (***REMOVED***1638.)

Each test below feeds boundary-condition `LoadMetrics` into
`analyze_metrics` and asserts the analyzer's pass/fail/warn decision
matches the canonical `THRESHOLDS` and baseline. Synthetic latency
samples are used only to exercise the analyzer logic — they are not
themselves "the" contract.
"""

from __future__ import annotations

from collections.abc import Sequence

from tests.load.metrics_collector import LoadMetrics, analyze_metrics
from tests.load.thresholds import (
    MIN_CACHE_HIT_RATE,
    REGRESSION_THRESHOLD,
    THRESHOLDS,
)


def _metrics_with_full_rag(latencies_ms: Sequence[float]) -> LoadMetrics:
    """Build a LoadMetrics with healthy ancillary signals + custom full_rag latencies."""
    m = LoadMetrics()
    for lat in latencies_ms:
        m.record_full_rag(lat)
    ***REMOVED*** Healthy supporting signals so unrelated thresholds do not interfere.
    for _ in range(20):
        m.record_routing(THRESHOLDS["routing"].warn_ms - 5)
        m.record_cache_hit(THRESHOLDS["cache_hit"].warn_ms - 5)
        m.record_qdrant(THRESHOLDS["qdrant"].warn_ms - 10)
    ***REMOVED*** Cache hit rate above MIN to keep it out of the failure list.
    m.cache_hits = 80
    m.cache_misses = 20
    return m


def test_analyze_passes_when_full_rag_under_warn_threshold() -> None:
    """When p95 is comfortably under warn, analyzer passes with no warnings/failures."""
    warn = THRESHOLDS["full_rag"].warn_ms  ***REMOVED*** 3000
    ***REMOVED*** 20 samples, all well under warn → p95 also under warn.
    samples = [warn - 500] * 20
    result = analyze_metrics(_metrics_with_full_rag(samples))
    assert result.passed is True
    assert result.failures == []
    full_rag_warn_msgs = [w for w in result.warnings if "full_rag" in w]
    assert full_rag_warn_msgs == []


def test_analyze_warns_when_full_rag_between_warn_and_fail() -> None:
    """Latency above warn but under fail produces a warning, not a failure."""
    warn = THRESHOLDS["full_rag"].warn_ms  ***REMOVED*** 3000
    fail = THRESHOLDS["full_rag"].fail_ms  ***REMOVED*** 4000
    midpoint = (warn + fail) // 2  ***REMOVED*** 3500
    samples = [midpoint] * 20
    result = analyze_metrics(_metrics_with_full_rag(samples))
    assert result.passed is True  ***REMOVED*** warn does not fail the gate
    assert any("full_rag" in w and "warn" in w for w in result.warnings)
    assert not any("full_rag" in f for f in result.failures)


def test_analyze_fails_when_full_rag_p95_exceeds_canonical_fail_threshold() -> None:
    """p95 strictly above THRESHOLDS['full_rag'].fail_ms must fail the gate."""
    fail = THRESHOLDS["full_rag"].fail_ms  ***REMOVED*** 4000 — the *real* gate value
    ***REMOVED*** All samples above fail → p95 above fail.
    samples = [fail + 100] * 20
    result = analyze_metrics(_metrics_with_full_rag(samples))
    assert result.passed is False
    full_rag_failures = [f for f in result.failures if "full_rag" in f]
    assert len(full_rag_failures) == 1
    assert "fail" in full_rag_failures[0]
    assert str(fail) in full_rag_failures[0]


def test_analyze_fails_when_cache_hit_rate_below_minimum() -> None:
    """Sub-MIN_CACHE_HIT_RATE cache hit ratio must surface in failures."""
    m = _metrics_with_full_rag([THRESHOLDS["full_rag"].warn_ms - 100] * 20)
    ***REMOVED*** Force hit rate well below MIN_CACHE_HIT_RATE.
    m.cache_hits = 10
    m.cache_misses = 90
    result = analyze_metrics(m)
    assert result.passed is False
    assert any("cache hit rate" in f for f in result.failures)


def test_analyze_flags_regression_against_baseline() -> None:
    """p95 above baseline * REGRESSION_THRESHOLD must register as a regression failure."""
    baseline_full_rag = 2500  ***REMOVED*** value from tests/load/baseline.json
    breach = int(baseline_full_rag * REGRESSION_THRESHOLD) + 50
    fail = THRESHOLDS["full_rag"].fail_ms
    ***REMOVED*** Choose a value above the regression line but below the absolute fail to
    ***REMOVED*** isolate the regression-only failure path.
    assert breach < fail, "test boundary must isolate regression case"
    samples = [breach] * 20
    baseline = {"routing": 15, "cache_hit": 20, "qdrant": 100, "full_rag": baseline_full_rag}
    result = analyze_metrics(_metrics_with_full_rag(samples), baseline=baseline)
    assert result.passed is False
    regression_failures = [f for f in result.failures if "full_rag regression" in f]
    assert len(regression_failures) == 1


def test_analyze_does_not_check_ttft_when_not_measured() -> None:
    """Empty TTFT samples must not trigger a TTFT warn/fail (only checked if measured)."""
    samples = [THRESHOLDS["full_rag"].warn_ms - 100] * 20
    result = analyze_metrics(_metrics_with_full_rag(samples), require_ttft=False)
    assert result.ttft_p95 == 0.0
    assert not any("ttft" in w for w in result.warnings)
    assert not any("ttft" in f for f in result.failures)


def test_analyze_requires_ttft_when_flag_is_set() -> None:
    """require_ttft=True surfaces a failure when TTFT was not collected."""
    samples = [THRESHOLDS["full_rag"].warn_ms - 100] * 20
    result = analyze_metrics(_metrics_with_full_rag(samples), require_ttft=True)
    assert result.passed is False
    assert any("TTFT required" in f for f in result.failures)


def test_threshold_dataclass_has_required_keys() -> None:
    """Sanity: canonical THRESHOLDS exposes every key analyze_metrics relies on."""
    required = {"routing", "cache_hit", "qdrant", "full_rag", "ttft"}
    assert required.issubset(THRESHOLDS.keys())
    for name in required:
        t = THRESHOLDS[name]
        assert t.warn_ms > 0
        assert t.fail_ms >= t.warn_ms


def test_min_cache_hit_rate_is_a_fraction() -> None:
    """Sanity: MIN_CACHE_HIT_RATE is a value in (0, 1]."""
    assert 0 < MIN_CACHE_HIT_RATE <= 1.0
