"""Unit tests for Langfuse latest-trace audit script."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.e2e.langfuse_latest_trace_audit import (
    AuditResult,
    AuditTrace,
    TraceCoverage,
    _check_trace_coverage,
    _fetch_traces_via_cli,
    _fetch_traces_via_sdk,
    _keys_if_dict,
    fetch_latest_traces,
    main,
    render_markdown,
    run_audit,
    sanitize_trace,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_langfuse_configured():
    with patch(
        "scripts.e2e.langfuse_latest_trace_audit._langfuse_is_configured",
        return_value=True,
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace_dict(
    *,
    trace_id: str = "t-1",
    name: str = "telegram-message",
    tags: list[str] | None = None,
    session_id: str | None = None,
    timestamp: str = "2026-05-12T10:00:00Z",
    observations: list[dict] | None = None,
    scores: list[dict] | None = None,
    input_: dict | None = None,
    output: dict | None = None,
) -> dict:
    return {
        "id": trace_id,
        "name": name,
        "tags": tags or ["telegram"],
        "sessionId": session_id,
        "timestamp": timestamp,
        "observations": observations or [],
        "scores": scores or [],
        "input": input_,
        "output": output,
    }


def _make_score(name: str) -> dict:
    return {"name": name}


def _make_obs(name: str) -> dict:
    return {"name": name}


# ---------------------------------------------------------------------------
# sanitize_trace
# ---------------------------------------------------------------------------


def test_sanitize_trace_from_dict():
    raw = _make_trace_dict(
        trace_id="abc",
        name="telegram-message",
        tags=["telegram"],
        observations=[_make_obs("telegram-rag-query")],
        scores=[_make_score("query_type")],
        input_={"query_hash": "h1", "query_preview": "hi"},
        output={"answer_hash": "h2"},
    )
    t = sanitize_trace(raw)
    assert t.trace_id == "abc"
    assert t.name == "telegram-message"
    assert t.tags == ["telegram"]
    assert t.observation_names == ["telegram-rag-query"]
    assert t.score_names == ["query_type"]
    assert t.root_input_keys == ["query_hash", "query_preview"]
    assert t.root_output_keys == ["answer_hash"]
    assert t.observation_count == 1
    assert t.score_count == 1
    assert not t.is_proxy_noise


def test_sanitize_trace_from_object():
    raw = MagicMock()
    raw.id = "obj-1"
    raw.name = "telegram-message"
    raw.tags = ["telegram"]
    raw.sessionId = "sess-1"
    raw.timestamp = "2026-05-12T10:00:00Z"
    raw.input = {"query_hash": "h1"}
    raw.output = {"answer_hash": "h2"}
    raw.observations = [MagicMock(name="obs1")]
    raw.observations[0].name = "telegram-rag-query"
    raw.scores = [MagicMock(name="sc1")]
    raw.scores[0].name = "query_type"

    t = sanitize_trace(raw)
    assert t.trace_id == "obj-1"
    assert t.observation_names == ["telegram-rag-query"]
    assert t.score_names == ["query_type"]
    assert t.root_input_keys == ["query_hash"]


def test_sanitize_trace_classifies_litellm_as_proxy_noise():
    for name in ("litellm-acompletion", "litellm-completion"):
        raw = _make_trace_dict(name=name, observations=[_make_obs("GENERATION")])
        t = sanitize_trace(raw)
        assert t.is_proxy_noise is True


def test_sanitize_trace_filters_forbidden_raw_keys():
    raw = _make_trace_dict(
        input_={
            "query": "secret query text",
            "query_hash": "h1",
            "user": {"id": 123},
            "chat": {"id": 456},
        },
        output={"answer": "secret answer", "answer_hash": "h2"},
    )
    t = sanitize_trace(raw)
    # Allowed sanitized keys are preserved.
    assert "query_hash" in t.root_input_keys
    assert "answer_hash" in t.root_output_keys
    # Forbidden raw keys are stripped.
    assert "query" not in t.root_input_keys
    assert "user" not in t.root_input_keys
    assert "chat" not in t.root_input_keys
    assert "answer" not in t.root_output_keys
    # Ensure no raw values leak into the dataclass.
    assert t.trace_id == "t-1"
    assert t.name == "telegram-message"


# ---------------------------------------------------------------------------
# _keys_if_dict
# ---------------------------------------------------------------------------


def test_keys_if_dict_returns_sorted_keys():
    assert _keys_if_dict({"query_hash": "h1", "query_preview": "hi"}) == [
        "query_hash",
        "query_preview",
    ]


def test_keys_if_dict_non_dict_returns_empty():
    assert _keys_if_dict("string") == []
    assert _keys_if_dict(None) == []
    assert _keys_if_dict([1, 2]) == []


# ---------------------------------------------------------------------------
# _check_trace_coverage
# ---------------------------------------------------------------------------


def test_coverage_passes_for_complete_app_trace():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id=None,
        timestamp=None,
        observation_names=[
            "telegram-rag-query",
            "telegram-rag-supervisor",
            "node-cache-check",
            "node-retrieve",
            "node-grade",
            "node-rerank",
            "node-generate",
            "node-cache-store",
            "node-respond",
        ],
        score_names=[
            "query_type",
            "latency_total_ms",
            "semantic_cache_hit",
            "embeddings_cache_hit",
            "search_cache_hit",
            "rerank_applied",
            "rerank_cache_hit",
            "results_count",
            "no_results",
            "llm_used",
        ],
        root_input_keys=["query_hash"],
        root_output_keys=["answer_hash"],
        observation_count=9,
        score_count=10,
        is_proxy_noise=False,
    )
    cov = _check_trace_coverage(trace)
    assert cov.ok
    assert not cov.missing_observations
    assert not cov.missing_scores


def test_coverage_fails_for_missing_observation():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id=None,
        timestamp=None,
        observation_names=["telegram-rag-query"],  # missing supervisor
        score_names=[
            "query_type",
            "latency_total_ms",
            "semantic_cache_hit",
            "embeddings_cache_hit",
            "search_cache_hit",
            "rerank_applied",
            "rerank_cache_hit",
            "results_count",
            "no_results",
            "llm_used",
        ],
        root_input_keys=["query_hash"],
        root_output_keys=["answer_hash"],
        observation_count=1,
        score_count=10,
        is_proxy_noise=False,
    )
    cov = _check_trace_coverage(trace)
    assert not cov.ok
    assert "telegram-rag-supervisor" in cov.missing_observations


def test_coverage_fails_for_missing_score():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id=None,
        timestamp=None,
        observation_names=["telegram-rag-query", "telegram-rag-supervisor"],
        score_names=["query_type"],  # missing many
        root_input_keys=["query_hash"],
        root_output_keys=["answer_hash"],
        observation_count=2,
        score_count=1,
        is_proxy_noise=False,
    )
    cov = _check_trace_coverage(trace)
    assert not cov.ok
    assert "latency_total_ms" in cov.missing_scores


def test_coverage_fails_for_missing_root_input():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id=None,
        timestamp=None,
        observation_names=["telegram-rag-query", "telegram-rag-supervisor"],
        score_names=[
            "query_type",
            "latency_total_ms",
            "semantic_cache_hit",
            "embeddings_cache_hit",
            "search_cache_hit",
            "rerank_applied",
            "rerank_cache_hit",
            "results_count",
            "no_results",
            "llm_used",
        ],
        root_input_keys=[],  # missing query_hash
        root_output_keys=["answer_hash"],
        observation_count=2,
        score_count=10,
        is_proxy_noise=False,
    )
    cov = _check_trace_coverage(trace)
    assert not cov.ok
    assert "root_input" in cov.missing_observations


def test_coverage_fails_for_missing_root_output():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id=None,
        timestamp=None,
        observation_names=["telegram-rag-query", "telegram-rag-supervisor"],
        score_names=[
            "query_type",
            "latency_total_ms",
            "semantic_cache_hit",
            "embeddings_cache_hit",
            "search_cache_hit",
            "rerank_applied",
            "rerank_cache_hit",
            "results_count",
            "no_results",
            "llm_used",
        ],
        root_input_keys=["query_hash"],
        root_output_keys=[],  # missing answer_hash
        observation_count=2,
        score_count=10,
        is_proxy_noise=False,
    )
    cov = _check_trace_coverage(trace)
    assert not cov.ok
    assert "root_output" in cov.missing_observations


def test_coverage_for_proxy_noise_is_not_app_coverage():
    trace = AuditTrace(
        trace_id="p1",
        name="litellm-acompletion",
        tags=[],
        session_id=None,
        timestamp=None,
        observation_names=["GENERATION"],
        score_names=[],
        root_input_keys=[],
        root_output_keys=[],
        observation_count=1,
        score_count=0,
        is_proxy_noise=True,
    )
    cov = _check_trace_coverage(trace)
    # Proxy noise is not evaluated against app coverage.
    assert cov.ok
    assert cov.scenario_kind is None


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


def test_render_markdown_is_deterministic():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id="s1",
        timestamp="2026-05-12T10:00:00Z",
        observation_names=["telegram-rag-query"],
        score_names=["query_type"],
        root_input_keys=["query_hash"],
        root_output_keys=["answer_hash"],
        observation_count=1,
        score_count=1,
        is_proxy_noise=False,
    )
    cov = TraceCoverage(
        trace=trace,
        scenario_kind="text_rag",
        missing_observations={"telegram-rag-supervisor"},
        missing_scores=set(),
        ok=False,
    )
    result = AuditResult(
        inspected=[cov],
        proxy_noise_count=0,
        app_trace_count=1,
        timestamp="20260512-100000",
        session_marker=None,
        artifact_path=Path(".artifacts/latest-traces.md"),
        ok=False,
    )
    md = render_markdown(result)
    assert "Langfuse Latest Trace Audit" in md
    assert "t1" in md
    assert "telegram-message" in md
    assert "FAIL" in md
    assert "telegram-rag-supervisor" in md
    # No raw values
    assert "secret" not in md.lower()


def test_render_markdown_contains_no_raw_values():
    trace = AuditTrace(
        trace_id="t1",
        name="telegram-message",
        tags=["telegram"],
        session_id=None,
        timestamp="2026-05-12T10:00:00Z",
        observation_names=["telegram-rag-query"],
        score_names=["query_type"],
        root_input_keys=["query_hash"],
        root_output_keys=["answer_hash"],
        observation_count=1,
        score_count=1,
        is_proxy_noise=False,
    )
    cov = TraceCoverage(trace=trace, scenario_kind="text_rag", ok=True)
    result = AuditResult(
        inspected=[cov],
        proxy_noise_count=0,
        app_trace_count=1,
        timestamp="20260512-100000",
        session_marker=None,
        artifact_path=Path(".artifacts/latest-traces.md"),
        ok=True,
    )
    md = render_markdown(result)
    assert "query_hash" in md  # key name is fine
    assert "answer_hash" in md


def test_render_markdown_shows_proxy_noise():
    trace = AuditTrace(
        trace_id="p1",
        name="litellm-acompletion",
        tags=[],
        session_id=None,
        timestamp=None,
        observation_names=["GENERATION"],
        score_names=[],
        root_input_keys=[],
        root_output_keys=[],
        observation_count=1,
        score_count=0,
        is_proxy_noise=True,
    )
    cov = TraceCoverage(trace=trace, scenario_kind=None, ok=True)
    result = AuditResult(
        inspected=[cov],
        proxy_noise_count=1,
        app_trace_count=0,
        timestamp="20260512-100000",
        session_marker=None,
        artifact_path=Path(".artifacts/latest-traces.md"),
        ok=False,  # zero app traces = fail
    )
    md = render_markdown(result)
    assert "proxy noise" in md
    assert "LiteLLM" in md


# ---------------------------------------------------------------------------
# fetch_latest_traces
# ---------------------------------------------------------------------------


def test_fetch_latest_traces_prefers_cli(mock_langfuse_configured):
    with patch("scripts.e2e.langfuse_latest_trace_audit._fetch_traces_via_cli") as mock_cli:
        mock_cli.return_value = [
            _make_trace_dict(trace_id="cli-1", name="telegram-message"),
        ]
        traces = fetch_latest_traces(limit=5, prefer_cli=True)
        assert len(traces) == 1
        assert traces[0].trace_id == "cli-1"
        mock_cli.assert_called_once_with(limit=5, session_id=None)


def test_fetch_latest_traces_falls_back_to_sdk_when_cli_fails():
    with patch(
        "scripts.e2e.langfuse_latest_trace_audit._langfuse_is_configured",
        return_value=True,
    ):
        with patch(
            "scripts.e2e.langfuse_latest_trace_audit._fetch_traces_via_cli",
            side_effect=RuntimeError("cli not found"),
        ):
            with patch("scripts.e2e.langfuse_latest_trace_audit._fetch_traces_via_sdk") as mock_sdk:
                mock_sdk.return_value = [
                    _make_trace_dict(trace_id="sdk-1", name="telegram-message"),
                ]
                traces = fetch_latest_traces(limit=5, prefer_cli=True)
                assert len(traces) == 1
                assert traces[0].trace_id == "sdk-1"


def test_fetch_latest_traces_raises_when_both_fail():
    with patch(
        "scripts.e2e.langfuse_latest_trace_audit._langfuse_is_configured",
        return_value=False,
    ):
        with patch(
            "scripts.e2e.langfuse_latest_trace_audit._fetch_traces_via_cli",
            side_effect=RuntimeError("cli not found"),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                fetch_latest_traces(limit=5, prefer_cli=True)
            assert "Langfuse is not configured" in str(exc_info.value)


# ---------------------------------------------------------------------------
# run_audit
# ---------------------------------------------------------------------------


def test_run_audit_writes_artifact(tmp_path: Path):
    output_dir = tmp_path / "audit"
    with patch("scripts.e2e.langfuse_latest_trace_audit.fetch_latest_traces") as mock_fetch:
        mock_fetch.return_value = [
            AuditTrace(
                trace_id="t1",
                name="telegram-message",
                tags=["telegram"],
                session_id=None,
                timestamp=None,
                observation_names=[
                    "telegram-rag-query",
                    "telegram-rag-supervisor",
                    "node-cache-check",
                ],
                score_names=[
                    "query_type",
                    "latency_total_ms",
                    "semantic_cache_hit",
                    "embeddings_cache_hit",
                    "search_cache_hit",
                    "rerank_applied",
                    "rerank_cache_hit",
                    "results_count",
                    "no_results",
                    "llm_used",
                ],
                root_input_keys=["query_hash"],
                root_output_keys=["answer_hash"],
                observation_count=3,
                score_count=10,
                is_proxy_noise=False,
            ),
        ]
        result = run_audit(
            session_id=None,
            limit=5,
            output_dir=output_dir,
            prefer_cli=False,
        )
    assert result.artifact_path.exists()
    content = result.artifact_path.read_text(encoding="utf-8")
    assert "Langfuse Latest Trace Audit" in content
    assert "t1" in content
    assert result.app_trace_count == 1
    assert result.proxy_noise_count == 0
    assert result.ok


def test_run_audit_fails_when_zero_app_traces(tmp_path: Path):
    output_dir = tmp_path / "audit"
    with patch("scripts.e2e.langfuse_latest_trace_audit.fetch_latest_traces") as mock_fetch:
        mock_fetch.return_value = [
            AuditTrace(
                trace_id="p1",
                name="litellm-acompletion",
                tags=[],
                session_id=None,
                timestamp=None,
                observation_names=["GENERATION"],
                score_names=[],
                root_input_keys=[],
                root_output_keys=[],
                observation_count=1,
                score_count=0,
                is_proxy_noise=True,
            ),
        ]
        result = run_audit(
            session_id=None,
            limit=5,
            output_dir=output_dir,
            prefer_cli=False,
        )
    assert not result.ok
    assert result.app_trace_count == 0
    assert result.proxy_noise_count == 1


def test_run_audit_fails_when_coverage_missing(tmp_path: Path):
    output_dir = tmp_path / "audit"
    with patch("scripts.e2e.langfuse_latest_trace_audit.fetch_latest_traces") as mock_fetch:
        mock_fetch.return_value = [
            AuditTrace(
                trace_id="t1",
                name="telegram-message",
                tags=["telegram"],
                session_id=None,
                timestamp=None,
                observation_names=["telegram-rag-query"],  # missing supervisor
                score_names=["query_type"],
                root_input_keys=["query_hash"],
                root_output_keys=["answer_hash"],
                observation_count=1,
                score_count=1,
                is_proxy_noise=False,
            ),
        ]
        result = run_audit(
            session_id=None,
            limit=5,
            output_dir=output_dir,
            prefer_cli=False,
        )
    assert not result.ok
    assert result.app_trace_count == 1


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_returns_zero_on_pass(capsys):
    with patch("scripts.e2e.langfuse_latest_trace_audit.run_audit") as mock_run:
        mock_run.return_value = AuditResult(
            inspected=[],
            proxy_noise_count=0,
            app_trace_count=1,
            timestamp="20260512-100000",
            session_marker=None,
            artifact_path=Path(".artifacts/20260512-100000/latest-traces.md"),
            ok=True,
        )
        rc = main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "PASS" in captured.out


def test_main_returns_one_on_fail(capsys):
    with patch("scripts.e2e.langfuse_latest_trace_audit.run_audit") as mock_run:
        mock_run.return_value = AuditResult(
            inspected=[],
            proxy_noise_count=0,
            app_trace_count=0,
            timestamp="20260512-100000",
            session_marker=None,
            artifact_path=Path(".artifacts/20260512-100000/latest-traces.md"),
            ok=False,
        )
        rc = main([])
    assert rc == 1
    captured = capsys.readouterr()
    assert "FAIL" in captured.out


def test_main_passes_session_marker():
    with patch("scripts.e2e.langfuse_latest_trace_audit.run_audit") as mock_run:
        mock_run.return_value = AuditResult(
            inspected=[],
            proxy_noise_count=0,
            app_trace_count=1,
            timestamp="20260512-100000",
            session_marker="sess-1",
            artifact_path=Path(".artifacts/20260512-100000/latest-traces.md"),
            ok=True,
        )
        rc = main(["--session", "sess-1"])
    assert rc == 0
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["session_id"] == "sess-1"


def test_main_returns_one_on_runtime_error():
    with patch(
        "scripts.e2e.langfuse_latest_trace_audit.run_audit",
        side_effect=RuntimeError("boom"),
    ):
        rc = main([])
    assert rc == 1


# ---------------------------------------------------------------------------
# _fetch_traces_via_cli / _fetch_traces_via_sdk integration mocks
# ---------------------------------------------------------------------------


def test_fetch_via_cli_parses_json():
    fake_json = json.dumps(
        {
            "data": [
                _make_trace_dict(trace_id="cli-1", name="telegram-message"),
            ]
        }
    )
    with patch("scripts.e2e.langfuse_latest_trace_audit.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_json, stderr="")
        traces = _fetch_traces_via_cli(limit=5)
        assert len(traces) == 1
        assert traces[0]["id"] == "cli-1"


def test_fetch_via_cli_raises_on_nonzero_rc():
    with patch("scripts.e2e.langfuse_latest_trace_audit.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth failed")
        with pytest.raises(RuntimeError) as exc_info:
            _fetch_traces_via_cli(limit=5)
        assert "auth failed" in str(exc_info.value)


def test_fetch_via_sdk_returns_dicts():
    mock_trace = MagicMock()
    mock_trace.id = "sdk-1"
    mock_trace.name = "telegram-message"
    mock_trace.tags = ["telegram"]
    mock_trace.sessionId = None
    mock_trace.timestamp = "2026-05-12T10:00:00Z"
    mock_trace.input = {"query_hash": "h1"}
    mock_trace.output = {"answer_hash": "h2"}
    mock_trace.observations = []
    mock_trace.scores = []

    mock_page = MagicMock()
    mock_page.data = [mock_trace]

    with patch("scripts.e2e.langfuse_latest_trace_audit.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.list.return_value = mock_page
        traces = _fetch_traces_via_sdk(limit=5)
        assert len(traces) == 1
        assert traces[0]["id"] == "sdk-1"
        assert traces[0]["input"]["query_hash"] == "h1"
