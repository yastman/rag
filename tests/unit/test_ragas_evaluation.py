"""Unit tests for src/evaluation/ragas_evaluation.py.

Tests RAGAS v0.4 integration, Langfuse v4 SDK scoring, and threshold enforcement.

Issue #2211: ``_log_ragas_scores_to_langfuse`` was previously written against
the Langfuse Python v3 API (``langfuse_client.trace(...)``, ``trace.score(...)``,
``trace.update(...)``). Those methods do not exist on Langfuse v4 SDK
(``langfuse>=4.0.0,<5.0`` per ``pyproject.toml``), so any real RAGAS run raised
``AttributeError`` and the function silently returned ``None`` via the broad
``except`` block. These tests pin the v4 contract:

* uses ``langfuse_client.start_as_current_observation(as_type="span", ...)`` as
  context manager;
* sets trace attributes via ``propagate_attributes(session_id=..., tags=...)``;
* publishes scores via ``langfuse_client.score_current_trace(...)``;
* updates trace I/O via ``observation.update(input=..., output=...)``;
* calls ``langfuse_client.flush()`` once at the end.
"""

from contextlib import nullcontext
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_v4_mocks():
    """Build a mock Langfuse v4 client + observation context manager.

    Returns ``(mock_client, mock_obs)`` where:

    * ``mock_client.start_as_current_observation(...)`` returns a context
      manager whose ``__enter__`` yields ``mock_obs``;
    * ``mock_client.score_current_trace(name=, value=, ...)`` is a plain
      ``MagicMock`` capturing every score call;
    * ``mock_obs.update(...)`` captures the final I/O update.
    """
    mock_obs = MagicMock(name="observation")
    mock_obs.trace_id = "trace-v4-abc123"

    mock_client = MagicMock(name="langfuse_v4_client")
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_obs)
    cm.__exit__ = MagicMock(return_value=False)
    mock_client.start_as_current_observation.return_value = cm
    return mock_client, mock_obs


def _score_calls(mock_client):
    """Return list of (name, value) tuples published via ``score_current_trace``."""
    return [
        (call.kwargs.get("name"), call.kwargs.get("value"))
        for call in mock_client.score_current_trace.call_args_list
    ]


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_faithfulness_threshold(self):
        assert FAITHFULNESS_THRESHOLD == 0.80

    def test_context_precision_threshold(self):
        assert CONTEXT_PRECISION_THRESHOLD == 0.80

    def test_context_recall_threshold(self):
        assert CONTEXT_RECALL_THRESHOLD == 0.90

    def test_answer_relevancy_threshold(self):
        assert ANSWER_RELEVANCY_THRESHOLD == 0.80


# ---------------------------------------------------------------------------
# _get_langfuse_client
# ---------------------------------------------------------------------------


class TestGetLangfuseClient:
    def test_returns_none_when_tracing_disabled(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _get_langfuse_client() is None

    def test_returns_none_when_tracing_explicitly_disabled(self):
        with patch.dict("os.environ", {"LANGFUSE_TRACING_ENABLED": "false"}):
            assert _get_langfuse_client() is None

    def test_creates_client_when_enabled(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "LANGFUSE_TRACING_ENABLED": "true",
                    "LANGFUSE_HOST": "http://test:3001",
                    "LANGFUSE_PUBLIC_KEY": "pk-test",
                    "LANGFUSE_SECRET_KEY": "sk-test",
                },
            ),
            patch("langfuse.Langfuse") as mock_langfuse_class,
        ):
            mock_client = MagicMock()
            mock_langfuse_class.return_value = mock_client

            assert _get_langfuse_client() is mock_client
            mock_langfuse_class.assert_called_once_with(
                host="http://test:3001",
                public_key="pk-test",
                secret_key="sk-test",
            )


# ---------------------------------------------------------------------------
# _log_ragas_scores_to_langfuse — v4 SDK contract
# ---------------------------------------------------------------------------


