"""Unit tests for rerank_node."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.nodes.rerank import rerank_node


@pytest.mark.asyncio
async def test_rerank_node_returns_empty_for_no_documents() -> None:
    runtime = SimpleNamespace(context={"cache": None, "reranker": None})
    metrics = MagicMock()
    with patch("telegram_bot.graph.nodes.rerank.PipelineMetrics.get", return_value=metrics):
        result = await rerank_node(
            {"documents": [], "messages": [], "llm_call_count": 0, "latency_stages": {}},
            runtime,
        )

    assert result["documents"] == []
    assert result["rerank_applied"] is False
    assert result["rerank_cache_hit"] is False
    assert result["llm_call_count"] == 1
    assert "rerank" in result["latency_stages"]
    metrics.record.assert_called_once()


@pytest.mark.asyncio
async def test_rerank_node_uses_perform_rerank_result() -> None:
    runtime = SimpleNamespace(context={"cache": object(), "reranker": object()})
    state = {
        "documents": [{"score": 0.1}, {"score": 0.9}],
        "messages": [{"content": "query"}],
        "llm_call_count": 2,
        "latency_stages": {},
    }

    with (
        patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank",
            AsyncMock(return_value=([{"score": 0.9}], True, False)),
        ),
        patch("telegram_bot.graph.nodes.rerank.PipelineMetrics.get", return_value=MagicMock()),
    ):
        result = await rerank_node(state, runtime)

    assert result["documents"] == [{"score": 0.9}]
    assert result["rerank_applied"] is True
    assert result["rerank_cache_hit"] is False
    assert result["llm_call_count"] == 3


@pytest.mark.asyncio
async def test_rerank_node_falls_back_to_score_sort_on_exception() -> None:
    runtime = SimpleNamespace(context={"cache": None, "reranker": None})
    docs = [{"score": 0.3}, {"score": 0.8}, {"score": 0.5}]
    state = {
        "documents": docs,
        "messages": [{"content": "query"}],
        "llm_call_count": 0,
        "latency_stages": {},
    }
    mock_lf = MagicMock()

    with (
        patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("telegram_bot.graph.nodes.rerank.get_client", return_value=mock_lf),
        patch("telegram_bot.graph.nodes.rerank.PipelineMetrics.get", return_value=MagicMock()),
    ):
        result = await rerank_node(state, runtime)

    assert [d["score"] for d in result["documents"]] == [0.8, 0.5, 0.3]
    assert result["rerank_applied"] is False
    assert result["rerank_cache_hit"] is False
    mock_lf.update_current_span.assert_called_once()
