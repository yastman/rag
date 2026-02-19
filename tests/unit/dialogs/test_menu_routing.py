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


async def test_cmd_start_client_starts_client_menu(mock_config):
    """cmd_start routes client user to ClientMenuSG.main."""
    from telegram_bot.dialogs.states import ClientMenuSG

    dialog_manager = AsyncMock()
    message = MagicMock()
    message.from_user.id = 42
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

    dialog_manager.start.assert_called_once()
    call_args = dialog_manager.start.call_args
    assert call_args.args[0] == ClientMenuSG.main


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


async def test_cmd_start_manager_without_kommo_starts_client_menu(mock_config):
    """cmd_start routes manager (kommo disabled) to ClientMenuSG.main."""
    from telegram_bot.dialogs.states import ClientMenuSG

    mock_config.kommo_enabled = False
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
    assert call_args.args[0] == ClientMenuSG.main


async def test_cmd_start_fallback_without_dialog_manager(mock_config):
    """cmd_start falls back to text response when dialog_manager is None."""
    message = MagicMock()
    message.from_user.id = 42
    message.answer = AsyncMock()

    with (
        patch("telegram_bot.bot.PropertyBot.__init__", return_value=None),
        patch("telegram_bot.bot.render_start_menu", return_value="Welcome!"),
    ):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.config = mock_config
        bot._user_service = None

        async def fake_resolve_role(user_id: int) -> str:
            return "client"

        bot._resolve_user_role = fake_resolve_role

        await bot.cmd_start(message, dialog_manager=None)

    message.answer.assert_called_once_with("Welcome!")
