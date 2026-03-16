"""Tests for grade_node — score-based document relevance grading.

These are the canonical unit tests for grade_node.
Note: tests/unit/graph/test_agentic_nodes.py::TestGradeNode and
TestGradeNodeScoreImproved have partial overlap — pruning deferred to a follow-up PR.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from telegram_bot.graph.nodes.grade import grade_node
from telegram_bot.graph.state import make_initial_state


def _make_docs(scores: list[float]) -> list[dict]:
    """Create mock documents with given scores."""
    return [{"id": str(i), "text": f"doc {i}", "score": s} for i, s in enumerate(scores)]


def _make_config(**kwargs):
    """Create a GraphConfig-like mock with defaults."""
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.relevance_threshold_rrf = kwargs.get("relevance_threshold_rrf", 0.005)
    cfg.skip_rerank_threshold = kwargs.get("skip_rerank_threshold", 0.018)
    cfg.score_improvement_delta = kwargs.get("score_improvement_delta", 0.001)
    return cfg


class TestGradeNodeEmptyInput:
    """grade_node with empty or missing documents."""

    async def test_empty_documents_marks_not_relevant(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = []

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is False
        assert result["grade_confidence"] == 0.0
        assert result["skip_rerank"] is False
        assert result["score_improved"] is False
        assert "grade" in result["latency_stages"]

    async def test_missing_documents_key_marks_not_relevant(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        # Don't set documents — grade_node does state.get("documents", [])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is False
        assert result["grade_confidence"] == 0.0

    async def test_non_dict_documents_treated_as_no_scores(self):
        """Documents that are not dicts (placeholders) should be skipped."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = ["not a dict", 42, None]

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is False
        assert result["grade_confidence"] == 0.0

    async def test_all_zero_scores_not_relevant(self):
        """Documents with score=0 are below default threshold (0.005)."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.0, 0.0, 0.0])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is False
        assert result["grade_confidence"] == 0.0


class TestGradeNodeRelevanceThreshold:
    """grade_node relevance determination based on top score."""

    async def test_score_above_threshold_marks_relevant(self):
        """Top score > 0.005 → documents_relevant=True."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.006, 0.003])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is True
        assert result["grade_confidence"] == pytest.approx(0.006)

    async def test_score_at_threshold_not_relevant(self):
        """Top score == threshold (not strictly greater) → not relevant."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.005])  # exactly at threshold

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config(relevance_threshold_rrf=0.005)
            result = await grade_node(state)

        # top_score > threshold → 0.005 > 0.005 is False
        assert result["documents_relevant"] is False

    async def test_score_below_threshold_not_relevant(self):
        """Top score < threshold → not relevant."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.003, 0.001])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is False

    async def test_typical_rrf_scores_are_relevant(self):
        """Typical RRF rank-1 score (~0.016) should be relevant."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        # RRF score for rank-1 with k=60: 1/(60+1) ≈ 0.0164
        state["documents"] = _make_docs([0.0164, 0.0154, 0.0145])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is True
        assert result["grade_confidence"] == pytest.approx(0.0164)


class TestGradeNodeSkipRerank:
    """grade_node skip_rerank flag when confidence is high."""

    async def test_high_score_sets_skip_rerank(self):
        """Score >= skip_rerank_threshold (0.018) → skip_rerank=True."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.020])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["skip_rerank"] is True
        assert result["documents_relevant"] is True

    async def test_relevant_but_low_confidence_does_not_skip_rerank(self):
        """Score in (threshold, skip_rerank_threshold) → relevant but rerank still runs."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        # above relevance (0.005) but below skip_rerank (0.018)
        state["documents"] = _make_docs([0.014])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is True
        assert result["skip_rerank"] is False

    async def test_not_relevant_never_skips_rerank(self):
        """Not relevant → skip_rerank=False regardless of score."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.002])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["documents_relevant"] is False
        assert result["skip_rerank"] is False


class TestGradeNodeScoreImprovement:
    """grade_node score_improved flag for rewrite guard."""

    async def test_first_pass_always_score_improved(self):
        """prev_confidence=0.0 → score_improved=True regardless of score."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.001])  # very low score
        state["grade_confidence"] = 0.0  # first pass

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["score_improved"] is True

    async def test_significant_improvement_sets_improved(self):
        """Delta >= score_improvement_delta (0.001) → score_improved=True."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.012])
        state["grade_confidence"] = 0.010  # prev, delta=0.002 >= 0.001

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["score_improved"] is True

    async def test_insufficient_improvement_not_improved(self):
        """Delta < score_improvement_delta → score_improved=False."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.0105])
        state["grade_confidence"] = 0.0100  # delta=0.0005 < 0.001

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["score_improved"] is False

    async def test_no_improvement_after_rewrite(self):
        """Score same as previous after rewrite → score_improved=False."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.010])
        state["grade_confidence"] = 0.010  # same score, delta=0

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["score_improved"] is False


class TestGradeNodeLatencyAndState:
    """grade_node latency and state update correctness."""

    async def test_latency_stages_updated(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.010])
        state["latency_stages"] = {"retrieve": 0.05}

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert "grade" in result["latency_stages"]
        assert result["latency_stages"]["retrieve"] == 0.05  # existing preserved
        assert result["latency_stages"]["grade"] > 0

    async def test_grade_confidence_equals_top_score(self):
        """grade_confidence must be the max document score."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.008, 0.014, 0.006])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert result["grade_confidence"] == pytest.approx(0.014)

    async def test_returns_all_required_keys(self):
        """Result must contain all expected state keys."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = _make_docs([0.010])

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        required = {
            "documents_relevant",
            "grade_confidence",
            "skip_rerank",
            "score_improved",
            "latency_stages",
        }
        assert required.issubset(result.keys())

    async def test_empty_docs_latency_stages_still_set(self):
        """Even on empty path, latency_stages should contain 'grade'."""
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["documents"] = []
        state["latency_stages"] = {}

        with patch("telegram_bot.graph.config.GraphConfig") as mock_cfg_cls:
            mock_cfg_cls.from_env.return_value = _make_config()
            result = await grade_node(state)

        assert "grade" in result["latency_stages"]
