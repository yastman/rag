"""Tests for LLM call limits in RAG pipeline (#374).

3-tier protection:
- Graph recursion_limit=15 (LangGraph built-in)
- llm_call_count field + route_grade limit check
- Config: MAX_LLM_CALLS env var
"""

from __future__ import annotations

from typing import get_type_hints
from unittest.mock import MagicMock, patch

import pytest


class TestRAGStateLLMCallCount:
    """RAGState must have llm_call_count field."""

    def test_rag_state_has_llm_call_count_annotation(self):
        from telegram_bot.graph.state import RAGState

        hints = get_type_hints(RAGState)
        assert "llm_call_count" in hints, "RAGState must have llm_call_count field"

    def test_initial_state_has_llm_call_count_zero(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="test")
        assert state["llm_call_count"] == 0

    def test_rag_state_has_max_llm_calls_annotation(self):
        from telegram_bot.graph.state import RAGState

        hints = get_type_hints(RAGState)
        assert "max_llm_calls" in hints, "RAGState must have max_llm_calls field"

    def test_initial_state_has_max_llm_calls_default(self):
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="test")
        assert state["max_llm_calls"] == 5


class TestRouteGradeLLMCallLimit:
    """route_grade must respect llm_call_count limit."""

    def test_llm_limit_reached_prevents_rewrite(self):
        """When llm_call_count >= max_llm_calls, rewrite is blocked → generate."""
        from telegram_bot.graph.edges import route_grade

        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": True,
            "llm_call_count": 5,
            "max_llm_calls": 5,
        }
        assert route_grade(state) == "generate"

    def test_llm_limit_not_reached_allows_rewrite(self):
        """When llm_call_count < max_llm_calls, rewrite is allowed."""
        from telegram_bot.graph.edges import route_grade

        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": True,
            "llm_call_count": 2,
            "max_llm_calls": 5,
        }
        assert route_grade(state) == "rewrite"

    def test_llm_limit_exceeded_prevents_rewrite(self):
        """When llm_call_count > max_llm_calls, rewrite is blocked → generate."""
        from telegram_bot.graph.edges import route_grade

        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": True,
            "llm_call_count": 7,
            "max_llm_calls": 5,
        }
        assert route_grade(state) == "generate"

    def test_llm_limit_does_not_affect_relevant_docs_rerank(self):
        """When documents are relevant, rerank still works regardless of llm_call_count."""
        from telegram_bot.graph.edges import route_grade

        state = {
            "documents_relevant": True,
            "skip_rerank": False,
            "llm_call_count": 10,
            "max_llm_calls": 5,
        }
        assert route_grade(state) == "rerank"

    def test_llm_limit_does_not_affect_relevant_docs_generate(self):
        """When documents are relevant and skip_rerank, generate works regardless."""
        from telegram_bot.graph.edges import route_grade

        state = {
            "documents_relevant": True,
            "skip_rerank": True,
            "llm_call_count": 10,
            "max_llm_calls": 5,
        }
        assert route_grade(state) == "generate"

    def test_default_max_llm_calls(self):
        """Missing max_llm_calls defaults to 5."""
        from telegram_bot.graph.edges import route_grade

        state = {
            "documents_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 3,
            "rewrite_effective": True,
            "score_improved": True,
            "llm_call_count": 5,
            # no max_llm_calls key
        }
        assert route_grade(state) == "generate"


class TestNodeLLMCallCountIncrement:
    """Nodes must increment llm_call_count in their state updates."""

    @pytest.mark.asyncio
    async def test_classify_node_increments_llm_call_count(self):
        from telegram_bot.graph.nodes.classify import classify_node
        from telegram_bot.graph.state import make_initial_state

        state = make_initial_state(user_id=1, session_id="s", query="квартира в Несебре")
        result = await classify_node(state)
        assert result["llm_call_count"] == 1

    @pytest.mark.asyncio
    async def test_rewrite_node_increments_llm_call_count(self):
        from unittest.mock import AsyncMock

        from telegram_bot.graph.nodes.rewrite import rewrite_node

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "rewritten query"
        mock_response.model = "test-model"

        mock_llm = MagicMock()
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

        state = {
            "messages": [{"role": "user", "content": "test query"}],
            "rewrite_count": 0,
            "llm_call_count": 2,
            "latency_stages": {},
        }

        with patch("telegram_bot.graph.config.GraphConfig") as mock_config_cls:
            mock_config = MagicMock()
            mock_config.rewrite_model = "test-model"
            mock_config.rewrite_max_tokens = 100
            mock_config.create_llm.return_value = mock_llm
            mock_config_cls.from_env.return_value = mock_config

            result = await rewrite_node(state, llm=mock_llm)

        assert result["llm_call_count"] == 3

    @pytest.mark.asyncio
    async def test_rerank_node_increments_llm_call_count(self):
        from telegram_bot.graph.nodes.rerank import rerank_node

        state = {
            "messages": [{"role": "user", "content": "test"}],
            "documents": [{"text": "doc1", "score": 0.9}],
            "llm_call_count": 1,
            "latency_stages": {},
        }

        result = await rerank_node(state, reranker=None)
        assert result["llm_call_count"] == 2


class TestBotConfigCallLimits:
    """BotConfig must have MAX_LLM_CALLS and MAX_TOOL_CALLS settings."""

    def test_max_llm_calls_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.max_llm_calls == 5

    def test_max_tool_calls_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.max_tool_calls == 5

    def test_max_llm_calls_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_LLM_CALLS", "10")
        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.max_llm_calls == 10

    def test_max_tool_calls_from_env(self, monkeypatch):
        monkeypatch.setenv("MAX_TOOL_CALLS", "8")
        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.max_tool_calls == 8


class TestGraphRecursionLimit:
    """Graph must have recursion_limit=15 via with_config."""

    def test_graph_has_recursion_limit(self):
        """build_graph should set recursion_limit=15 via with_config."""

        mock_cache = MagicMock()
        mock_embeddings = MagicMock()
        mock_sparse = MagicMock()
        mock_qdrant = MagicMock()

        with patch("telegram_bot.graph.graph.StateGraph") as mock_sg_cls:
            mock_workflow = MagicMock()
            mock_compiled = MagicMock()
            mock_workflow.compile.return_value = mock_compiled
            mock_sg_cls.return_value = mock_workflow

            from telegram_bot.graph.graph import build_graph

            build_graph(
                cache=mock_cache,
                embeddings=mock_embeddings,
                sparse_embeddings=mock_sparse,
                qdrant=mock_qdrant,
            )

            mock_compiled.with_config.assert_called_once_with(recursion_limit=15)


class TestScoringCallLimits:
    """Langfuse scores must include llm_calls_total and tool_calls_total."""

    def test_write_langfuse_scores_includes_llm_calls_total(self):
        from telegram_bot.scoring import write_langfuse_scores

        mock_lf = MagicMock()
        result = {
            "query_type": "GENERAL",
            "latency_stages": {},
            "llm_call_count": 3,
        }
        write_langfuse_scores(mock_lf, result)

        # Find call with name="llm_calls_total"
        found = any(
            c.kwargs.get("name") == "llm_calls_total" or (c.args and c.args[0] == "llm_calls_total")
            for c in mock_lf.score_current_trace.call_args_list
        )
        assert found, "write_langfuse_scores must write llm_calls_total score"
