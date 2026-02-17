"""Unit tests for src/evaluation/ragas_evaluation.py.

Tests RAGAS v0.4 integration, Langfuse scoring, and threshold enforcement.
"""

from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("ragas", reason="ragas not installed (eval extra)")
pytestmark = pytest.mark.requires_extras

from src.evaluation.ragas_evaluation import (
    ANSWER_RELEVANCY_THRESHOLD,
    CONTEXT_PRECISION_THRESHOLD,
    CONTEXT_RECALL_THRESHOLD,
    FAITHFULNESS_THRESHOLD,
    _get_langfuse_client,
    _log_ragas_scores_to_langfuse,
)


class TestThresholds:
    """Test threshold constants are correctly set."""

    def test_faithfulness_threshold(self):
        """Test faithfulness threshold is 0.80."""
        assert FAITHFULNESS_THRESHOLD == 0.80

    def test_context_precision_threshold(self):
        """Test context precision threshold is 0.80."""
        assert CONTEXT_PRECISION_THRESHOLD == 0.80

    def test_context_recall_threshold(self):
        """Test context recall threshold is 0.90."""
        assert CONTEXT_RECALL_THRESHOLD == 0.90

    def test_answer_relevancy_threshold(self):
        """Test answer relevancy threshold is 0.80."""
        assert ANSWER_RELEVANCY_THRESHOLD == 0.80


class TestGetLangfuseClient:
    """Test _get_langfuse_client function."""

    def test_returns_none_when_tracing_disabled(self):
        """Test returns None when LANGFUSE_TRACING_ENABLED is not set."""
        with patch.dict("os.environ", {}, clear=True):
            result = _get_langfuse_client()
            assert result is None

    def test_returns_none_when_tracing_explicitly_disabled(self):
        """Test returns None when LANGFUSE_TRACING_ENABLED is false."""
        with patch.dict("os.environ", {"LANGFUSE_TRACING_ENABLED": "false"}):
            result = _get_langfuse_client()
            assert result is None

    def test_creates_client_when_enabled(self):
        """Test creates Langfuse client when tracing is enabled."""
        # Patch at the point of import inside the function
        with patch.dict(
            "os.environ",
            {
                "LANGFUSE_TRACING_ENABLED": "true",
                "LANGFUSE_HOST": "http://test:3001",
                "LANGFUSE_PUBLIC_KEY": "pk-test",
                "LANGFUSE_SECRET_KEY": "sk-test",
            },
        ):
            with patch("langfuse.Langfuse") as mock_langfuse_class:
                mock_client = MagicMock()
                mock_langfuse_class.return_value = mock_client

                result = _get_langfuse_client()

                # Verify Langfuse was called with correct params
                mock_langfuse_class.assert_called_once_with(
                    host="http://test:3001",
                    public_key="pk-test",
                    secret_key="sk-test",
                )
                assert result == mock_client


