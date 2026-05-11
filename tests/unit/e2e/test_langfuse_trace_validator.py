"""Unit tests for Langfuse E2E trace validator."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from scripts.e2e.langfuse_trace_validator import validate_latest_trace, wait_for_trace


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


# ---------------------------------------------------------------------------
# Alias group: node-cache-check / cache-check
# ---------------------------------------------------------------------------


def _sanitized_observed_trace(*, include_cache_check_alias: bool = False):
    """Build a mock trace shaped like sanitized local audit observations.

    Based on artifact evidence (root_input keys present, observed cache names,
    required score names present). No raw payload values.

    Scores are chosen so only the ``node-cache-check`` branch requirement is
    triggered, keeping the alias-group test focused.
    """
    mock_trace = MagicMock()
    mock_trace.input = {
        "action": "message",
        "content_type": "text",
        "query_hash": "abc123",
        "query_len": 24,
        "query_preview": "test query",
    }
    mock_trace.output = {"answer_hash": "def456"}

    observations = [
        type("Obs", (), {"name": "telegram-message"}),
        type("Obs", (), {"name": "telegram-rag-query"}),
        type("Obs", (), {"name": "telegram-rag-supervisor"}),
        type("Obs", (), {"name": "client-direct-pipeline"}),
        type("Obs", (), {"name": "classify-query"}),
        type("Obs", (), {"name": "cache-semantic-check"}),
        type("Obs", (), {"name": "cache-exact-get"}),
        type("Obs", (), {"name": "cache-search-get"}),
        type("Obs", (), {"name": "cache-embedding-get"}),
        type("Obs", (), {"name": "grade-documents"}),
        type("Obs", (), {"name": "hybrid-retrieve"}),
        type("Obs", (), {"name": "service-generate-response"}),
        type("Obs", (), {"name": "history-save"}),
    ]

    if include_cache_check_alias:
        observations.append(type("Obs", (), {"name": "cache-check"}))

    # Observations are unordered; shuffle alias into middle of list.
    mock_trace.observations = observations

    # Scores configured so ``semantic_cache_hit=True`` short-circuits the
    # retrieval/generation branch requirements, leaving only
    # ``node-cache-check`` as the branch-required observation.
    mock_trace.scores = [
        type("Score", (), {"name": "query_type", "value": 1.0}),
        type("Score", (), {"name": "latency_total_ms", "value": 1500.0}),
        type("Score", (), {"name": "semantic_cache_hit", "value": True}),
        type("Score", (), {"name": "embeddings_cache_hit", "value": False}),
        type("Score", (), {"name": "search_cache_hit", "value": False}),
        type("Score", (), {"name": "rerank_applied", "value": False}),
        type("Score", (), {"name": "rerank_cache_hit", "value": False}),
        type("Score", (), {"name": "results_count", "value": 0.0}),
        type("Score", (), {"name": "no_results", "value": True}),
        type("Score", (), {"name": "llm_used", "value": False}),
    ]
    return mock_trace


def test_validator_fails_when_cache_check_alias_group_unsatisfied(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    """Without node-cache-check or cache-check, validation must fail (strict)."""
    mock_trace = _sanitized_observed_trace(include_cache_check_alias=False)

    with patch("scripts.e2e.langfuse_trace_validator.Langfuse") as MockLangfuse:
        mock_client = MockLangfuse.return_value
        mock_client.api.trace.get.return_value = mock_trace

        result = validate_latest_trace(
            started_at=datetime.now(),
            should_skip_rag=False,
            is_command=False,
            scenario_kind="text_rag",
        )

    assert not result.ok, "Expected validation to fail without cache-check alias"
    assert "node-cache-check" in result.missing_spans, (
        f"Expected node-cache-check in missing_spans, got: {result.missing_spans}"
    )


def test_validator_passes_with_cache_check_alias(
    mock_langfuse_configured,
    mock_wait_for_trace,
):
    """cache-check satisfies the node-cache-check requirement via alias group."""
    mock_trace = _sanitized_observed_trace(include_cache_check_alias=True)

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
    assert "node-cache-check" not in result.missing_spans, (
        f"Did not expect node-cache-check in missing_spans, got: {result.missing_spans}"
    )
