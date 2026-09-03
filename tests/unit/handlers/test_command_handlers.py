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
        """Router registers handlers for all 7 commands."""
        router = create_commands_router(mock_bot)
        # Check message handlers count (7 command handlers)
        assert len(router.message.handlers) == 7


class TestCmdHelp:
    """Test cmd_help handler."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_clears_cache_conversation(self, mock_bot):
        """cmd_clear calls cache.clear_conversation with user_id."""
        message = _make_message(user_id=777)
        await cmd_clear(mock_bot, message)

        mock_bot._cache.clear_conversation.assert_awaited_once_with(777)
        message.answer.assert_called_once()
        assert "очищена" in message.answer.call_args[0][0].lower()


class TestCmdMetrics:
    """Test cmd_metrics handler."""

    @pytest.mark.asyncio
    async def test_points_to_structured_json_logs(self, mock_bot):
        """cmd_metrics points operators at JSON product logs after Prometheus removal."""
        message = _make_message()

        await cmd_metrics(mock_bot, message)

        message.answer.assert_called_once()
        text = message.answer.call_args[0][0]
        assert "structured JSON logs" in text
        assert "event=pipeline_latency" in text
        assert "event=pipeline_counter" in text
        assert "Prometheus /metrics" in text


class TestCmdStart:
    """Test cmd_start handler."""

    @pytest.mark.asyncio
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


class TestCmdClearcache:
    """Test cmd_clearcache keyboard structure."""

    @pytest.mark.asyncio
    async def test_keyboard_has_five_rows(self, mock_bot):
        """cmd_clearcache keyboard now has 5 rows (history + all_and_history added)."""
        from telegram_bot.handlers.command_handlers import cmd_clearcache

        mock_bot._is_admin = MagicMock(return_value=True)
        message = _make_message()
        await cmd_clearcache(mock_bot, message)

        message.answer.assert_called_once()
        kb = message.answer.call_args.kwargs.get("reply_markup") or message.answer.call_args.args[1]
        assert hasattr(kb, "inline_keyboard")
        assert len(kb.inline_keyboard) == 5

    @pytest.mark.asyncio
    async def test_keyboard_contains_history_buttons(self, mock_bot):
        """cc:history and cc:all_and_history buttons are present."""
        from telegram_bot.handlers.command_handlers import cmd_clearcache

        mock_bot._is_admin = MagicMock(return_value=True)
        message = _make_message()
        await cmd_clearcache(mock_bot, message)

        kb = message.answer.call_args.kwargs.get("reply_markup") or message.answer.call_args.args[1]
        all_data = {btn.callback_data for row in kb.inline_keyboard for btn in row}
        assert "cc:history" in all_data
        assert "cc:all_and_history" in all_data

    @pytest.mark.asyncio
    async def test_clearcache_requires_admin_command_rejects_non_admin(self, mock_bot):
        """Non-admin user gets an error reply; no keyboard is sent."""
        from telegram_bot.handlers.command_handlers import cmd_clearcache

        mock_bot._is_admin = MagicMock(return_value=False)
        message = _make_message(user_id=99999)
        await cmd_clearcache(mock_bot, message)

        message.answer.assert_called_once()
        # Must NOT contain an InlineKeyboardMarkup (no cache tier selection)
        call_kwargs = message.answer.call_args.kwargs
        assert "reply_markup" not in call_kwargs or call_kwargs.get("reply_markup") is None

    @pytest.mark.asyncio
    async def test_clearcache_requires_admin_command_admin_gets_keyboard(self, mock_bot):
        """Admin user gets the cache tier selection keyboard."""
        from telegram_bot.handlers.command_handlers import cmd_clearcache

        mock_bot._is_admin = MagicMock(return_value=True)
        message = _make_message(user_id=1)
        await cmd_clearcache(mock_bot, message)

        message.answer.assert_called_once()
        kb = message.answer.call_args.kwargs.get("reply_markup")
        assert kb is not None
        assert hasattr(kb, "inline_keyboard")


class TestClearcacheCallbackRequiresAdmin:
    """Admin gate for cc: callback — non-admin cannot flush caches."""

    def _make_callback(self, user_id: int, data: str = "cc:all") -> MagicMock:
        cb = MagicMock()
        cb.data = data
        cb.answer = AsyncMock()
        cb.from_user = MagicMock(id=user_id)
        cb.message = MagicMock()
        cb.message.chat = MagicMock(id=user_id)
        cb.message.edit_text = AsyncMock()
        return cb

    def _make_bot(self, *, is_admin: bool) -> MagicMock:
        bot = MagicMock()
        bot._is_admin = MagicMock(return_value=is_admin)
        bot._cache = MagicMock()
        bot._cache.clear_all_caches = AsyncMock(return_value={})
        bot._cache.clear_semantic_cache = AsyncMock(return_value=0)
        bot._cache.clear_by_tier = AsyncMock(return_value=0)
        bot._cache.clear_conversation = AsyncMock()
        return bot

    @pytest.mark.asyncio
    async def test_clearcache_requires_admin_callback_rejects_non_admin(self):
        """Non-admin cc: callback is answered with an error; no cache is flushed."""
        from telegram_bot.handlers.bot_crm_callbacks import handle_clearcache_callback

        bot = self._make_bot(is_admin=False)
        cb = self._make_callback(user_id=99999, data="cc:all")

        await handle_clearcache_callback(bot, cb)

        bot._cache.clear_all_caches.assert_not_awaited()
        cb.answer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clearcache_requires_admin_callback_allows_admin(self):
        from telegram_bot.handlers.bot_crm_callbacks import handle_clearcache_callback

        bot = self._make_bot(is_admin=True)
        cb = self._make_callback(user_id=1, data="cc:all")

        await handle_clearcache_callback(bot, cb)

        bot._cache.clear_all_caches.assert_awaited_once()