class TestLogRagasScoresToLangfuseV4Contract:
    """Pin the v4 SDK contract for ragas score publishing (#2211)."""

    def test_returns_none_when_client_is_none(self):
        assert (
            _log_ragas_scores_to_langfuse(
                langfuse_client=None,
                metrics={"faithfulness": 0.85},
                session_id="test-session",
            )
            is None
        )

    def test_uses_start_as_current_observation_context_manager(self):
        """v4: must open a span via ``start_as_current_observation`` (not v3 ``trace(...)``)."""
        mock_client, _mock_obs = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85},
                session_id="test-session",
            )

        # v4 contract: start_as_current_observation called exactly once
        assert mock_client.start_as_current_observation.call_count == 1
        kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert kwargs.get("as_type") == "span"
        assert kwargs.get("name") == "ragas-evaluation"

        # v3 ``trace(...)`` method is forbidden
        assert not mock_client.trace.called, (
            "v3 ``langfuse_client.trace(...)`` API was removed in Langfuse v4 SDK; "
            "use ``start_as_current_observation`` instead (#2211)."
        )

    def test_uses_propagate_attributes_for_session_and_tags(self):
        """v4: session_id/tags travel via ``propagate_attributes(...)`` context manager."""
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ) as mock_propagate:
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85},
                session_id="ragas-2026-05-28",
            )

        mock_propagate.assert_called_once()
        kw = mock_propagate.call_args.kwargs
        assert kw.get("session_id") == "ragas-2026-05-28"
        assert "ragas" in kw.get("tags", [])
        assert "evaluation" in kw.get("tags", [])

    def test_publishes_all_four_ragas_metrics_via_score_current_trace(self):
        """v4: each RAGAS metric must be published via ``score_current_trace``."""
        mock_client, _ = _build_v4_mocks()

        metrics = {
            "faithfulness": 0.85,
            "context_precision": 0.82,
            "context_recall": 0.91,
            "answer_relevancy": 0.88,
        }
        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics=metrics,
                session_id="s1",
            )

        published = dict(_score_calls(mock_client))
        for ragas_metric, value in metrics.items():
            assert ragas_metric in published, (
                f"{ragas_metric} must be published via ``score_current_trace``"
            )
            assert published[ragas_metric] == value

    def test_publishes_acceptance_passed_score(self):
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85},
                session_id="s1",
            )

        published = dict(_score_calls(mock_client))
        assert published.get("acceptance_passed") == 1.0

    def test_publishes_acceptance_failed_when_faithfulness_below_threshold(self):
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.75},
                session_id="s1",
            )

        published = dict(_score_calls(mock_client))
        assert published.get("acceptance_passed") == 0.0

    def test_publishes_eval_duration_when_present(self):
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85, "eval_duration_seconds": 42.5},
                session_id="s1",
            )

        published = dict(_score_calls(mock_client))
        assert published.get("eval_duration_seconds") == 42.5

    def test_publishes_queries_evaluated_when_present(self):
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85, "queries_evaluated": 55},
                session_id="s1",
            )

        published = dict(_score_calls(mock_client))
        assert published.get("queries_evaluated") == 55.0

    def test_updates_observation_with_input_and_output(self):
        """v4: trace I/O must be written via ``observation.update(input=, output=)``."""
        mock_client, mock_obs = _build_v4_mocks()

        metrics = {"faithfulness": 0.85, "context_precision": 0.82}
        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics=metrics,
                session_id="s1",
            )

        assert mock_obs.update.called, "observation.update(...) must be called"
        update_kwargs = mock_obs.update.call_args.kwargs
        assert "output" in update_kwargs
        assert update_kwargs["output"]["metrics"] == metrics
        assert update_kwargs["output"]["acceptance_passed"] is True

    def test_flushes_client_after_logging(self):
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85},
                session_id="s1",
            )

        mock_client.flush.assert_called_once()

    def test_returns_trace_id_from_observation(self):
        mock_client, mock_obs = _build_v4_mocks()
        mock_obs.trace_id = "trace-v4-xyz789"

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            result = _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": 0.85},
                session_id="s1",
            )

        assert result == "trace-v4-xyz789"

    def test_handles_langfuse_errors_gracefully(self):
        mock_client = MagicMock()
        mock_client.start_as_current_observation.side_effect = Exception("Connection failed")

        result = _log_ragas_scores_to_langfuse(
            langfuse_client=mock_client,
            metrics={"faithfulness": 0.85},
            session_id="s1",
        )

        assert result is None


class TestRAGASMetricsFormat:
    def test_complete_metrics_dict_publishes_seven_scores(self):
        """Full metrics dict produces 7 scores: 4 RAGAS + duration + queries + acceptance."""
        mock_client, _ = _build_v4_mocks()

        complete_metrics = {
            "faithfulness": 0.85,
            "context_precision": 0.82,
            "context_recall": 0.91,
            "answer_relevancy": 0.88,
            "eval_duration_seconds": 123.4,
            "queries_evaluated": 55,
        }
        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics=complete_metrics,
                session_id="s1",
            )

        # 4 RAGAS + eval_duration + queries_evaluated + acceptance_passed = 7
        assert mock_client.score_current_trace.call_count == 7


class TestThresholdEnforcement:
    @pytest.mark.parametrize(
        "faithfulness,expected_passed",
        [
            (0.80, True),
            (0.81, True),
            (0.95, True),
            (0.79, False),
            (0.50, False),
            (0.0, False),
        ],
    )
    def test_acceptance_based_on_faithfulness(self, faithfulness, expected_passed):
        mock_client, _ = _build_v4_mocks()

        with patch(
            "src.evaluation.ragas_evaluation.propagate_attributes",
            return_value=nullcontext(),
        ):
            _log_ragas_scores_to_langfuse(
                langfuse_client=mock_client,
                metrics={"faithfulness": faithfulness},
                session_id="s1",
            )

        published = dict(_score_calls(mock_client))
        expected_value = 1.0 if expected_passed else 0.0
        assert published.get("acceptance_passed") == expected_value