class TestLogRagasScoresToLangfuse:
    """Test _log_ragas_scores_to_langfuse function."""

    def test_returns_none_when_client_is_none(self):
        """Test returns None when langfuse_client is None."""
        result = _log_ragas_scores_to_langfuse(
            langfuse_client=None,
            metrics={"faithfulness": 0.85},
            session_id="test-session",
        )
        assert result is None

    def test_logs_all_ragas_metrics(self):
        """Test all 4 RAGAS metrics are logged to Langfuse."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-123"
        mock_client.trace.return_value = mock_trace

        metrics = {
            "faithfulness": 0.85,
            "context_precision": 0.82,
            "context_recall": 0.91,
            "answer_relevancy": 0.88,
        }

        result = _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        assert result == "trace-123"

        # Verify trace was created
        mock_client.trace.assert_called_once()
        call_kwargs = mock_client.trace.call_args.kwargs
        assert call_kwargs["session_id"] == "test-session"
        assert "ragas" in call_kwargs["tags"]

        # Verify all 4 RAGAS metrics + acceptance_passed were scored
        # 4 RAGAS metrics + acceptance_passed = 5 score calls minimum
        assert mock_trace.score.call_count >= 5

    def test_logs_eval_duration_when_present(self):
        """Test eval_duration_seconds is logged when present."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-456"
        mock_client.trace.return_value = mock_trace

        metrics = {
            "faithfulness": 0.85,
            "eval_duration_seconds": 42.5,
        }

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        # Check that eval_duration_seconds was logged
        score_calls = mock_trace.score.call_args_list
        duration_calls = [c for c in score_calls if c.kwargs.get("name") == "eval_duration_seconds"]
        assert len(duration_calls) == 1
        assert duration_calls[0].kwargs["value"] == 42.5

    def test_logs_queries_evaluated_when_present(self):
        """Test queries_evaluated is logged when present."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-789"
        mock_client.trace.return_value = mock_trace

        metrics = {
            "faithfulness": 0.85,
            "queries_evaluated": 55,
        }

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        score_calls = mock_trace.score.call_args_list
        queries_calls = [c for c in score_calls if c.kwargs.get("name") == "queries_evaluated"]
        assert len(queries_calls) == 1
        assert queries_calls[0].kwargs["value"] == 55.0

    def test_acceptance_passed_when_faithfulness_meets_threshold(self):
        """Test acceptance_passed=1.0 when faithfulness >= 0.80."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-pass"
        mock_client.trace.return_value = mock_trace

        metrics = {"faithfulness": 0.85}  # > 0.80

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        score_calls = mock_trace.score.call_args_list
        acceptance_calls = [c for c in score_calls if c.kwargs.get("name") == "acceptance_passed"]
        assert len(acceptance_calls) == 1
        assert acceptance_calls[0].kwargs["value"] == 1.0

    def test_acceptance_failed_when_faithfulness_below_threshold(self):
        """Test acceptance_passed=0.0 when faithfulness < 0.80."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-fail"
        mock_client.trace.return_value = mock_trace

        metrics = {"faithfulness": 0.75}  # < 0.80

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        score_calls = mock_trace.score.call_args_list
        acceptance_calls = [c for c in score_calls if c.kwargs.get("name") == "acceptance_passed"]
        assert len(acceptance_calls) == 1
        assert acceptance_calls[0].kwargs["value"] == 0.0

    def test_trace_output_includes_metrics_and_acceptance(self):
        """Test trace output contains metrics and acceptance_passed."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-output"
        mock_client.trace.return_value = mock_trace

        metrics = {"faithfulness": 0.85, "context_precision": 0.82}

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        # Verify trace.update was called with output
        mock_trace.update.assert_called_once()
        update_kwargs = mock_trace.update.call_args.kwargs
        assert "output" in update_kwargs
        assert update_kwargs["output"]["metrics"] == metrics
        assert update_kwargs["output"]["acceptance_passed"] is True

    def test_flushes_client_after_logging(self):
        """Test langfuse client is flushed after logging."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-flush"
        mock_client.trace.return_value = mock_trace

        metrics = {"faithfulness": 0.85}

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        mock_client.flush.assert_called_once()

    def test_handles_langfuse_errors_gracefully(self):
        """Test returns None when Langfuse raises an exception."""
        mock_client = MagicMock()
        mock_client.trace.side_effect = Exception("Connection failed")

        result = _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics={"faithfulness": 0.85},
            session_id="test-session",
        )

        assert result is None


class TestRAGASMetricsFormat:
    """Test that metrics dict follows expected format."""

    def test_all_expected_metrics_can_be_logged(self):
        """Test complete metrics dict can be logged without errors."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-complete"
        mock_client.trace.return_value = mock_trace

        # Complete metrics dict as returned by RAGASEvaluator
        complete_metrics = {
            "faithfulness": 0.85,
            "context_precision": 0.82,
            "context_recall": 0.91,
            "answer_relevancy": 0.88,
            "eval_duration_seconds": 123.4,
            "queries_evaluated": 55,
        }

        result = _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=complete_metrics,
            session_id="test-session",
        )

        assert result == "trace-complete"

        # Should have logged 7 scores:
        # 4 RAGAS metrics + eval_duration + queries_evaluated + acceptance_passed
        assert mock_trace.score.call_count == 7


class TestThresholdEnforcement:
    """Test threshold enforcement in acceptance criteria."""

    @pytest.mark.parametrize(
        "faithfulness,expected_passed",
        [
            (0.80, True),  # Exactly at threshold
            (0.81, True),  # Above threshold
            (0.95, True),  # Well above threshold
            (0.79, False),  # Just below threshold
            (0.50, False),  # Well below threshold
            (0.0, False),  # Zero
        ],
    )
    def test_acceptance_based_on_faithfulness(self, faithfulness, expected_passed):
        """Test acceptance_passed correctly reflects faithfulness threshold."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_trace.id = "trace-param"
        mock_client.trace.return_value = mock_trace

        metrics = {"faithfulness": faithfulness}

        _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics=metrics,
            session_id="test-session",
        )

        # Find acceptance_passed score call
        score_calls = mock_trace.score.call_args_list
        acceptance_calls = [c for c in score_calls if c.kwargs.get("name") == "acceptance_passed"]
        assert len(acceptance_calls) == 1

        expected_value = 1.0 if expected_passed else 0.0
        assert acceptance_calls[0].kwargs["value"] == expected_value
