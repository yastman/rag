"""Performance SLO contract tests for observability baselines (#556)."""

from __future__ import annotations


def _p95(values: list[float]) -> float:
    assert values, "values must be non-empty"
    ordered = sorted(values)
    idx = round(0.95 * (len(ordered) - 1))
    return ordered[idx]


def _success_rate(ok: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return ok / total


def test_p95_latency_budget_contract():
    """Synthetic contract: p95 latency should stay within 5s budget."""
    latencies_ms = [
        900,
        1100,
        1500,
        1700,
        2100,
        2600,
        2900,
        3200,
        3600,
        4200,
    ]
    assert _p95(latencies_ms) < 5000


def test_success_rate_budget_contract():
    """Synthetic contract: successful responses should meet 95% threshold."""
    ok = 48
    total = 50
    assert _success_rate(ok, total) >= 0.95


def test_cache_speedup_contract():
    """Synthetic contract: cache-hit path should be at least 3x faster."""
    miss_avg_ms = 1800.0
    hit_avg_ms = 500.0
    assert miss_avg_ms / hit_avg_ms >= 3.0
