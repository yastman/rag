"""Tests for error span tracking in LangGraph nodes (P1.2 #103).

Verifies that generate, rewrite, rerank, and respond nodes call
get_client().update_current_span(level="ERROR", ...) on failure paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.state import make_initial_state


def _make_state(query: str = "Какие квартиры?") -> dict:
    """Create minimal RAGState for error-path testing."""
    state = make_initial_state(user_id=123, session_id="s-test", query=query)
    state["query_type"] = "GENERAL"
    state["documents"] = [
        {
            "text": "Квартира в Несебре, 65000€",
            "score": 0.92,
            "metadata": {"title": "Апартамент", "city": "Несебр", "price": 65000},
        },
    ]
    return state


class TestGenerateNodeErrorSpan:
    """generate_node sets ERROR span when LLM fails."""

    @pytest.mark.asyncio
    async def test_llm_error_sets_error_span(self) -> None:
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config = MagicMock()
        mock_config.domain = "недвижимость"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.generate_max_tokens = 2048
        mock_config.streaming_enabled = False
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM unavailable"),
        )
        mock_config.create_llm.return_value = mock_client

        mock_lf = MagicMock()
        state = _make_state()

        with (
            patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            result = await generate_node(state)

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, "generate_node must emit ERROR span when LLM fails"
        assert "LLM failed" in error_calls[-1]["status_message"]
        assert "LLM unavailable" in error_calls[-1]["status_message"]
        # Fallback response still returned
        assert result["response"] != ""


class TestRewriteNodeErrorSpan:
    """rewrite_node sets ERROR span when LLM rewrite fails."""

    @pytest.mark.asyncio
    async def test_llm_rewrite_error_sets_error_span(self) -> None:
        from telegram_bot.graph.nodes.rewrite import rewrite_node

        mock_llm = MagicMock()
        mock_llm.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM rewrite timeout"),
        )

        mock_config = MagicMock()
        mock_config.rewrite_model = "gpt-4o-mini"
        mock_config.rewrite_max_tokens = 64

        mock_lf = MagicMock()
        state = _make_state()
        node_fn = getattr(rewrite_node, "__wrapped__", rewrite_node)

        with (
            patch(
                "telegram_bot.graph.config.GraphConfig.from_env",
                return_value=mock_config,
            ),
            patch.dict(node_fn.__globals__, {"get_client": lambda: mock_lf}),
        ):
            result = await node_fn(state, llm=mock_llm)

        mock_lf.update_current_span.assert_called_once()
        call_kwargs = mock_lf.update_current_span.call_args.kwargs
        assert call_kwargs["level"] == "ERROR"
        assert "Rewrite LLM failed" in call_kwargs["status_message"]
        assert "LLM rewrite timeout" in call_kwargs["status_message"]
        # Falls back to original query
        assert result["rewrite_effective"] is False


class TestRerankNodeErrorSpan:
    """rerank_node sets ERROR span when ColBERT fails."""

    @pytest.mark.asyncio
    async def test_colbert_error_sets_error_span(self) -> None:
        from telegram_bot.graph.nodes.rerank import rerank_node

        mock_reranker = AsyncMock()
        mock_reranker.rerank = AsyncMock(side_effect=RuntimeError("ColBERT timeout"))

        mock_lf = MagicMock()
        state = _make_state()
        node_fn = getattr(rerank_node, "__wrapped__", rerank_node)

        with patch.dict(node_fn.__globals__, {"get_client": lambda: mock_lf}):
            result = await node_fn(state, reranker=mock_reranker)

        mock_lf.update_current_span.assert_called_once()
        call_kwargs = mock_lf.update_current_span.call_args.kwargs
        assert call_kwargs["level"] == "ERROR"
        assert "ColBERT rerank failed" in call_kwargs["status_message"]
        assert "ColBERT timeout" in call_kwargs["status_message"]
        # Falls back to score-sort
        assert result["rerank_applied"] is False


class TestRespondNodeErrorSpan:
    """respond_node sets ERROR span when Telegram send fails."""

    @pytest.mark.asyncio
    async def test_send_error_sets_error_span(self) -> None:
        from telegram_bot.graph.nodes.respond import respond_node

        mock_message = AsyncMock()
        mock_message.answer = AsyncMock(side_effect=RuntimeError("Telegram API error"))

        mock_lf = MagicMock()
        state = _make_state()
        state["response"] = "Ответ пользователю"
        state["message"] = mock_message
        state["response_sent"] = False
        node_fn = getattr(respond_node, "__wrapped__", respond_node)

        with patch.dict(node_fn.__globals__, {"get_client": lambda: mock_lf}):
            result = await node_fn(state)

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert error_calls, "respond_node must emit ERROR span on Telegram send failure"
        assert "Telegram send failed" in error_calls[-1]["status_message"]
        # Node still returns latency
        assert "respond" in result["latency_stages"]
