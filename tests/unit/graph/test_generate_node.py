"""Tests for generate_node — LLM answer generation with conversation history."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.state import make_initial_state


def _make_state_with_docs(
    query: str = "Какие квартиры в Несебре?",
    documents: list | None = None,
    conversation_history: list | None = None,
) -> dict:
    """Helper: create a state with documents and optional conversation history."""
    state = make_initial_state(user_id=123, session_id="s-test", query=query)
    state["query_type"] = "GENERAL"
    state["documents"] = documents or [
        {
            "text": "Квартира в Несебре, 2 комнаты, 65000€",
            "score": 0.92,
            "metadata": {"title": "Апартамент Несебр", "city": "Несебр", "price": 65000},
        },
        {
            "text": "Студия в Несебре, 35000€, вид на море",
            "score": 0.87,
            "metadata": {"title": "Студия с видом", "city": "Несебр", "price": 35000},
        },
    ]
    if conversation_history:
        state["messages"] = conversation_history + state["messages"]
    return state


class TestGenerateNode:
    """Test generate_node produces answers from retrieved documents."""

    @pytest.mark.asyncio
    async def test_generates_from_docs(self) -> None:
        """generate_node calls LLM with formatted context and returns response."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "В Несебре есть квартира за 65000€ и студия за 35000€."
        mock_llm.ainvoke.return_value = mock_response

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_llm",
            return_value=mock_llm,
        ):
            result = await generate_node(state)

        assert result["response"] == "В Несебре есть квартира за 65000€ и студия за 35000€."
        assert "generate" in result["latency_stages"]
        mock_llm.ainvoke.assert_called_once()

        # Verify prompt contains context from docs
        call_args = mock_llm.ainvoke.call_args[0][0]
        # call_args is a list of messages
        messages_text = " ".join(str(m) for m in call_args)
        assert "Несебр" in messages_text

    @pytest.mark.asyncio
    async def test_uses_conversation_history(self) -> None:
        """generate_node includes conversation history in the prompt."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Ответ с учётом контекста разговора."
        mock_llm.ainvoke.return_value = mock_response

        history = [
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте! Чем могу помочь?"},
        ]
        state = _make_state_with_docs(
            query="А что есть в Несебре?",
            conversation_history=history,
        )

        with patch(
            "telegram_bot.graph.nodes.generate._get_llm",
            return_value=mock_llm,
        ):
            result = await generate_node(state)

        assert result["response"] == "Ответ с учётом контекста разговора."
        # Verify conversation history is included in messages
        call_args = mock_llm.ainvoke.call_args[0][0]
        messages_text = " ".join(str(m) for m in call_args)
        assert "Привет" in messages_text
        assert "Здравствуйте" in messages_text

    @pytest.mark.asyncio
    async def test_fallback_on_error(self) -> None:
        """generate_node returns fallback response when LLM fails."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = Exception("LLM unavailable")

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_llm",
            return_value=mock_llm,
        ):
            result = await generate_node(state)

        assert result["response"] != ""
        assert "generate" in result["latency_stages"]
        # Fallback should mention found objects or service unavailability
        assert "Несебр" in result["response"] or "недоступен" in result["response"]

    @pytest.mark.asyncio
    async def test_system_prompt_uses_domain(self) -> None:
        """generate_node builds system prompt with domain from config."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Ответ."
        mock_llm.ainvoke.return_value = mock_response

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_llm",
            return_value=mock_llm,
        ):
            with patch(
                "telegram_bot.graph.nodes.generate._get_domain",
                return_value="недвижимость",
            ):
                await generate_node(state)

        # System prompt should contain domain
        call_args = mock_llm.ainvoke.call_args[0][0]
        system_msg = call_args[0]
        assert "недвижимость" in str(system_msg)

    @pytest.mark.asyncio
    async def test_limits_to_top_5_docs(self) -> None:
        """generate_node formats only top-5 documents for context."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "Ответ."
        mock_llm.ainvoke.return_value = mock_response

        docs = [
            {"text": f"Doc {i}", "score": 1.0 - i * 0.1, "metadata": {"title": f"Doc {i}"}}
            for i in range(10)
        ]
        state = _make_state_with_docs(documents=docs)

        with patch(
            "telegram_bot.graph.nodes.generate._get_llm",
            return_value=mock_llm,
        ):
            await generate_node(state)

        # Check that context has at most 5 documents
        call_args = mock_llm.ainvoke.call_args[0][0]
        messages_text = " ".join(str(m) for m in call_args)
        assert "Doc 0" in messages_text
        assert "Doc 4" in messages_text
        assert "Doc 5" not in messages_text

    @pytest.mark.asyncio
    async def test_empty_documents_fallback(self) -> None:
        """generate_node handles empty documents gracefully."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "К сожалению, информации не найдено."
        mock_llm.ainvoke.return_value = mock_response

        state = _make_state_with_docs(documents=[])

        with patch(
            "telegram_bot.graph.nodes.generate._get_llm",
            return_value=mock_llm,
        ):
            result = await generate_node(state)

        assert result["response"] != ""
