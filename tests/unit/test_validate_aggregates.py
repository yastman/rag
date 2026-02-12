"""Tests for validation metrics aggregation."""

import contextlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.validate_traces import (
    TraceResult,
    ValidationRun,
    _flush_redis_caches,
    aggregate_node_payloads,
    check_langfuse_config,
    compute_aggregates,
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

    def test_go_no_go_renders_skip_status(self, tmp_path):
        """Skipped criteria render as '[-] SKIP', not '[x] PASS'."""
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

    @pytest.mark.asyncio
    async def test_flush_uses_cache_version_prefix(self, monkeypatch: pytest.MonkeyPatch):
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

        await _flush_redis_caches(mock_cache)

        assert "embeddings:v9:*" in seen_matches
        assert "sparse:v9:*" in seen_matches
        assert "analysis:v9:*" in seen_matches
        assert "search:v9:*" in seen_matches
        assert "rerank:v9:*" in seen_matches

    def test_report_includes_streaming_ttft_section(self, tmp_path):
        """Report includes Streaming TTFT section when streaming aggregates exist."""
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
            },
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
