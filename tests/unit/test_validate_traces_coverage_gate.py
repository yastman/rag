"""Unit tests for required trace-family coverage gate in validate_traces."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.validate_traces import (
    REQUIRED_TELEGRAM_OBSERVATION_FAMILIES,
    REQUIRED_TRACE_NAMES,
    TELEGRAM_ROOT_CONTEXT_REQUIREMENT,
    check_required_trace_coverage,
    evaluate_go_no_go,
)


def _trace(trace_id: str, *, name: str = "telegram-message", input_data: dict | None = None):
    return SimpleNamespace(id=trace_id, name=name, input=input_data or {}, observations=[])


def _obs(name: str, *, level: str | None = None):
    obs = SimpleNamespace(name=name)
    if level is not None:
        obs.level = level
    return obs


def test_check_required_trace_coverage_marks_missing_trace_families() -> None:
    mock_lf = MagicMock()
    mock_lf.api.trace.list.side_effect = [
        SimpleNamespace(data=[SimpleNamespace(id="trace-api")]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
    ]

    with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
        coverage = check_required_trace_coverage(required_observation_names=[])

    assert coverage["present"] == ["rag-api-query"]
    assert set(coverage["missing"]) == {"voice-session", "ingestion-cli-run"}


def test_check_required_trace_coverage_accepts_telegram_observations_under_root() -> None:
    mock_lf = MagicMock()
    mock_lf.api.trace.list.side_effect = [
        # Direct family checks
        SimpleNamespace(data=[SimpleNamespace(id="trace-api")]),
        SimpleNamespace(data=[SimpleNamespace(id="trace-voice")]),
        SimpleNamespace(data=[SimpleNamespace(id="trace-ingest")]),
        # Telegram root traces in lookback window
        SimpleNamespace(data=[SimpleNamespace(id="root-1"), SimpleNamespace(id="root-2")]),
    ]

    root_1 = _trace(
        "root-1",
        input_data={
            "content_type": "text",
            "query_preview": "какие есть варианты внж?",
            "query_hash": "a1b2c3d4",
            "query_len": 24,
            "route": "rag_query",
        },
    )
    root_1.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("detect-agent-intent"),
        _obs("detect-agent-intent"),
        _obs("node-cache-check", level="WARNING"),
        _obs("node-retrieve"),
        _obs("node-generate"),
    ]

    root_2 = _trace(
        "root-2",
        input_data={
            "content_type": "text",
            "query_preview": "повтори прошлый ответ",
            "query_hash": "e5f6a7b8",
            "query_len": 21,
            "route": "cache_hit",
        },
    )
    root_2.observations = [
        _obs("telegram-rag-query"),
        _obs("node-cache-check"),
    ]

    mock_lf.api.trace.get.side_effect = [root_1, root_2]

    with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
        coverage = check_required_trace_coverage()

    expected_present = set(REQUIRED_TRACE_NAMES) | set(REQUIRED_TELEGRAM_OBSERVATION_FAMILIES)
    assert expected_present.issubset(set(coverage["present"]))
    assert TELEGRAM_ROOT_CONTEXT_REQUIREMENT in coverage["present"]
    assert TELEGRAM_ROOT_CONTEXT_REQUIREMENT not in coverage["missing"]
    assert coverage["warning_observation_count"] == 1
    assert coverage["observation_counts"]["detect-agent-intent"] == 2
    assert coverage["root_context_missing"] == {}
    assert coverage["root_context_pii_violations"] == {}
    assert coverage["cache_hit_without_retrieve_generation"] == 1


def test_check_required_trace_coverage_fails_when_root_context_is_unsanitized() -> None:
    mock_lf = MagicMock()
    mock_lf.api.trace.list.side_effect = [
        SimpleNamespace(data=[]),
    ]

    bad_root = _trace(
        "bad-root",
        input_data={
            "content_type": "text",
            "query_preview": "сырой вопрос",
            "query_len": 11,
            "route": "rag_query",
            "user": {"id": 123},
            "message": {"text": "raw"},
        },
    )
    bad_root.observations = [_obs("telegram-rag-query")]
    mock_lf.api.trace.get.return_value = bad_root
    mock_lf.api.trace.list.side_effect = [
        SimpleNamespace(data=[]),  # opportunistic voice-session check
        SimpleNamespace(data=[SimpleNamespace(id="bad-root")]),  # telegram root check
    ]

    with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
        coverage = check_required_trace_coverage(
            required_trace_names=[],
            required_observation_names=["telegram-rag-query"],
        )

    assert "telegram-rag-query" in coverage["present"]
    assert TELEGRAM_ROOT_CONTEXT_REQUIREMENT in coverage["missing"]
    assert coverage["root_context_missing"] == {"bad-root": ["query_hash"]}
    assert coverage["root_context_pii_violations"] == {"bad-root": ["message", "user"]}


def test_check_required_trace_coverage_litellm_proxy_traces_do_not_count_as_app_coverage() -> None:
    mock_lf = MagicMock()
    mock_lf.api.trace.list.side_effect = [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
    ]

    with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
        coverage = check_required_trace_coverage()

    assert "telegram-rag-query" in coverage["missing"]
    assert "telegram-rag-supervisor" in coverage["missing"]


def test_evaluate_go_no_go_fails_when_required_trace_family_missing() -> None:
    criteria = evaluate_go_no_go(
        {"cold": {}, "cache_hit": {}},
        [],
        orphan_rate=0.0,
        required_trace_coverage={
            "required": REQUIRED_TRACE_NAMES,
            "present": ["rag-api-query"],
            "missing": ["voice-session", "ingestion-cli-run"],
        },
    )

    gate = criteria["required_trace_families_present"]
    assert gate["passed"] is False
    assert "voice-session" in gate["actual"]
    assert "ingestion-cli-run" in gate["actual"]


def test_evaluate_go_no_go_passes_when_required_trace_families_present() -> None:
    criteria = evaluate_go_no_go(
        {"cold": {}, "cache_hit": {}},
        [],
        orphan_rate=0.0,
        required_trace_coverage={
            "required": REQUIRED_TRACE_NAMES,
            "present": REQUIRED_TRACE_NAMES,
            "missing": [],
        },
    )

    gate = criteria["required_trace_families_present"]
    assert gate["passed"] is True
    assert gate["actual"] == "all present"


def test_evaluate_go_no_go_treats_opportunistic_voice_session_as_nonblocking() -> None:
    criteria = evaluate_go_no_go(
        {"cold": {}, "cache_hit": {}},
        [],
        orphan_rate=0.0,
        required_trace_coverage={
            "required": ["rag-api-query", "ingestion-cli-run"],
            "present": ["rag-api-query", "ingestion-cli-run"],
            "missing": [],
            "opportunistic_missing": ["voice-session"],
            "opportunistic_present": [],
        },
    )

    gate = criteria["required_trace_families_present"]
    assert gate["passed"] is True
    assert "voice-session" in gate["actual"]
    assert "opportunistic" in gate["actual"].lower() or "missing" in gate["actual"].lower()
