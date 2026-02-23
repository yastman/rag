"""Unit tests for required trace-family coverage gate in validate_traces."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts.validate_traces import (
    REQUIRED_TRACE_NAMES,
    check_required_trace_coverage,
    evaluate_go_no_go,
)


def test_check_required_trace_coverage_marks_missing_trace_families() -> None:
    mock_lf = MagicMock()
    mock_lf.api.trace.list.side_effect = [
        SimpleNamespace(data=[SimpleNamespace(id="trace-api")]),
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[]),
    ]

    with patch("scripts.validate_traces.Langfuse", return_value=mock_lf):
        coverage = check_required_trace_coverage()

    assert coverage["present"] == ["rag-api-query"]
    assert set(coverage["missing"]) == {"voice-session", "ingestion-cli-run"}


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
