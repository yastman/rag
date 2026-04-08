"""Tests for client menu wiring fixes (#658)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from ._property_bot_ast import get_default_map, get_parameter_names, get_property_bot_method


def test_handle_menu_button_accepts_dialog_manager():
    """handle_menu_button accepts state and optional dialog_manager."""
    method = get_property_bot_method("handle_menu_button")
    params = get_parameter_names(method)
    assert "state" in params
    assert "dialog_manager" in params
    assert get_default_map(method)["dialog_manager"] is None


def test_handle_search_accepts_dialog_manager():
    """_handle_search accepts optional dialog_manager."""
    method = get_property_bot_method("_handle_search")
    params = get_parameter_names(method)
    assert "dialog_manager" in params
    assert get_default_map(method)["dialog_manager"] is None


async def test_handle_menu_button_clears_stale_fsm_state():
    """handle_menu_button clears FSM state if user was in phone collection (#658)."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)

        message = MagicMock()
        message.text = "🔑 Услуги"
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_state = AsyncMock(return_value="PhoneCollectorStates:waiting_phone")
        state.clear = AsyncMock()

        # Mock _handle_services to avoid real logic
        bot._handle_services = AsyncMock()

        await bot.handle_menu_button(message, state)

        state.clear.assert_called_once()
        bot._handle_services.assert_called_once_with(message, i18n=None)


async def test_handle_menu_button_no_clear_when_state_is_none():
    """handle_menu_button does not clear state when no active FSM state."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)

        message = MagicMock()
        message.text = "🔑 Услуги"
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)
        state.clear = AsyncMock()

        bot._handle_services = AsyncMock()

        await bot.handle_menu_button(message, state)

        state.clear.assert_not_called()
        bot._handle_services.assert_called_once_with(message, i18n=None)


async def test_handle_menu_button_no_clear_for_unrelated_state():
    """Only PhoneCollectorStates should be cleared by menu handler."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)

        message = MagicMock()
        message.text = "🔑 Услуги"
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_state = AsyncMock(return_value="FunnelSG:budget")
        state.clear = AsyncMock()

        bot._handle_services = AsyncMock()

        await bot.handle_menu_button(message, state)

        state.clear.assert_not_called()
        bot._handle_services.assert_called_once_with(message, i18n=None)


async def test_handle_search_starts_funnel_dialog():
    """_handle_search starts FunnelSG.city dialog when dialog_manager available (#658, #697, #712)."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from aiogram_dialog import StartMode

        from telegram_bot.bot import PropertyBot
        from telegram_bot.dialogs.states import FunnelSG

        bot = PropertyBot.__new__(PropertyBot)

        message = MagicMock()
        dialog_manager = AsyncMock()
        dialog_manager.start = AsyncMock()

        await bot._handle_search(message, dialog_manager)

        dialog_manager.start.assert_called_once()
        call_args = dialog_manager.start.call_args
        assert call_args[0][0] == FunnelSG.city
        assert call_args.kwargs["mode"] == StartMode.RESET_STACK


async def test_handle_search_fallback_without_dialog_manager():
    """_handle_search falls back to RAG text when dialog_manager is None (#658)."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot.handle_menu_action_text = AsyncMock()

        message = MagicMock()

        await bot._handle_search(message, None)

        bot.handle_menu_action_text.assert_called_once_with(message, "Подбери апартаменты")


async def test_handle_menu_button_passes_dialog_manager_to_search():
    """handle_menu_button passes dialog_manager to _handle_search (#658)."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)

        message = MagicMock()
        message.text = "🏠 Подобрать квартиру"

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        dialog_manager = AsyncMock()
        bot._handle_search = AsyncMock()

        await bot.handle_menu_button(message, state, dialog_manager)

        bot._handle_search.assert_called_once_with(message, dialog_manager)


async def test_handle_menu_button_parses_localized_labels_with_hub():
    """handle_menu_button should pass i18n_hub to parse_menu_button for non-RU labels."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot._i18n_hub = MagicMock()
        bot._handle_services = AsyncMock()

        message = MagicMock()
        message.text = "🔑 Послуги"
        message.answer = AsyncMock()

        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)

        with patch("telegram_bot.bot.parse_menu_button", return_value="services") as parse_mock:
            await bot.handle_menu_button(message, state, i18n=MagicMock())

        parse_mock.assert_called_once_with("🔑 Послуги", i18n_hub=bot._i18n_hub)
        bot._handle_services.assert_called_once()


def test_handoff_dialog_registered():
    """handoff_dialog must be registered via include_router (fixes UnregisteredDialogError)."""
    import ast
    from pathlib import Path

    bot_py = Path("telegram_bot/bot.py").read_text()
    tree = ast.parse(bot_py)

    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "handoff_dialog"
        ):
            found = True
            break
    assert found, "handoff_dialog is not registered via dp.include_router()"


def test_client_menu_dialog_is_registered():
    """client_menu_dialog should be registered on the dispatcher for SDK root navigation."""
    import ast
    from pathlib import Path

    bot_py = Path("telegram_bot/bot.py").read_text()
    tree = ast.parse(bot_py)

    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "client_menu_dialog"
        ):
            found = True
            break

    assert found, "client_menu_dialog is not registered via dp.include_router()"
