"""Unit tests for Langfuse E2E trace validator."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from scripts.e2e.langfuse_trace_validator import validate_latest_trace


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
    mock_trace.observations = [
        # Current LangGraph pipeline spans
        type(
            "Obs",
            (),
            {
                "name": "telegram-rag-query",
                "input": {"query_hash": "abc123"},
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
    """Validator should fail when root observation input lacks query_hash."""
    mock_trace = MagicMock()
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
