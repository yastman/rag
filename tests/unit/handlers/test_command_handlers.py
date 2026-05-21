"""Tests for telegram_bot/handlers/command_handlers.py Router module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.handlers.command_handlers import (
    cmd_clear,
    cmd_help,
    cmd_metrics,
    cmd_start,
    cmd_stats,
    create_commands_router,
)


@pytest.fixture
def mock_bot():
    """Create a mock PropertyBot instance for handler tests."""
    bot = MagicMock()
    bot.config = MagicMock()
    bot.config.kommo_enabled = False
    bot.config.manager_ids = set()
    bot._cache = MagicMock()
    bot._cache.clear_conversation = AsyncMock()
    bot._cache.get_metrics = MagicMock(return_value={})
    bot._history_service = None
    bot._checkpointer = None
    bot._agent_checkpointer = None
    bot._resolve_user_role = AsyncMock(return_value="client")
    bot._is_admin = MagicMock(return_value=False)
    bot._i18n_hub = None
    return bot


def _make_message(text="test", user_id=12345, chat_id=12345):
    """Create a mock message."""
    message = MagicMock()
    message.text = text
    message.from_user = MagicMock(id=user_id, first_name="Test")
    message.chat = MagicMock(id=chat_id)
    message.answer = AsyncMock()
    return message


class TestCreateCommandsRouter:
    """Test create_commands_router factory."""

    def test_returns_router_with_expected_name(self, mock_bot):
        """Factory returns a Router named 'commands'."""
        from aiogram import Router

        router = create_commands_router(mock_bot)
        assert isinstance(router, Router)
        assert router.name == "commands"

    def test_router_has_all_command_handlers_registered(self, mock_bot):
        """Router registers handlers for all 9 commands."""
        router = create_commands_router(mock_bot)
        # Check message handlers count (9 command handlers)
        assert len(router.message.handlers) == 9


class TestCmdHelp:
    """Test cmd_help handler."""

    async def test_sends_expected_text(self, mock_bot):
        """cmd_help sends response with example queries and commands."""
        message = _make_message()
        await cmd_help(mock_bot, message)

        message.answer.assert_called_once()
        text = message.answer.call_args[0][0]
        assert "/clear" in text
        assert "/stats" in text
        assert "/history" in text
        assert "/metrics" in text
        assert "/clearcache" in text


class TestCmdStats:
    """Test cmd_stats handler."""

    async def test_formats_cache_metrics(self, mock_bot):
        """cmd_stats formats and sends cache metrics."""
        mock_bot._cache.get_metrics.return_value = {
            "semantic": {"hit_rate": 80.0, "hits": 40, "misses": 10},
        }
        message = _make_message()
        await cmd_stats(mock_bot, message)

        message.answer.assert_called_once()
        text = message.answer.call_args[0][0]
        assert "80%" in text
        assert "40/50" in text


class TestCmdClear:
    """Test cmd_clear handler."""

    async def test_clears_cache_conversation(self, mock_bot):
        """cmd_clear calls cache.clear_conversation with user_id."""
        message = _make_message(user_id=777)
        await cmd_clear(mock_bot, message)

        mock_bot._cache.clear_conversation.assert_awaited_once_with(777)
        message.answer.assert_called_once()
        assert "очищена" in message.answer.call_args[0][0].lower()


class TestCmdMetrics:
    """Test cmd_metrics handler."""

    async def test_calls_pipeline_metrics(self, mock_bot):
        """cmd_metrics calls PipelineMetrics.get() and sends formatted text."""
        message = _make_message()
        with patch("telegram_bot.handlers.command_handlers.PipelineMetrics") as mock_pm:
            mock_metrics = MagicMock()
            mock_metrics.format_text.return_value = "p50=100ms p95=200ms"
            mock_pm.get.return_value = mock_metrics

            await cmd_metrics(mock_bot, message)

        message.answer.assert_called_once()
        text = message.answer.call_args[0][0]
        assert "p50" in text


class TestCmdStart:
    """Test cmd_start handler."""

    async def test_client_shows_main_menu(self, mock_bot):
        """cmd_start for client role shows client main menu."""
        message = _make_message()
        mock_bot._resolve_user_role = AsyncMock(return_value="client")

        with patch(
            "telegram_bot.dialogs.root_nav.show_client_main_menu",
            new_callable=AsyncMock,
        ) as mock_show_menu:
            await cmd_start(mock_bot, message)

            mock_show_menu.assert_called_once_with(message, i18n=None)
