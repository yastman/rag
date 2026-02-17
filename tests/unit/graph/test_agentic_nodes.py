"""Tests for agentic nodes: grade, rerank, rewrite."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.state import make_initial_state


# --- grade_node tests ---


class TestGradeNode:
    @pytest.mark.parametrize(
        ("documents", "expected_relevant"),
        [
            pytest.param(
                [{"text": "doc1", "score": 0.5}, {"text": "doc2", "score": 0.2}],
                True,
                id="high_scores_relevant",
            ),
            pytest.param(
                [{"text": "doc1", "score": 0.003}, {"text": "doc2", "score": 0.001}],
                False,
                id="low_scores_not_relevant",
            ),
            pytest.param([], False, id="empty_not_relevant"),
            pytest.param(
                [{"text": "doc1", "score": 0.005}],
                False,
                id="threshold_boundary_not_relevant",
            ),
        ],
    )
    async def test_grade_relevance(self, documents, expected_relevant):
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = documents
        result = await grade_node(state)
        assert result["documents_relevant"] is expected_relevant
        assert "grade" in result["latency_stages"]


class TestGradeNodeRRFScores:
    async def test_rrf_scores_are_relevant(self):
        """RRF scores ~0.016 should be considered relevant (not irrelevant)."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="квартиры")
        state["documents"] = [
            {"score": 0.016, "text": "doc1"},  # RRF rank 1: 1/61 ≈ 0.016
            {"score": 0.015, "text": "doc2"},
            {"score": 0.014, "text": "doc3"},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is True
    async def test_very_low_scores_are_not_relevant(self):
        """Scores near zero should still be irrelevant."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [
            {"score": 0.001, "text": "garbage"},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is False
    async def test_rrf_high_confidence_skips_rerank(self):
        """RRF top-1 score 0.016 exceeds skip_rerank_threshold (0.012) → skip_rerank=True."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="квартиры")
        state["documents"] = [
            {"score": 0.016, "text": "doc1"},
            {"score": 0.015, "text": "doc2"},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is True
        assert result["skip_rerank"] is True
        assert result["grade_confidence"] == 0.016
    async def test_rrf_low_confidence_does_not_skip_rerank(self):
        """RRF score 0.010 below skip_rerank_threshold (0.012) → skip_rerank=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [
            {"score": 0.010, "text": "doc1"},
            {"score": 0.008, "text": "doc2"},
        ]
        result = await grade_node(state)
        assert result["documents_relevant"] is True
        assert result["skip_rerank"] is False
    async def test_threshold_configurable_via_env(self):
        """RELEVANCE_THRESHOLD_RRF env var should override default."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [{"score": 0.008, "text": "doc1"}]
        with patch.dict("os.environ", {"RELEVANCE_THRESHOLD_RRF": "0.01"}):
            result = await grade_node(state)
        assert result["documents_relevant"] is False  # 0.008 < 0.01


# --- rerank_node tests ---


class TestRerankNode:
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
    async def test_rerank_empty_documents(self):
        """Empty documents returns empty list."""
        from telegram_bot.graph.nodes.rerank import rerank_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = []
        result = await rerank_node(state, reranker=None)
        assert result["documents"] == []
        assert result["rerank_applied"] is False
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


def _make_mock_llm(content: str = "rewritten query") -> MagicMock:
    """Create mock AsyncOpenAI client for rewrite_node tests."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock(choices=[mock_choice])

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


class TestRewriteNode:
    async def test_rewrite_increments_count(self):
        """Rewrite increments rewrite_count."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="test query")
        state["rewrite_count"] = 0

        mock_llm = _make_mock_llm("improved query about real estate")

        result = await rewrite_node(state, llm=mock_llm)
        assert result["rewrite_count"] == 1
        assert result["query_embedding"] is None
        assert result["sparse_embedding"] is None
        assert "rewrite" in result["latency_stages"]
    async def test_rewrite_updates_messages(self):
        """Rewrite appends a new HumanMessage with rewritten query."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="original query")

        mock_llm = _make_mock_llm("rewritten query")

        result = await rewrite_node(state, llm=mock_llm)
        # Should return messages list with a HumanMessage
        assert len(result["messages"]) == 1
        msg = result["messages"][0]
        assert msg.content == "rewritten query"
    async def test_rewrite_llm_failure_keeps_original(self):
        """If LLM fails, keeps original query."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="original query")

        mock_llm = MagicMock()
        mock_llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        result = await rewrite_node(state, llm=mock_llm)
        assert result["rewrite_count"] == 1
        msg = result["messages"][0]
        assert msg.content == "original query"
    async def test_rewrite_second_attempt(self):
        """Second rewrite attempt increments count to 2."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        state = make_initial_state(user_id=1, session_id="s", query="query v2")
        state["rewrite_count"] = 1

        mock_llm = _make_mock_llm("query v3")

        result = await rewrite_node(state, llm=mock_llm)
        assert result["rewrite_count"] == 2
    async def test_rewrite_empty_content_sets_ineffective(self):
        """When LLM returns empty content, rewrite_effective=False."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        mock_llm = _make_mock_llm("")  # empty content after strip

        state = make_initial_state(user_id=1, session_id="s", query="тест")
        result = await rewrite_node(state, llm=mock_llm)

        assert result["rewrite_effective"] is False
        assert result["rewrite_count"] == 1
    async def test_rewrite_same_text_sets_ineffective(self):
        """When LLM returns the same text as original, rewrite_effective=False."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        mock_llm = _make_mock_llm("тест")  # same as original query

        state = make_initial_state(user_id=1, session_id="s", query="тест")
        result = await rewrite_node(state, llm=mock_llm)

        assert result["rewrite_effective"] is False
        assert result["rewrite_count"] == 1
    async def test_rewrite_with_content_sets_effective(self):
        """When LLM returns valid content, rewrite_effective=True."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        mock_llm = _make_mock_llm("переформулированный запрос")

        state = make_initial_state(user_id=1, session_id="s", query="тест")
        result = await rewrite_node(state, llm=mock_llm)

        assert result["rewrite_effective"] is True
    async def test_rewrite_latency_stages_contains_only_numeric_values(self):
        """latency_stages must keep only numeric durations."""
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        mock_llm = _make_mock_llm("переформулированный запрос")
        state = make_initial_state(user_id=1, session_id="s", query="тест")
        result = await rewrite_node(state, llm=mock_llm)

        stages = result["latency_stages"]
        assert set(stages.keys()) == {"rewrite"}
        assert isinstance(stages["rewrite"], float)
        assert result["rewrite_count"] == 1


# --- grade_node score_improved tests ---


class TestGradeNodeScoreImproved:
    async def test_first_grade_always_improved(self):
        """First grade (prev=0.0) always sets score_improved=True."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["documents"] = [{"text": "doc", "score": 0.003}]
        # grade_confidence starts at 0.0
        result = await grade_node(state)
        assert result["score_improved"] is True
    async def test_score_improved_above_delta(self):
        """Score improved by >= delta → score_improved=True."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.003  # previous top score
        state["documents"] = [{"text": "doc", "score": 0.005}]  # delta = 0.002 > 0.001
        result = await grade_node(state)
        assert result["score_improved"] is True
    async def test_score_not_improved_below_delta(self):
        """Score didn't improve enough → score_improved=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.004  # previous top score
        state["documents"] = [{"text": "doc", "score": 0.0045}]  # delta = 0.0005 < 0.001
        result = await grade_node(state)
        assert result["score_improved"] is False
    async def test_score_decreased_not_improved(self):
        """Score got worse → score_improved=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.006
        state["documents"] = [{"text": "doc", "score": 0.004}]  # worse
        result = await grade_node(state)
        assert result["score_improved"] is False
    async def test_empty_docs_not_improved(self):
        """Empty documents → score_improved=False."""
        from telegram_bot.graph.nodes.grade import grade_node

        state = make_initial_state(user_id=1, session_id="s", query="test")
        state["grade_confidence"] = 0.005
        state["documents"] = []
        result = await grade_node(state)
        assert result["score_improved"] is False
