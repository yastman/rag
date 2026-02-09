"""Tests for agentic nodes: grade, rerank, rewrite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.state import make_initial_state


# --- grade_node tests ---


class TestGradeNode:
    @pytest.mark.asyncio
    async def test_relevant_documents(self):
        """Documents with top score > 0.3 are relevant."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [
            {"text": "doc1", "score": 0.5},
            {"text": "doc2", "score": 0.2},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is True
        assert "grade" in result["latency_stages"]

    @pytest.mark.asyncio
    async def test_not_relevant_documents(self):
        """Documents with top score <= 0.3 are not relevant."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [
            {"text": "doc1", "score": 0.2},
            {"text": "doc2", "score": 0.1},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is False

    @pytest.mark.asyncio
    async def test_empty_documents(self):
        """No documents → not relevant."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = []
        result = await grade_node(state)
        assert result["documents_relevant"] is False

    @pytest.mark.asyncio
    async def test_threshold_boundary(self):
        """Score exactly at threshold (0.3) is NOT relevant (strictly >)."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [{"text": "doc1", "score": 0.3}]
        result = await grade_node(state)
        assert result["documents_relevant"] is False


# --- rerank_node tests ---


class TestRerankNode:
    @pytest.mark.asyncio
    async def test_rerank_with_colbert(self):
        """ColBERT reranker reorders documents and sets rerank_applied=True."""
        from telegram_bot.graph.nodes.rerank import rerank_node

        state = make_initial_state(user_id=1, session_id="s", query="test query")
        state["documents"] = [
            {"text": "doc A", "score": 0.3},
            {"text": "doc B", "score": 0.5},
            {"text": "doc C", "score": 0.4},
        ]

        mock_reranker = AsyncMock()
        mock_reranker.rerank.return_value = [
            {"index": 1, "score": 0.9},
            {"index": 2, "score": 0.7},
        ]

        result = await rerank_node(state, reranker=mock_reranker, top_k=2)
        assert result["rerank_applied"] is True
        assert len(result["documents"]) == 2
        assert result["documents"][0]["text"] == "doc B"
        assert result["documents"][0]["score"] == 0.9
        assert "rerank" in result["latency_stages"]

    @pytest.mark.asyncio
    async def test_rerank_without_colbert(self):
        """Without reranker, sorts by score and takes top-k."""
        from telegram_bot.graph.nodes.rerank import rerank_node

        state = make_initial_state(user_id=1, session_id="s", query="test query")
        state["documents"] = [
            {"text": "doc A", "score": 0.3},
            {"text": "doc B", "score": 0.5},
            {"text": "doc C", "score": 0.4},
        ]

        result = await rerank_node(state, reranker=None, top_k=2)
        assert result["rerank_applied"] is False
        assert len(result["documents"]) == 2
        # Sorted by score desc: B(0.5), C(0.4)
        assert result["documents"][0]["text"] == "doc B"
        assert result["documents"][1]["text"] == "doc C"

    @pytest.mark.asyncio
    async def test_rerank_empty_documents(self):
        """Empty documents returns empty list."""
        from telegram_bot.graph.nodes.rerank import rerank_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = []
        result = await rerank_node(state, reranker=None)
        assert result["documents"] == []
        assert result["rerank_applied"] is False

    @pytest.mark.asyncio
    async def test_rerank_colbert_failure_fallback(self):
        """If ColBERT fails, falls back to score sort."""
        from telegram_bot.graph.nodes.rerank import rerank_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [
            {"text": "A", "score": 0.2},
            {"text": "B", "score": 0.8},
        ]

        mock_reranker = AsyncMock()
        mock_reranker.rerank.side_effect = RuntimeError("ColBERT unavailable")

        result = await rerank_node(state, reranker=mock_reranker, top_k=2)
        assert result["rerank_applied"] is False
        assert result["documents"][0]["text"] == "B"


# --- rewrite_node tests ---


class TestRewriteNode:
    @pytest.mark.asyncio
    async def test_rewrite_increments_count(self):
        """Rewrite increments rewrite_count."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="test query")
        state["rewrite_count"] = 0

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "improved query about real estate"
        mock_llm.ainvoke.return_value = mock_response

        result = await rewrite_node(state, llm=mock_llm)
        assert result["rewrite_count"] == 1
        assert result["query_embedding"] is None
        assert result["sparse_embedding"] is None
        assert "rewrite" in result["latency_stages"]

    @pytest.mark.asyncio
    async def test_rewrite_updates_messages(self):
        """Rewrite appends a new HumanMessage with rewritten query."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="original query")

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "rewritten query"
        mock_llm.ainvoke.return_value = mock_response

        result = await rewrite_node(state, llm=mock_llm)
        # Should return messages list with a HumanMessage
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg.content == "rewritten query"

    @pytest.mark.asyncio
    async def test_rewrite_llm_failure_keeps_original(self):
        """If LLM fails, keeps original query."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="original query")

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("LLM unavailable")

        result = await rewrite_node(state, llm=mock_llm)
        assert result["rewrite_count"] == 1
        msg = result["messages"][0]
        assert msg.content == "original query"

    @pytest.mark.asyncio
    async def test_rewrite_second_attempt(self):
        """Second rewrite attempt increments count to 2."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="query v2")
        state["rewrite_count"] = 1

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "query v3"
        mock_llm.ainvoke.return_value = mock_response

        result = await rewrite_node(state, llm=mock_llm)
        assert result["rewrite_count"] == 2
