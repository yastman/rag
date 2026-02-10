"""Tests for validation metrics aggregation."""

import pytest

from scripts.validate_traces import TraceResult, compute_aggregates


def _make_result(
    phase: str = "cold",
    latency: float = 100.0,
    cache_hit: bool = False,
    rerank: bool = True,
    results_count: int = 10,
    rewrite_count: int = 0,
    latency_stages: dict | None = None,
) -> TraceResult:
    return TraceResult(
        trace_id="test",
        query="test query",
        collection="test",
        phase=phase,
        source="test",
        difficulty="easy",
        latency_wall_ms=latency,
        state={
            "cache_hit": cache_hit,
            "search_cache_hit": False,
            "embeddings_cache_hit": False,
            "rerank_applied": rerank,
            "search_results_count": results_count,
            "rewrite_count": rewrite_count,
            "latency_stages": latency_stages or {},
        },
    )


class TestComputeAggregates:
    """Test metrics aggregation."""

    def test_cold_aggregates(self):
        results = [
            _make_result(latency=100),
            _make_result(latency=200),
            _make_result(latency=300),
            _make_result(latency=400),
            _make_result(latency=500),
        ]
        agg = compute_aggregates(results)

        assert "cold" in agg
        cold = agg["cold"]
        assert cold["n"] == 5
        assert cold["latency_p50"] == pytest.approx(300.0, abs=1)
        assert cold["latency_mean"] == pytest.approx(300.0, abs=1)
        assert cold["latency_max"] == pytest.approx(500.0, abs=1)

    def test_cache_hit_separate(self):
        results = [
            _make_result(phase="cold", latency=500),
            _make_result(phase="cache_hit", latency=50, cache_hit=True),
            _make_result(phase="cache_hit", latency=30, cache_hit=True),
        ]
        agg = compute_aggregates(results)

        assert agg["cold"]["n"] == 1
        assert agg["cache_hit"]["n"] == 2
        assert agg["cache_hit"]["semantic_cache_hit_rate"] == pytest.approx(1.0)

    def test_warmup_excluded(self):
        results = [
            _make_result(phase="warmup", latency=999),
            _make_result(phase="cold", latency=100),
        ]
        agg = compute_aggregates(results)

        assert "warmup" not in agg
        assert agg["cold"]["n"] == 1

    def test_rerank_rate(self):
        results = [
            _make_result(rerank=True),
            _make_result(rerank=True),
            _make_result(rerank=False),
        ]
        agg = compute_aggregates(results)
        assert agg["cold"]["rerank_applied_rate"] == pytest.approx(2 / 3)

    def test_node_latencies(self):
        results = [
            _make_result(latency_stages={"retrieve": 0.1, "generate": 0.2}),
            _make_result(latency_stages={"retrieve": 0.3, "generate": 0.4}),
        ]
        agg = compute_aggregates(results)
        # retrieve: [100ms, 300ms] → p50=200ms
        assert agg["cold"]["node_p50"]["retrieve"] == pytest.approx(200.0, abs=10)
        assert "generate" in agg["cold"]["node_p50"]

    def test_empty_results(self):
        agg = compute_aggregates([])
        assert agg == {}
