"""Unit tests for Langfuse E2E trace validator."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from scripts.e2e.langfuse_trace_validator import validate_latest_trace, wait_for_trace


def _score(name: str, value: object):
    return type("Score", (), {"name": name, "value": value})


def _obs(name: str):
    return type("Obs", (), {"name": name})


def _required_scores(**overrides: object) -> list[type]:
    values: dict[str, object] = {
        "query_type": 1.0,
        "latency_total_ms": 1500.0,
        "semantic_cache_hit": True,
        "embeddings_cache_hit": False,
        "search_cache_hit": False,
        "rerank_applied": False,
        "rerank_cache_hit": False,
        "results_count": 0.0,
        "no_results": True,
        "llm_used": False,
    }
    values.update(overrides)
    return [_score(name, value) for name, value in values.items()]


@pytest.fixture
def mock_langfuse_configured():
    """Mock Langfuse configuration check."""
    with patch("scripts.e2e.langfuse_trace_validator._langfuse_is_configured", return_value=True):
        yield


@pytest.fixture
def mock_wait_for_trace():
    """Mock wait_for_trace to return a trace ID."""
    with patch("scripts.e2e.langfuse_trace_validator.wait_for_trace", return_value="test-trace-id"):
        yield


def test_validator_accepts_current_langgraph_span_names(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    """Validator should accept current LangGraph node span names.

    Current contract (as of 2026-02-13):
    - telegram-rag-query (trace name)
    - node-classify
    - node-cache-check
    - node-retrieve
    - node-grade
    - node-rerank
    - node-generate
    - node-cache-store
    - node-respond
    """
    # Mock Langfuse trace with current LangGraph span names
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        # Current LangGraph pipeline spans
        type(
            "Obs",
            (),
            {
                "name": "telegram-rag-query",
            },
        ),
        type("Obs", (), {"name": "telegram-rag-supervisor"}),
        type("Obs", (), {"name": "node-classify"}),
        type("Obs", (), {"name": "node-cache-check"}),
        type("Obs", (), {"name": "node-retrieve"}),
        type("Obs", (), {"name": "node-grade"}),
        type("Obs", (), {"name": "node-rerank"}),
        type("Obs", (), {"name": "node-generate"}),
        type("Obs", (), {"name": "node-cache-store"}),
        type("Obs", (), {"name": "node-respond"}),
    ]

    # Mock required scores
    mock_trace.scores = [
        type("Score", (), {"name": "query_type", "value": 1.0}),
        type("Score", (), {"name": "latency_total_ms", "value": 1500.0}),
        type("Score", (), {"name": "semantic_cache_hit", "value": False}),
        type("Score", (), {"name": "embeddings_cache_hit", "value": False}),
        type("Score", (), {"name": "search_cache_hit", "value": False}),
        type("Score", (), {"name": "rerank_applied", "value": True}),
        type("Score", (), {"name": "rerank_cache_hit", "value": False}),
        type("Score", (), {"name": "results_count", "value": 3.0}),
        type("Score", (), {"name": "no_results", "value": False}),
        type("Score", (), {"name": "llm_used", "value": True}),
    ]

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        mock_client = MockLangfuse.return_value
        mock_client.api.trace.get.return_value = mock_trace

        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
        )

    # Should pass validation with current span names
    assert result.ok, (
        f"Validation failed: missing_spans={result.missing_spans}, missing_scores={result.missing_scores}"
    )
    assert not result.missing_spans, f"Expected no missing spans, got: {result.missing_spans}"
    assert not result.missing_scores, f"Expected no missing scores, got: {result.missing_scores}"


def test_validator_accepts_telegram_message_root_with_rag_observations(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    """Validator should accept telegram-message root with RAG observations and proper root context."""
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        # Root observation with proper context
        type(
            "Obs",
            (),
            {
                "name": "telegram-message",
                "input": {"query_hash": "abc123", "query_preview": "test query"},
                "output": {"answer_hash": "def456", "response_preview": "test answer"},
            },
        ),
        type("Obs", (), {"name": "telegram-rag-query"}),
        type("Obs", (), {"name": "telegram-rag-supervisor"}),
        # RAG pipeline spans
        type("Obs", (), {"name": "node-classify"}),
        type("Obs", (), {"name": "node-cache-check"}),
        type("Obs", (), {"name": "node-retrieve"}),
        type("Obs", (), {"name": "node-grade"}),
        type("Obs", (), {"name": "node-rerank"}),
        type("Obs", (), {"name": "node-generate"}),
        type("Obs", (), {"name": "node-cache-store"}),
        type("Obs", (), {"name": "node-respond"}),
    ]

    # Mock required scores
    mock_trace.scores = [
        type("Score", (), {"name": "query_type", "value": 1.0}),
        type("Score", (), {"name": "latency_total_ms", "value": 1500.0}),
        type("Score", (), {"name": "semantic_cache_hit", "value": False}),
        type("Score", (), {"name": "embeddings_cache_hit", "value": False}),
        type("Score", (), {"name": "search_cache_hit", "value": False}),
        type("Score", (), {"name": "rerank_applied", "value": True}),
        type("Score", (), {"name": "rerank_cache_hit", "value": False}),
        type("Score", (), {"name": "results_count", "value": 3.0}),
        type("Score", (), {"name": "no_results", "value": False}),
        type("Score", (), {"name": "llm_used", "value": True}),
    ]

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        mock_client = MockLangfuse.return_value
        mock_client.api.trace.get.return_value = mock_trace

        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert result.ok, (
        f"Validation failed: missing_spans={result.missing_spans}, missing_scores={result.missing_scores}"
    )
    assert not result.missing_spans, f"Expected no missing spans, got: {result.missing_spans}"
    assert not result.missing_scores, f"Expected no missing scores, got: {result.missing_scores}"


def test_validator_fails_when_root_input_is_missing(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    """Validator should fail when trace-level input lacks query_hash (Blocker 2)."""
    mock_trace = MagicMock()
    # trace.input lacks query_hash — root_input marker expected
    mock_trace.input = {"query_preview": "test query"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        # Root observation missing query_hash in input
        type(
            "Obs",
            (),
            {
                "name": "telegram-message",
                "input": {"query_preview": "test query"},
                "output": {"answer_hash": "def456"},
            },
        ),
        type("Obs", (), {"name": "node-classify"}),
        type("Obs", (), {"name": "node-cache-check"}),
        type("Obs", (), {"name": "node-retrieve"}),
        type("Obs", (), {"name": "node-grade"}),
        type("Obs", (), {"name": "node-rerank"}),
        type("Obs", (), {"name": "node-generate"}),
        type("Obs", (), {"name": "node-cache-store"}),
        type("Obs", (), {"name": "node-respond"}),
    ]

    # Mock required scores
    mock_trace.scores = [
        type("Score", (), {"name": "query_type", "value": 1.0}),
        type("Score", (), {"name": "latency_total_ms", "value": 1500.0}),
        type("Score", (), {"name": "semantic_cache_hit", "value": False}),
        type("Score", (), {"name": "embeddings_cache_hit", "value": False}),
        type("Score", (), {"name": "search_cache_hit", "value": False}),
        type("Score", (), {"name": "rerank_applied", "value": True}),
        type("Score", (), {"name": "rerank_cache_hit", "value": False}),
        type("Score", (), {"name": "results_count", "value": 3.0}),
        type("Score", (), {"name": "no_results", "value": False}),
        type("Score", (), {"name": "llm_used", "value": True}),
    ]

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        mock_client = MockLangfuse.return_value
        mock_client.api.trace.get.return_value = mock_trace

        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok, "Expected validation to fail due to missing root_input"
    assert "root_input" in result.missing_spans, (
        f"Expected root_input in missing_spans, got: {result.missing_spans}"
    )
    # root_output should be present since answer_hash is provided
    assert "root_output" not in result.missing_spans, (
        f"Did not expect root_output in missing_spans, got: {result.missing_spans}"
    )


def test_validator_accepts_cache_check_alias_for_node_cache_check(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = _required_scores(semantic_cache_hit=True)

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert result.ok, (
        f"Validation failed: missing_spans={result.missing_spans}, "
        f"missing_scores={result.missing_scores}"
    )
    assert "node-cache-check" not in result.missing_spans


def test_validator_fails_when_query_type_score_is_non_numeric(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = _required_scores(query_type="GENERAL")

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok
    assert "query_type" in result.missing_scores


def test_validator_fails_when_query_type_score_is_missing(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"answer_hash": "def456"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = [score for score in _required_scores() if score.name != "query_type"]

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=True,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok
    assert "query_type" in result.missing_scores


def test_validator_fails_when_root_output_is_missing(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    mock_trace = MagicMock()
    mock_trace.input = {"query_hash": "abc123"}
    mock_trace.output = {"response_preview": "test answer"}
    mock_trace.observations = [
        _obs("telegram-rag-query"),
        _obs("telegram-rag-supervisor"),
        _obs("cache-check"),
    ]
    mock_trace.scores = _required_scores()

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        MockLangfuse.return_value.api.trace.get.return_value = mock_trace
        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok
    assert "root_output" in result.missing_spans


# ---------------------------------------------------------------------------
# Blocker 3: wait_for_trace multi-name support
# ---------------------------------------------------------------------------


def test_wait_for_trace_single_name_backward_compat():
    """Single string trace_name still works (backward-compatible)."""
    with patch("scripts.e2e.langfuse_trace_validator._langfuse_is_configured", return_value=True):
        with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
            mock_client = MockLangfuse.return_value
            mock_trace = MagicMock()
            mock_trace.id = "trace-x"
            mock_client.api.trace.list.return_value.data = [mock_trace]

            result = wait_for_trace(
                started_at=datetime.now(),
                trace_name="telegram-rag-query",
            )

    assert result == "trace-x"


def test_wait_for_trace_multi_name_finds_match():
    """Multiple trace names — returns first hit across name list."""
    with patch("scripts.e2e.langfuse_trace_validator._langfuse_is_configured", return_value=True):
        with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
            mock_client = MockLangfuse.return_value

            def list_side_effect(name, tags, from_timestamp, order_by, limit):
                page = MagicMock()
                page.data = []
                return page

            # Return trace only for second name
            def list_for_second(name, tags, from_timestamp, order_by, limit):
                page = MagicMock()
                if name == "telegram-message":
                    t = MagicMock()
                    t.id = "trace-msg"
                    page.data = [t]
                else:
                    page.data = []
                return page

            mock_client.api.trace.list.side_effect = list_for_second

            result = wait_for_trace(
                started_at=datetime.now(),
                trace_name=["telegram-rag-voice", "telegram-message"],
            )

    assert result == "trace-msg"
