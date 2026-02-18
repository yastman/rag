"""Tests for create_bot_agent factory (#413)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


def test_create_bot_agent_returns_compiled_graph():
    """create_bot_agent returns a compiled graph with .ainvoke method."""
    from telegram_bot.agents.agent import create_bot_agent

    mock_agent = MagicMock()
    with patch("telegram_bot.agents.agent.create_agent", return_value=mock_agent) as mock_ca:
        agent = create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[MagicMock()],
            checkpointer=AsyncMock(),
        )
        mock_ca.assert_called_once()
        assert agent is mock_agent


def test_create_bot_agent_passes_context_schema():
    """create_bot_agent passes BotContext as context_schema."""
    from telegram_bot.agents.agent import create_bot_agent
    from telegram_bot.agents.context import BotContext

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
        )
        call_kwargs = mock_ca.call_args[1]
        assert call_kwargs["context_schema"] is BotContext


def test_create_bot_agent_passes_system_prompt():
    """create_bot_agent includes system_prompt with tool descriptions."""
    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            system_prompt="Custom prompt",
        )
        call_kwargs = mock_ca.call_args[1]
        assert "Custom prompt" in call_kwargs["system_prompt"]


def test_create_bot_agent_passes_checkpointer():
    """create_bot_agent passes checkpointer for conversation persistence."""
    from telegram_bot.agents.agent import create_bot_agent

    mock_cp = AsyncMock()
    with patch("telegram_bot.agents.agent.create_agent") as mock_ca:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=mock_cp,
        )
        call_kwargs = mock_ca.call_args[1]
        assert call_kwargs["checkpointer"] is mock_cp
