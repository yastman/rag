"""Tests for validation metrics aggregation."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.validate_traces import (
    TraceResult,
    ValidationRun,
    aggregate_node_payloads,
    check_langfuse_config,
    compute_aggregates,
    evaluate_go_no_go,
    format_phase_summary,
    generate_report,
    resolve_report_collections,
)


def _make_result(
    phase: str = "cold",
    latency: float = 100.0,
    cache_hit: bool = False,
    rerank: bool = True,
    results_count: int = 10,
    rewrite_count: int = 0,
    observation_error_count: int = 0,
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
            "observation_error_count": observation_error_count,
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

    def test_cold_aggregates_include_p90(self):
        """Aggregates should expose p90 explicitly for Go/No-Go checks."""
        results = [
            _make_result(latency=100),
            _make_result(latency=200),
            _make_result(latency=300),
            _make_result(latency=400),
            _make_result(latency=500),
        ]
        agg = compute_aggregates(results)

        assert "latency_p90" in agg["cold"]
        assert agg["cold"]["latency_p90"] > agg["cold"]["latency_p50"]
        assert agg["cold"]["latency_p90"] <= agg["cold"]["latency_max"]


class TestEvaluateGoNoGo:
    """Test gate evaluation edge cases."""

    def test_handles_empty_cold_results(self):
        criteria = evaluate_go_no_go(
            {"cold": {}, "cache_hit": {}},
            [],
            orphan_rate=0.0,
        )
        assert criteria["cold_over_10s_lt_15pct"]["actual"] == "0.0% (0/0)"
        assert criteria["orphan_traces_zero"]["passed"] is True

    def test_uses_generate_p50_key_not_ttft(self):
        """Go/No-Go must use 'generate_p50_lt_2s', not 'ttft_p50_lt_2s'."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p95": 5000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert "generate_p50_lt_2s" in criteria, "Criterion must be named 'generate_p50_lt_2s'"
        assert "ttft_p50_lt_2s" not in criteria, "Old 'ttft_p50_lt_2s' key must not exist"
        assert criteria["generate_p50_lt_2s"]["passed"] is True  # 1500 < 2000

    def test_zero_errors_fails_on_observation_level_errors(self):
        aggregates = {
            "cold": {"latency_p50": 1000, "latency_p95": 1200, "node_p50": {"generate": 800}},
            "cache_hit": {"latency_p50": 100},
        }
        results = [
            _make_result(phase="cold", latency=1000, observation_error_count=1),
            _make_result(phase="cache_hit", latency=120),
        ]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)
        assert criteria["zero_errors"]["passed"] is False

    def test_uses_cold_p90_metric_when_available(self):
        """Criterion key says p90, so evaluator must prefer latency_p90 over p95."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p90": 9000,
                "latency_p95": 1000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert criteria["cold_p90_lt_8s"]["passed"] is False
        assert criteria["cold_p90_lt_8s"]["actual"] == "9000 ms"


class TestLangfusePreflight:
    """Langfuse preflight should fail fast on incomplete/invalid credentials."""

    def test_requires_public_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
        monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3001")
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

        with pytest.raises(SystemExit):
            check_langfuse_config()

    def test_fails_on_invalid_credentials(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3001")

        mock_lf = MagicMock()
        mock_lf.api.trace.list.side_effect = RuntimeError("Invalid credentials")

        with (
            patch("scripts.validate_traces.Langfuse", return_value=mock_lf),
            pytest.raises(SystemExit),
        ):
            check_langfuse_config()

    def test_auth_probe_does_not_flush_client(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3001")

        mock_lf = MagicMock()
        with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
            check_langfuse_config()

        mock_lf.api.trace.list.assert_called_once_with(limit=1)
        mock_lf.flush.assert_not_called()


class TestAggregateNodePayloads:
    """Payload byte aggregation for heavy-node observability checks."""

    def test_aggregates_p50_by_node_and_field(self):
        r1 = _make_result(phase="cold", latency=100)
        r1.node_payload_bytes = {
            "retrieve": {"input": 120, "output": 180, "metadata": 301, "total": 601},
            "generate": {"input": 130, "output": 250, "metadata": 301, "total": 681},
        }
        r2 = _make_result(phase="cold", latency=110)
        r2.node_payload_bytes = {
            "retrieve": {"input": 140, "output": 170, "metadata": 301, "total": 611},
            "generate": {"input": 150, "output": 260, "metadata": 301, "total": 711},
        }

        payloads = aggregate_node_payloads([r1, r2])

        assert payloads["retrieve"]["input_p50"] == pytest.approx(130.0)
        assert payloads["retrieve"]["output_p50"] == pytest.approx(175.0)
        assert payloads["retrieve"]["metadata_p50"] == pytest.approx(301.0)
        assert payloads["generate"]["total_p50"] == pytest.approx(696.0)

    def test_ignores_nodes_without_payload_data(self):
        r1 = _make_result(phase="cold", latency=100)
        r1.node_payload_bytes = {}
        payloads = aggregate_node_payloads([r1])
        assert payloads == {}


class TestReportAndSummary:
    """Report and console summary formatting should expose p90 explicitly."""

    def test_generate_report_includes_latency_p90_row(self, tmp_path):
        run = ValidationRun(
            run_id="run-1",
            git_sha="abc123",
            started_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            collections=["c1"],
            skip_rerank_threshold=0.012,
            relevance_threshold_rrf=0.005,
            results=[],
        )
        aggregates = {
            "cold": {
                "n": 1,
                "latency_p50": 100.0,
                "latency_p90": 130.0,
                "latency_p95": 150.0,
                "latency_mean": 110.0,
                "latency_max": 160.0,
                "semantic_cache_hit_rate": 0.0,
                "search_cache_hit_rate": 0.0,
                "rerank_applied_rate": 0.0,
                "rewrite_rate": 0.0,
                "results_count_mean": 20.0,
                "node_p50": {},
                "node_p95": {},
            }
        }
        out = tmp_path / "report.md"
        generate_report(run, aggregates, out)
        text = out.read_text(encoding="utf-8")
        assert "| latency p90 | 130 ms |" in text

    def test_format_phase_summary_includes_p90(self):
        agg = {
            "n": 3,
            "latency_p50": 100.0,
            "latency_p90": 140.0,
            "latency_p95": 160.0,
            "latency_mean": 120.0,
        }
        line = format_phase_summary("cold", agg)
        assert "p90=140ms" in line


class TestCollectionResolution:
    """Report collections must reflect actually validated collections only."""

    def test_uses_only_collections_present_in_results(self):
        discovered = ["gdrive_documents_bge", "contextual_bulgaria_voyage"]
        results = [
            TraceResult(
                trace_id="t1",
                query="q",
                collection="gdrive_documents_bge",
                phase="cold",
                source="smoke",
                difficulty="easy",
                latency_wall_ms=1000.0,
            )
        ]
        assert resolve_report_collections(discovered, results) == ["gdrive_documents_bge"]

    def test_falls_back_to_discovered_if_results_empty(self):
        discovered = ["gdrive_documents_bge", "contextual_bulgaria_voyage"]
        assert resolve_report_collections(discovered, []) == discovered
