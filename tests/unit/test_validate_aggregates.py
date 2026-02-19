"""Tests for validation metrics aggregation."""

import contextlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.validate_traces import (
    TRACKED_NODE_NAMES,
    TraceResult,
    ValidationRun,
    _flush_redis_caches,
    _langfuse_auth_probe,
    aggregate_node_payloads,
    check_langfuse_config,
    check_orphan_traces,
    compute_aggregates,
    detect_runner_mode,
    discover_collections,
    evaluate_go_no_go,
    format_phase_summary,
    generate_report,
    resolve_report_collections,
    run_single_query,
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
    scores: dict[str, float] | None = None,
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
        scores=scores or {},
    )


def _make_validation_run(**overrides: object) -> ValidationRun:
    """Create a minimal ValidationRun for report tests."""
    import datetime

    defaults = {
        "run_id": "run-1",
        "git_sha": "abc123",
        "started_at": datetime.datetime.now(datetime.UTC),
        "collections": ["c1"],
        "skip_rerank_threshold": 0.012,
        "relevance_threshold_rrf": 0.005,
        "results": [],
    }
    defaults.update(overrides)
    return ValidationRun(**defaults)


def _make_cold_aggregates(**overrides: object) -> dict:
    """Create standard cold aggregates dict for report tests."""
    defaults = {
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
    defaults.update(overrides)
    return defaults


def _make_mock_qdrant_client(collection_names: list[str]) -> AsyncMock:
    """Create mock Qdrant client with given collection names."""
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name=n) for n in collection_names]
    )
    mock_client.close = AsyncMock()
    return mock_client


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

    def test_tracked_node_names_includes_voice_and_summarize(self):
        """TRACKED_NODE_NAMES covers transcribe and summarize spans (#241)."""
        assert "transcribe" in TRACKED_NODE_NAMES
        assert "summarize" in TRACKED_NODE_NAMES
        # All original 9 pipeline nodes still present
        for node in [
            "classify",
            "cache_check",
            "retrieve",
            "grade",
            "rerank",
            "generate",
            "rewrite",
            "cache_store",
            "respond",
        ]:
            assert node in TRACKED_NODE_NAMES

    def test_node_latencies_includes_transcribe(self):
        """Transcribe node spans are tracked in aggregates (#241)."""
        results = [
            _make_result(latency_stages={"transcribe": 0.08, "classify": 0.05}),
        ]
        agg = compute_aggregates(results)
        assert "transcribe" in agg["cold"]["node_p50"]
        assert agg["cold"]["node_p50"]["transcribe"] == pytest.approx(80.0, abs=5)

    def test_empty_results(self):
        agg = compute_aggregates([])
        assert agg == {}

    def test_judge_score_aggregation(self):
        """Judge scores from managed evaluators are aggregated (#386)."""
        results = [
            _make_result(scores={"judge_faithfulness": 0.9, "judge_answer_relevance": 0.8}),
            _make_result(scores={"judge_faithfulness": 0.7, "judge_answer_relevance": 0.6}),
            _make_result(scores={"judge_faithfulness": 0.8}),
        ]
        agg = compute_aggregates(results)

        assert agg["judge_faithfulness_mean"] == pytest.approx(0.8, abs=0.01)
        assert agg["judge_faithfulness_count"] == 3
        assert agg["judge_answer_relevance_mean"] == pytest.approx(0.7, abs=0.01)
        assert agg["judge_answer_relevance_count"] == 2
        assert "judge_context_relevance_mean" not in agg  # no data

    def test_judge_scores_absent_no_keys(self):
        """No judge scores -> no judge keys in aggregates."""
        results = [_make_result(scores={"cache_hit": 1.0})]
        agg = compute_aggregates(results)
        assert "judge_faithfulness_mean" not in agg

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

    def test_ttft_criterion_skip_on_small_sample(self):
        """n < 3 streaming samples -> skipped=True, passed=True."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p90": 5000,
                "latency_p95": 6000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
            "streaming": {"n": 2, "ttft_sample_count": 2, "ttft_p50": 800.0},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert "ttft_p50_lt_1000ms" in criteria
        assert criteria["ttft_p50_lt_1000ms"]["skipped"] is True
        assert criteria["ttft_p50_lt_1000ms"]["passed"] is True

    def test_ttft_criterion_pass_under_threshold(self):
        """TTFT p50 < 1000ms with sufficient samples -> passed."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p90": 5000,
                "latency_p95": 6000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
            "streaming": {"n": 5, "ttft_sample_count": 5, "ttft_p50": 700.0},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        c = criteria["ttft_p50_lt_1000ms"]
        assert c["passed"] is True
        assert c["skipped"] is False
        assert "700" in c["actual"]

    def test_ttft_criterion_fail_over_threshold(self):
        """TTFT p50 >= 1000ms -> failed."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p90": 5000,
                "latency_p95": 6000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
            "streaming": {"n": 5, "ttft_sample_count": 5, "ttft_p50": 1200.0},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        c = criteria["ttft_p50_lt_1000ms"]
        assert c["passed"] is False
        assert c["skipped"] is False

    def test_ttft_criterion_no_streaming_data(self):
        """No streaming aggregates -> skipped (n=0)."""
        aggregates = {
            "cold": {
                "latency_p50": 3000,
                "latency_p90": 5000,
                "latency_p95": 6000,
                "node_p50": {"generate": 1500},
            },
            "cache_hit": {"latency_p50": 500},
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(aggregates, results, orphan_rate=0.0)

        assert criteria["ttft_p50_lt_1000ms"]["skipped"] is True

    def test_custom_cold_p50_threshold(self):
        """Go/No-Go uses config threshold, not hardcoded 5000."""
        agg = {"cold": {"latency_p50": 6000}, "cache_hit": {}}
        # Default config: 5000 -> FAIL
        result = evaluate_go_no_go(agg, [], thresholds={"cold_p50_ms": 5000})
        assert result["cold_p50_lt_5s"]["passed"] is False

        # Custom config: 7000 -> PASS
        result = evaluate_go_no_go(agg, [], thresholds={"cold_p50_ms": 7000})
        assert result["cold_p50_lt_5s"]["passed"] is True

    def test_custom_rewrite_tokens_threshold(self):
        """Rewrite tokens threshold loaded from config, not hardcoded 96."""
        r = _make_result(phase="cold", scores={"rewrite_completion_tokens": 110.0})
        agg = {"cold": {}, "cache_hit": {}}
        # Default: 96 -> FAIL
        result = evaluate_go_no_go(agg, [r], thresholds={"rewrite_tokens_p50": 96})
        assert result["rewrite_tokens_p50_le_96"]["passed"] is False

        # Custom: 120 -> PASS
        result = evaluate_go_no_go(agg, [r], thresholds={"rewrite_tokens_p50": 120})
        assert result["rewrite_tokens_p50_le_96"]["passed"] is True

    def test_default_thresholds_from_yaml(self):
        """When no thresholds passed, loads from thresholds.yaml."""
        agg = {"cold": {"latency_p50": 4000}, "cache_hit": {}}
        result = evaluate_go_no_go(agg, [])
        # Should use yaml default (5000), so 4000 passes
        assert result["cold_p50_lt_5s"]["passed"] is True

    def test_judge_criteria_pass_above_threshold(self):
        """Judge criteria pass when mean >= threshold (#386)."""
        agg = {
            "cold": {"latency_p50": 3000, "latency_p90": 5000, "node_p50": {"generate": 1500}},
            "cache_hit": {"latency_p50": 500},
            "judge_faithfulness_mean": 0.80,
            "judge_faithfulness_count": 10,
            "judge_answer_relevance_mean": 0.75,
            "judge_answer_relevance_count": 10,
            "judge_context_relevance_mean": 0.70,
            "judge_context_relevance_count": 10,
        }
        results = [_make_result(phase="cold", latency=3000)]
        criteria = evaluate_go_no_go(agg, results, orphan_rate=0.0)

        assert criteria["judge_faithfulness_gte"]["passed"] is True
        assert criteria["judge_answer_relevance_gte"]["passed"] is True
        assert criteria["judge_context_relevance_gte"]["passed"] is True
        assert criteria["judge_faithfulness_gte"]["skipped"] is False

    def test_judge_criteria_fail_below_threshold(self):
        """Judge criteria fail when mean < threshold (#386)."""
        agg = {
            "cold": {},
            "cache_hit": {},
            "judge_faithfulness_mean": 0.50,
            "judge_faithfulness_count": 10,
        }
        criteria = evaluate_go_no_go(agg, [], orphan_rate=0.0)

        assert criteria["judge_faithfulness_gte"]["passed"] is False
        assert "0.500" in criteria["judge_faithfulness_gte"]["actual"]

    def test_judge_criteria_skipped_when_no_data(self):
        """Judge criteria skipped when no judge scores available (#386)."""
        agg = {"cold": {}, "cache_hit": {}}
        criteria = evaluate_go_no_go(agg, [], orphan_rate=0.0)

        assert criteria["judge_faithfulness_gte"]["skipped"] is True
        assert criteria["judge_faithfulness_gte"]["passed"] is True
        assert criteria["judge_answer_relevance_gte"]["skipped"] is True
        assert criteria["judge_context_relevance_gte"]["skipped"] is True


class TestLangfusePreflight:
    """Langfuse preflight should fail fast on incomplete/invalid credentials."""

    @pytest.fixture(autouse=True)
    def _disable_retry_sleep(self, monkeypatch: pytest.MonkeyPatch):
        """Keep retry semantics but remove real backoff delays in unit tests."""
        monkeypatch.setattr(_langfuse_auth_probe.retry, "sleep", lambda _seconds: None)

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
        mock_lf.auth_check.side_effect = RuntimeError("Invalid credentials")

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
        mock_lf.auth_check.return_value = True
        with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
            check_langfuse_config()

        mock_lf.auth_check.assert_called()
        mock_lf.flush.assert_not_called()

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


class TestRedisFlush:
    """Redis cache flush must verify completeness or return SKIPPED."""

    async def test_returns_ok_when_all_keys_deleted(self):
        """Flush succeeds: all patterns cleared, verify returns OK."""
        mock_redis = AsyncMock()
        deleted = False

        async def fake_scan_iter(match=None, count=100):
            # Before delete: yield keys; after delete: empty
            if not deleted:
                yield f"key:{match}"

        async def fake_delete(*keys):
            nonlocal deleted
            deleted = True

        mock_redis.scan_iter = fake_scan_iter
        mock_redis.delete = fake_delete

        mock_cache = MagicMock()
        mock_cache.redis = mock_redis
        mock_cache.semantic_cache = None

        result = await _flush_redis_caches(mock_cache)
        assert result == "OK"

    async def test_returns_skipped_when_redis_unavailable(self):
        """No redis connection -> SKIPPED, not silent warm run."""
        mock_cache = MagicMock()
        mock_cache.redis = None

        result = await _flush_redis_caches(mock_cache)
        assert result == "SKIPPED"

    async def test_returns_skipped_when_keys_remain_after_flush(self):
        """Flush runs but keys remain -> SKIPPED."""
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

    async def test_uses_current_cache_version_for_flush_patterns(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Flush patterns must be derived from active cache version."""
        seen_matches: list[str] = []

        async def fake_scan_iter(match=None, count=100):
            if match is not None:
                seen_matches.append(match)
            if False:
                yield None

        mock_redis = AsyncMock()
        mock_redis.scan_iter = fake_scan_iter
        mock_redis.delete = AsyncMock()

        mock_cache = MagicMock()
        mock_cache.redis = mock_redis
        mock_cache.semantic_cache = None

        monkeypatch.setattr("scripts.validate_traces._get_cache_version", lambda: "v9")

        result = await _flush_redis_caches(mock_cache)

        assert result == "OK"
        assert any(m == "embeddings:v9:*" for m in seen_matches)
        assert any(m == "sparse:v9:*" for m in seen_matches)
        assert any(m == "analysis:v9:*" for m in seen_matches)
        assert any(m == "search:v9:*" for m in seen_matches)
        assert any(m == "rerank:v9:*" for m in seen_matches)


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
        run = _make_validation_run()
        aggregates = {"cold": _make_cold_aggregates()}
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

    def test_go_no_go_renders_skip_status(self, tmp_path):
        """Skipped criteria render as '[-] SKIPPED (...)', not '[x] PASS'."""
        run = _make_validation_run()
        aggregates = {"cold": _make_cold_aggregates()}
        go_no_go = {
            "cold_p50_lt_5s": {
                "target": "< 5000 ms",
                "actual": "100 ms",
                "passed": True,
                "skipped": False,
            },
            "ttft_p50_lt_1000ms": {
                "target": "< 1000 ms",
                "actual": "N/A (n=0, need >= 3)",
                "passed": True,
                "skipped": True,
            },
        }
        out = tmp_path / "report.md"
        generate_report(run, aggregates, out, go_no_go=go_no_go)
        text = out.read_text(encoding="utf-8")

        assert "[-] SKIP" in text
        assert "[x] PASS" in text


class TestRedisFlushPatterns:
    """Redis flush should use active cache version for exact-cache prefixes."""

    # NOTE: test_flush_uses_cache_version_prefix was removed as duplicate of
    # TestRedisFlush.test_uses_current_cache_version_for_flush_patterns

    def test_report_includes_streaming_ttft_section(self, tmp_path):
        """Report includes Streaming TTFT section when streaming aggregates exist."""
        run = _make_validation_run()
        aggregates = {
            "cold": _make_cold_aggregates(),
            "streaming": {
                "n": 5,
                "ttft_sample_count": 5,
                "ttft_p50": 450.0,
                "ttft_p95": 800.0,
                "ttft_mean": 500.0,
                "ttft_max": 900.0,
            },
        }
        out = tmp_path / "report.md"
        generate_report(run, aggregates, out)
        text = out.read_text(encoding="utf-8")

        assert "## Streaming TTFT" in text
        assert "| ttft p50 | 450 ms |" in text
        assert "| sample count | 5 |" in text


class TestReportNoReferenceTrace:
    """Issue #168: reference trace c2b95d86 removed from report."""

    def test_report_no_reference_trace_section(self, tmp_path):
        """Report should not contain Reference Trace Comparison section."""
        run = _make_validation_run(run_id="test-123", git_sha="abc", collections=["test"])
        output = tmp_path / "report.md"
        generate_report(
            run=run,
            aggregates={},
            output_path=output,
        )
        content = output.read_text()
        assert "c2b95d86" not in content
        assert "Reference Trace Comparison" not in content


class TestGoNoGoReportFormat:
    """Test Go/No-Go report formatting in markdown."""

    @pytest.mark.parametrize(
        ("criterion", "expected_text"),
        [
            pytest.param(
                {
                    "target": "< 1000 ms",
                    "actual": "N/A (n=2, need >= 3)",
                    "passed": True,
                    "skipped": True,
                },
                "SKIPPED",
                id="skipped",
            ),
            pytest.param(
                {"target": "< 5000 ms", "actual": "3200 ms", "passed": True},
                "PASS",
                id="pass",
            ),
            pytest.param(
                {"target": "< 5000 ms", "actual": "6100 ms", "passed": False},
                "FAIL",
                id="fail",
            ),
        ],
    )
    def test_criterion_format(self, criterion: dict, expected_text: str):
        from scripts.validate_traces import _format_go_no_go_status

        assert expected_text in _format_go_no_go_status(criterion)


class TestCollectionResolution:
    """Report collections must reflect actually validated collections only."""

    def test_uses_only_collections_present_in_results(self):
        discovered = ["gdrive_documents_bge"]
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
        discovered = ["gdrive_documents_bge"]
        assert resolve_report_collections(discovered, []) == discovered


class TestCollectionDiscovery:
    """Collection discovery should use Qdrant API, not hardcoded list."""

    async def test_discovers_exact_match(self):
        """Finds collection by exact name from Qdrant API."""
        mock_client = _make_mock_qdrant_client(["gdrive_documents_bge", "some_other_collection"])
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        assert "gdrive_documents_bge" in result

    async def test_discovers_collection_with_quantization_suffix(self):
        """Finds base collection even when stored with _scalar suffix."""
        mock_client = _make_mock_qdrant_client(["gdrive_documents_bge_scalar"])
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        assert "gdrive_documents_bge_scalar" in result

    async def test_prefers_exact_match_over_suffixed(self):
        """If both base and suffixed exist, prefer exact match."""
        mock_client = _make_mock_qdrant_client(
            ["gdrive_documents_bge", "gdrive_documents_bge_scalar"]
        )
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        # Exact match preferred — only one entry per base name
        assert result.count("gdrive_documents_bge") == 1
        assert "gdrive_documents_bge_scalar" not in result

    async def test_returns_empty_when_qdrant_unavailable(self):
        """Qdrant connection failure returns empty list, not crash."""
        mock_client = _make_mock_qdrant_client([])
        mock_client.get_collections.side_effect = ConnectionError("refused")

        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        assert result == []

    async def test_discovers_bge_collection_without_voyage_key(self):
        """BGE-M3 collection discovery does not depend on VOYAGE_API_KEY."""
        mock_client = _make_mock_qdrant_client(["gdrive_documents_bge"])
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections("http://localhost:6333")

        assert "gdrive_documents_bge" in result

    async def test_prefers_mode_suffix_when_quantization_enabled(self):
        """Quantization mode must influence discovered collection choice."""
        mock_client = _make_mock_qdrant_client(
            [
                "gdrive_documents_bge",
                "gdrive_documents_bge_scalar",
                "gdrive_documents_bge_binary",
            ]
        )
        with patch("qdrant_client.AsyncQdrantClient", return_value=mock_client):
            result = await discover_collections(
                "http://localhost:6333",
                quantization_mode="binary",
            )

        assert "gdrive_documents_bge_binary" in result
        assert "gdrive_documents_bge" not in result


class TestRunnerModeDetection:
    """Runner-mode detection should treat suffixed names the same as base names."""

    def test_voyage_suffix_collection_uses_voyage_runner(self):
        mode = detect_runner_mode("contextual_bulgaria_voyage_binary")
        assert mode == "voyage_compatible"


class TestLangfuseLookupSkipsSynthetic:
    """Synthetic skipped traces must not trigger Langfuse lookups."""

    def test_orphan_check_skips_cold_skipped_synthetic_traces(self):
        skipped = _make_result(phase="cold", latency=0)
        skipped.state["cold_skipped"] = True
        skipped.trace_id = "skipped"
        normal = _make_result(phase="cold", latency=100)
        normal.trace_id = "real-trace"

        mock_lf = MagicMock()
        mock_lf.api.trace.get.return_value = SimpleNamespace(session_id="session-1")

        with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
            rate = check_orphan_traces([skipped, normal])

        assert rate == 0.0
        mock_lf.api.trace.get.assert_called_once_with("real-trace")


class TestFakeMessage:
    """FakeMessage / FakeSentMessage for streaming TTFT measurement."""

    async def test_answer_records_timestamp_and_returns_sent(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        assert msg.t_answer_called is None
        assert msg.sent is None

        sent = await msg.answer("placeholder")
        assert msg.t_answer_called is not None
        assert msg.sent is sent

    async def test_edit_text_records_first_edit_timestamp(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        assert sent.t_first_edit is None

        await sent.edit_text("chunk 1")
        t1 = sent.t_first_edit
        assert t1 is not None
        assert sent.edit_calls_count == 1
        assert sent.last_text_len == 7  # len("chunk 1")

        await sent.edit_text("chunk 1 more")
        assert sent.t_first_edit == t1  # first edit unchanged
        assert sent.edit_calls_count == 2
        assert sent.last_text_len == 12

    async def test_ttft_calculation_positive(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        await sent.edit_text("first chunk")

        ttft = (sent.t_first_edit - msg.t_answer_called) * 1000
        assert ttft >= 0

    async def test_no_edits_gives_none_ttft(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        assert sent.t_first_edit is None

    async def test_delete_is_noop(self):
        from scripts.validate_traces import FakeMessage

        msg = FakeMessage()
        sent = await msg.answer("placeholder")
        await sent.delete()  # should not raise


class TestStreamingAggregation:
    """Streaming TTFT aggregation in compute_aggregates."""

    def test_streaming_phase_produces_ttft_aggregates(self):
        """Streaming results with valid TTFT produce ttft_p50/p95/mean/max."""
        results = [
            _make_result(phase="streaming", latency=2000),
            _make_result(phase="streaming", latency=2100),
            _make_result(phase="streaming", latency=1900),
        ]
        results[0].state["streaming_ttft_ms"] = 400.0
        results[1].state["streaming_ttft_ms"] = 600.0
        results[2].state["streaming_ttft_ms"] = 500.0

        agg = compute_aggregates(results)

        assert "streaming" in agg
        s = agg["streaming"]
        assert s["n"] == 3
        assert s["ttft_sample_count"] == 3
        assert s["ttft_p50"] == pytest.approx(500.0, abs=1)
        assert s["ttft_mean"] == pytest.approx(500.0, abs=1)
        assert s["ttft_max"] == pytest.approx(600.0, abs=1)

    def test_streaming_excludes_none_ttft_from_aggregates(self):
        """Results with streaming_ttft_ms=None are excluded from TTFT stats."""
        results = [
            _make_result(phase="streaming", latency=2000),
            _make_result(phase="streaming", latency=2100),
            _make_result(phase="streaming", latency=1900),
        ]
        results[0].state["streaming_ttft_ms"] = 400.0
        results[1].state["streaming_ttft_ms"] = None
        results[2].state["streaming_ttft_ms"] = 600.0

        agg = compute_aggregates(results)

        s = agg["streaming"]
        assert s["n"] == 3
        assert s["ttft_sample_count"] == 2
        assert s["ttft_p50"] == pytest.approx(500.0, abs=1)

    def test_streaming_not_mixed_into_cold(self):
        """Streaming results must not appear in cold aggregates."""
        results = [
            _make_result(phase="cold", latency=3000),
            _make_result(phase="streaming", latency=2000),
        ]
        results[1].state["streaming_ttft_ms"] = 500.0

        agg = compute_aggregates(results)

        assert agg["cold"]["n"] == 1
        assert agg["streaming"]["n"] == 1

    def test_no_streaming_results_no_streaming_key(self):
        """No streaming results -> no 'streaming' key in aggregates."""
        results = [_make_result(phase="cold", latency=3000)]
        agg = compute_aggregates(results)
        assert "streaming" not in agg

    def test_all_none_ttft_no_streaming_key(self):
        """All streaming results with None TTFT -> no 'streaming' key."""
        results = [_make_result(phase="streaming", latency=2000)]
        agg = compute_aggregates(results)
        assert "streaming" not in agg

    def test_non_numeric_ttft_ignored(self):
        """Non-numeric TTFT values must be ignored from streaming stats."""
        results = [
            _make_result(phase="streaming", latency=2000),
            _make_result(phase="streaming", latency=2100),
        ]
        results[0].state["streaming_ttft_ms"] = 450.0
        results[1].state["streaming_ttft_ms"] = "450ms"

        agg = compute_aggregates(results)

        s = agg["streaming"]
        assert s["n"] == 2
        assert s["ttft_sample_count"] == 1
        assert s["ttft_p50"] == pytest.approx(450.0, abs=1)


class TestAggregatesStddev:
    """Issue #168: aggregates must include latency_stddev."""

    def test_aggregates_include_stddev(self):
        results = [
            _make_result(phase="cold", latency=2000),
            _make_result(phase="cold", latency=3000),
            _make_result(phase="cold", latency=4000),
        ]
        agg = compute_aggregates(results)
        cold = agg["cold"]
        assert "latency_stddev" in cold
        # stddev of [2000, 3000, 4000] ≈ 816.5
        assert 800 < cold["latency_stddev"] < 850

    def test_stddev_zero_for_single_result(self):
        results = [_make_result(phase="cold", latency=5000)]
        agg = compute_aggregates(results)
        assert agg["cold"]["latency_stddev"] == 0.0


class TestRunSingleQuery:
    """run_single_query should restore mutable config even on failures."""

    async def test_restores_streaming_flag_on_graph_failure(self, monkeypatch: pytest.MonkeyPatch):
        class _FakeClient:
            def update_current_trace(self, **kwargs):
                return None

        def _fake_observe(*, name: str):
            def _decorator(fn):
                async def _wrapped(*args, **kwargs):
                    kwargs.pop("langfuse_trace_id", None)
                    return await fn(*args, **kwargs)

                return _wrapped

            return _decorator

        class _FailingGraph:
            async def ainvoke(self, state):
                raise RuntimeError("graph boom")

        fake_bot = types.SimpleNamespace(_write_langfuse_scores=lambda *_args, **_kwargs: None)
        fake_graph = types.SimpleNamespace(build_graph=lambda **_kwargs: _FailingGraph())
        fake_state = types.SimpleNamespace(
            make_initial_state=lambda **_kwargs: {"messages": [{"role": "user", "content": "q"}]}
        )
        fake_observability = types.SimpleNamespace(
            get_client=lambda: _FakeClient(),
            observe=_fake_observe,
            propagate_attributes=lambda **_kwargs: contextlib.nullcontext(),
        )

        monkeypatch.setitem(sys.modules, "telegram_bot.bot", fake_bot)
        monkeypatch.setitem(sys.modules, "telegram_bot.graph.graph", fake_graph)
        monkeypatch.setitem(sys.modules, "telegram_bot.graph.state", fake_state)
        monkeypatch.setitem(sys.modules, "telegram_bot.observability", fake_observability)

        config = types.SimpleNamespace(
            streaming_enabled=False,
            max_rewrite_attempts=1,
            skip_rerank_threshold=0.012,
            relevance_threshold_rrf=0.005,
        )
        services = {
            "cache": object(),
            "embeddings": object(),
            "sparse_embeddings": object(),
            "qdrant": object(),
            "reranker": None,
            "llm": None,
            "config": config,
        }
        query = types.SimpleNamespace(text="q", source="test", difficulty="easy")
        run_meta = {"run_id": "run-1", "git_sha": "abc123", "collection": "test-col"}

        with pytest.raises(RuntimeError, match="graph boom"):
            await run_single_query(
                query,
                services,
                run_meta,
                phase="streaming",
                message=object(),
            )

        assert config.streaming_enabled is False
