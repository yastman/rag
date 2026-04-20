"""Focused tests for the Langfuse v4 evaluation examples."""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

from src.evaluation import langfuse_integration as integration


def _result(article_number: int) -> MagicMock:
    result = MagicMock()
    result.payload = {"article_number": article_number}
    return result


def _undecorated(func):
    return getattr(func, "__wrapped__", func)


class TestInitializeLangfuse:
    def test_initialize_langfuse_success(self) -> None:
        fake_client = MagicMock()

        with patch.object(integration, "Langfuse", return_value=fake_client) as mock_langfuse:
            client, enabled = integration.initialize_langfuse(
                host="http://localhost:3001",
                public_key="pk-test",
                secret_key="sk-test",
            )

        assert client is fake_client
        assert enabled is True
        mock_langfuse.assert_called_once_with(
            host="http://localhost:3001",
            public_key="pk-test",
            secret_key="sk-test",
        )

    def test_initialize_langfuse_disabled(self) -> None:
        client, enabled = integration.initialize_langfuse(enabled=False)

        assert client is None
        assert enabled is False


def test_trace_search_with_decorator_uses_v4_context_propagation() -> None:
    mock_lf = MagicMock()
    search_results = [_result(121), _result(115)]

    with (
        patch.object(integration, "get_client", return_value=mock_lf),
        patch.object(
            integration, "propagate_attributes", return_value=nullcontext()
        ) as mock_propagate,
        patch.object(integration.time, "time", side_effect=[100.0, 100.05]),
    ):
        results, metrics = _undecorated(integration.trace_search_with_decorator)(
            query="статья 121 УК",
            search_fn=lambda _: search_results,
            engine_name="dbsf_colbert",
            user_id="user-123",
            session_id="session-456",
            expected_article=121,
        )

    assert results == search_results
    assert metrics["precision_at_1"] == 1.0
    assert metrics["recall_at_10"] == 1.0
    mock_propagate.assert_called_once_with(
        user_id="user-123",
        session_id="session-456",
        tags=["search", "dbsf_colbert", "evaluation"],
        metadata={"engine": "dbsf_colbert", "expected_article": "121"},
    )
    input_update = mock_lf.update_current_span.call_args_list[0].kwargs
    output_update = mock_lf.update_current_span.call_args_list[1].kwargs
    assert input_update["input"] == {"query": "статья 121 УК", "engine": "dbsf_colbert"}
    assert output_update["output"]["num_results"] == 2
    mock_lf.score_current_trace.assert_any_call(name="precision_at_1", value=1.0)
    mock_lf.score_current_trace.assert_any_call(name="recall_at_10", value=1.0)


def test_trace_search_with_spans_uses_native_v4_observations() -> None:
    mock_lf = MagicMock()
    root_span = MagicMock()
    retrieval_span = MagicMock()
    eval_span = MagicMock()

    root_ctx = MagicMock()
    root_ctx.__enter__ = MagicMock(return_value=root_span)
    root_ctx.__exit__ = MagicMock(return_value=False)
    retrieval_ctx = MagicMock()
    retrieval_ctx.__enter__ = MagicMock(return_value=retrieval_span)
    retrieval_ctx.__exit__ = MagicMock(return_value=False)
    eval_ctx = MagicMock()
    eval_ctx.__enter__ = MagicMock(return_value=eval_span)
    eval_ctx.__exit__ = MagicMock(return_value=False)

    mock_lf.start_as_current_observation.return_value = root_ctx
    root_span.start_as_current_observation.side_effect = [retrieval_ctx, eval_ctx]
    search_results = [_result(121), _result(115)]

    with (
        patch.object(integration, "get_client", return_value=mock_lf),
        patch.object(
            integration, "propagate_attributes", return_value=nullcontext()
        ) as mock_propagate,
        patch.object(integration.time, "time", side_effect=[200.0, 200.02]),
    ):
        results, metrics = integration.trace_search_with_spans(
            query="статья 121 УК",
            search_fn=lambda _: search_results,
            engine_name="dbsf_colbert",
            user_id="user-123",
            session_id="session-456",
            expected_article=121,
        )

    assert results == search_results
    assert metrics["latency_ms"] == pytest.approx(20.0)
    mock_lf.start_as_current_observation.assert_called_once_with(
        as_type="span",
        name="rag-search",
    )
    mock_propagate.assert_called_once_with(
        user_id="user-123",
        session_id="session-456",
        tags=["search", "dbsf_colbert"],
        metadata={"engine": "dbsf_colbert", "expected_article": "121"},
    )
    root_span.update.assert_called_once_with(
        input={"query": "статья 121 УК", "engine": "dbsf_colbert"},
        metadata={"engine": "dbsf_colbert", "expected_article": "121"},
    )
    root_span.start_as_current_observation.assert_any_call(
        as_type="span",
        name="retrieval-dbsf_colbert",
        input={"query": "статья 121 УК"},
    )
    root_span.start_as_current_observation.assert_any_call(
        as_type="span",
        name="evaluation",
        input={"expected_article": 121},
    )
    eval_span.score.assert_any_call(name="precision_at_1", value=1.0)
    eval_span.score.assert_any_call(name="recall_at_10", value=1.0)


def test_trace_search_with_spans_skips_evaluation_without_expected_article() -> None:
    mock_lf = MagicMock()
    root_span = MagicMock()
    retrieval_span = MagicMock()

    root_ctx = MagicMock()
    root_ctx.__enter__ = MagicMock(return_value=root_span)
    root_ctx.__exit__ = MagicMock(return_value=False)
    retrieval_ctx = MagicMock()
    retrieval_ctx.__enter__ = MagicMock(return_value=retrieval_span)
    retrieval_ctx.__exit__ = MagicMock(return_value=False)

    mock_lf.start_as_current_observation.return_value = root_ctx
    root_span.start_as_current_observation.return_value = retrieval_ctx

    with (
        patch.object(integration, "get_client", return_value=mock_lf),
        patch.object(integration, "propagate_attributes", return_value=nullcontext()),
        patch.object(integration.time, "time", side_effect=[300.0, 300.01]),
    ):
        _, metrics = integration.trace_search_with_spans(
            query="test query",
            search_fn=lambda _: [],
            engine_name="baseline",
            user_id="user-123",
        )

    assert metrics["latency_ms"] == pytest.approx(10.0)
    assert metrics["num_results"] == 0
    assert root_span.start_as_current_observation.call_count == 1
