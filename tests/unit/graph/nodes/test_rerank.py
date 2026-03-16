"""Tests for rerank_node — ColBERT reranking with score-sort fallback.

These are the canonical unit tests for rerank_node.
Note: tests/unit/graph/test_agentic_nodes.py::TestRerankNode has partial overlap —
pruning deferred to a follow-up PR.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from telegram_bot.graph.nodes.rerank import rerank_node
from telegram_bot.graph.state import make_initial_state


def _make_runtime(cache=None, reranker=None) -> Runtime:
    """Create a Runtime with GraphContext for rerank_node tests."""
    return Runtime(
        context={
            "cache": cache,
            "reranker": reranker,
        }
    )


def _make_docs(scores: list[float]) -> list[dict]:
    """Create mock documents with given scores."""
    return [{"id": str(i), "text": f"doc {i}", "score": s} for i, s in enumerate(scores)]


def _state_with_query(query: str = "test query") -> dict:
    """Create a minimal state with a human message."""
    state = make_initial_state(user_id=1, session_id="s1", query=query)
    state["messages"] = [HumanMessage(content=query)]
    return state


class TestRerankNodeEmptyInput:
    """rerank_node with empty document list."""

    async def test_empty_documents_returns_early(self):
        state = _state_with_query()
        state["documents"] = []
        state["llm_call_count"] = 0

        result = await rerank_node(state, _make_runtime())

        assert result["documents"] == []
        assert result["rerank_applied"] is False
        assert result["rerank_cache_hit"] is False
        assert result["llm_call_count"] == 1  # incremented even on early return
        assert "rerank" in result["latency_stages"]

    async def test_empty_documents_does_not_call_perform_rerank(self):
        """Empty documents triggers early return before perform_rerank is called."""
        state = _state_with_query()
        state["documents"] = []

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            await rerank_node(state, _make_runtime(reranker=AsyncMock()))

        mock_rerank.assert_not_awaited()


class TestRerankNodeWithReranker:
    """rerank_node when reranker is available (ColBERT path)."""

    async def test_calls_perform_rerank(self):
        state = _state_with_query("find apartments")
        state["documents"] = _make_docs([0.010, 0.008, 0.012])

        reranked = _make_docs([0.015, 0.012, 0.010])
        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (reranked, True, False)
            result = await rerank_node(state, _make_runtime(reranker=MagicMock()))

        mock_rerank.assert_awaited_once()
        assert result["documents"] == reranked
        assert result["rerank_applied"] is True

    async def test_rerank_cache_hit_propagated(self):
        state = _state_with_query()
        state["documents"] = _make_docs([0.010])

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (_make_docs([0.010]), True, True)  # cache_hit=True
            result = await rerank_node(state, _make_runtime(reranker=MagicMock()))

        assert result["rerank_cache_hit"] is True

    async def test_llm_call_count_incremented(self):
        state = _state_with_query()
        state["documents"] = _make_docs([0.010])
        state["llm_call_count"] = 2

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (_make_docs([0.010]), True, False)
            result = await rerank_node(state, _make_runtime(reranker=MagicMock()))

        assert result["llm_call_count"] == 3


class TestRerankNodeFallback:
    """rerank_node score-sort fallback when no reranker or perform_rerank returns not applied."""

    async def test_no_reranker_sorts_by_score(self):
        """When perform_rerank returns rerank_applied=False, node sorts docs by score descending."""
        state = _state_with_query()
        state["documents"] = _make_docs([0.005, 0.015, 0.010, 0.008, 0.012, 0.003])

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            # perform_rerank returns rerank_applied=False → node applies score-sort fallback
            mock_rerank.return_value = (state["documents"], False, False)
            result = await rerank_node(state, _make_runtime(reranker=None))

        scores = [d["score"] for d in result["documents"]]
        assert scores == sorted(scores, reverse=True)
        assert len(result["documents"]) <= 5  # top_k default

    async def test_fallback_applies_top_k_limit(self):
        """Score-sort fallback trims to top_k=5."""
        state = _state_with_query()
        state["documents"] = _make_docs([0.01] * 10)

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (state["documents"], False, False)
            result = await rerank_node(state, _make_runtime(reranker=None))

        assert len(result["documents"]) == 5

    async def test_exception_triggers_score_sort_fallback(self):
        """ColBERT failure → graceful fallback to score-sort."""
        state = _state_with_query()
        state["documents"] = _make_docs([0.005, 0.015, 0.010])

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.side_effect = RuntimeError("ColBERT service timeout")
            with patch("telegram_bot.graph.nodes.rerank.get_client") as mock_get_client:
                mock_lf = MagicMock()
                mock_get_client.return_value = mock_lf
                result = await rerank_node(state, _make_runtime(reranker=MagicMock()))

        assert result["rerank_applied"] is False
        assert result["rerank_cache_hit"] is False
        # Should be sorted by score
        scores = [d["score"] for d in result["documents"]]
        assert scores == sorted(scores, reverse=True)

    async def test_exception_logs_error_to_langfuse(self):
        """On ColBERT failure, error is recorded via langfuse span."""
        state = _state_with_query()
        state["documents"] = _make_docs([0.010])

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.side_effect = RuntimeError("timeout")
            with patch("telegram_bot.graph.nodes.rerank.get_client") as mock_get_client:
                mock_lf = MagicMock()
                mock_get_client.return_value = mock_lf
                await rerank_node(state, _make_runtime(reranker=MagicMock()))

        mock_lf.update_current_span.assert_called_once()
        call_kwargs = mock_lf.update_current_span.call_args[1]
        assert call_kwargs.get("level") == "ERROR"


class TestRerankNodeQueryExtraction:
    """rerank_node extracts query from messages correctly."""

    async def test_query_from_human_message_object(self):
        """Extracts content from HumanMessage object."""
        state = _state_with_query("test from message object")
        state["documents"] = _make_docs([0.010])

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (_make_docs([0.010]), True, False)
            await rerank_node(state, _make_runtime(reranker=MagicMock()))

        call_args = mock_rerank.call_args
        assert call_args[0][0] == "test from message object"

    async def test_query_from_dict_message(self):
        """Extracts content from dict-style message."""
        state = make_initial_state(user_id=1, session_id="s1", query="dict query")
        state["messages"] = [{"role": "user", "content": "dict query"}]
        state["documents"] = _make_docs([0.010])

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (_make_docs([0.010]), True, False)
            await rerank_node(state, _make_runtime(reranker=MagicMock()))

        call_args = mock_rerank.call_args
        assert call_args[0][0] == "dict query"


class TestRerankNodeLatency:
    """rerank_node latency tracking."""

    async def test_latency_stages_set(self):
        state = _state_with_query()
        state["documents"] = _make_docs([0.010])
        state["latency_stages"] = {"retrieve": 0.1}

        with patch(
            "telegram_bot.graph.nodes.rerank.perform_rerank", new_callable=AsyncMock
        ) as mock_rerank:
            mock_rerank.return_value = (_make_docs([0.010]), True, False)
            result = await rerank_node(state, _make_runtime(reranker=MagicMock()))

        assert "rerank" in result["latency_stages"]
        assert result["latency_stages"]["retrieve"] == 0.1  # existing preserved

    async def test_latency_stages_set_on_empty_input(self):
        state = _state_with_query()
        state["documents"] = []
        state["latency_stages"] = {}

        result = await rerank_node(state, _make_runtime())

        assert "rerank" in result["latency_stages"]
        assert result["latency_stages"]["rerank"] >= 0
