"""Tests for /start command role-based menu routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_config():
    """Minimal BotConfig mock."""
    cfg = MagicMock()
    cfg.telegram_token = "fake-token"
    cfg.manager_ids = []
    cfg.admin_ids = []
    cfg.kommo_enabled = False
    cfg.domain = "недвижимость"
    cfg.domain_language = "русском языке"
    return cfg


async def test_cmd_start_client_shows_reply_keyboard_even_with_dialog_manager(mock_config):
    """cmd_start routes client users to the lower reply keyboard root."""
    from aiogram.types import ReplyKeyboardMarkup

    dialog_manager = AsyncMock()
    message = MagicMock()
    message.from_user.id = 42
    message.from_user.first_name = "Test"
    message.answer = AsyncMock()

    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None

        async def fake_resolve_role(user_id: int) -> str:
            return "client"

        bot._resolve_user_role = fake_resolve_role

        await bot.cmd_start(message, dialog_manager=dialog_manager)

    dialog_manager.reset_stack.assert_awaited_once_with(remove_keyboard=True)
    message.answer.assert_called_once()
    _, kwargs = message.answer.call_args
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)


async def test_cmd_start_manager_with_kommo_starts_manager_menu(mock_config):
    """cmd_start routes manager (kommo_enabled) to ManagerMenuSG.main."""
    from telegram_bot.dialogs.states import ManagerMenuSG

    mock_config.kommo_enabled = True
    dialog_manager = AsyncMock()
    message = MagicMock()
    message.from_user.id = 99
    message.answer = AsyncMock()

    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None

        async def fake_resolve_role(user_id: int) -> str:
            return "manager"

        bot._resolve_user_role = fake_resolve_role

        await bot.cmd_start(message, dialog_manager=dialog_manager)

    dialog_manager.start.assert_called_once()
    call_args = dialog_manager.start.call_args
    assert call_args.args[0] == ManagerMenuSG.main


async def test_cmd_start_manager_without_kommo_shows_client_reply_keyboard(mock_config):
    """Managers without CRM mode should also land in the lower client root."""
    from aiogram.types import ReplyKeyboardMarkup

    mock_config.kommo_enabled = False
    dialog_manager = AsyncMock()
    message = MagicMock()
    message.from_user.id = 99
    message.from_user.first_name = "Test"
    message.answer = AsyncMock()

    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None

        async def fake_resolve_role(user_id: int) -> str:
            return "manager"

        bot._resolve_user_role = fake_resolve_role

        await bot.cmd_start(message, dialog_manager=dialog_manager)

    dialog_manager.reset_stack.assert_awaited_once_with(remove_keyboard=True)
    message.answer.assert_called_once()
    _, kwargs = message.answer.call_args
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)


async def test_cmd_start_fallback_without_dialog_manager(mock_config):
    """cmd_start sends ReplyKeyboard when dialog_manager is absent."""
    from aiogram.types import ReplyKeyboardMarkup

    message = MagicMock()
    message.from_user.id = 42
    message.from_user.first_name = "Test"
    message.answer = AsyncMock()

    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None

        async def fake_resolve_role(user_id: int) -> str:
            return "client"

        bot._resolve_user_role = fake_resolve_role

        await bot.cmd_start(message, dialog_manager=None)

    message.answer.assert_called_once()
    _, kwargs = message.answer.call_args
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)
