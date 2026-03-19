"""Tests for menu button on_click -> handle_menu_action flow (#444)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


async def test_on_menu_action_services_closes_dialog_and_calls_handler():
    """Legacy non-dialog buttons should close the root dialog and call existing handlers."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    mock_bot = AsyncMock()
    mock_bot._handle_services = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    button = MagicMock()
    button.widget_id = "services"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "i18n": "i18n-stub"}

    await on_menu_action(callback, button, manager)

    manager.done.assert_called_once()
    mock_bot._handle_services.assert_awaited_once_with(callback.message, i18n="i18n-stub")


async def test_on_menu_action_no_bot_silently_skips():
    """on_menu_action exits quietly when property_bot is absent."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    callback = MagicMock()
    callback.message = MagicMock()
    button = MagicMock()
    button.widget_id = "services"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {}  # no property_bot

    # Should not raise
    await on_menu_action(callback, button, manager)

    manager.done.assert_not_called()


async def test_on_menu_action_manager_reuses_dialog_manager():
    """Manager button should keep SDK ownership and start the manager flow via dialog_manager."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    mock_bot = AsyncMock()
    mock_bot._handle_manager = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    button = MagicMock()
    button.widget_id = "manager"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {
        "property_bot": mock_bot,
        "i18n": "i18n-stub",
        "state": "state-stub",
    }

    await on_menu_action(callback, button, manager)

    manager.done.assert_not_called()
    mock_bot._handle_manager.assert_awaited_once_with(
        callback.message,
        i18n="i18n-stub",
        state="state-stub",
        dialog_manager=manager,
    )


async def test_on_manager_action_calls_manager_done_and_handle_menu_action():
    """on_manager_action closes dialog, then calls handle_menu_action with mapped query and locale."""
    from telegram_bot.dialogs.manager_menu import _BUTTON_QUERIES, on_manager_action

    mock_bot = AsyncMock()
    mock_bot.handle_menu_action = AsyncMock()

    callback = MagicMock()
    button = MagicMock()
    button.widget_id = "mgr_search"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "locale": "uk"}

    await on_manager_action(callback, button, manager)

    manager.done.assert_called_once()
    mock_bot.handle_menu_action.assert_called_once_with(
        callback, _BUTTON_QUERIES["mgr_search"], locale="uk"
    )


def test_crm_submenu_is_navigation_hub():
    """CRM submenu (#697 refactor) uses Start buttons — no action dispatching."""
    from telegram_bot.dialogs.crm_submenu import crm_submenu_dialog
    from telegram_bot.dialogs.states import CRMMenuSG

    # Verify dialog uses CRMMenuSG.main state (not old CrmSubmenuSG)
    states = [w.get_state() for w in crm_submenu_dialog.windows.values()]
    assert CRMMenuSG.main in states


def test_handle_menu_action_exists_on_property_bot():
    """PropertyBot has a handle_menu_action method."""
    import inspect

    from telegram_bot.bot import PropertyBot

    assert hasattr(PropertyBot, "handle_menu_action")
    assert inspect.iscoroutinefunction(PropertyBot.handle_menu_action)


def test_handle_menu_action_signature():
    """handle_menu_action accepts (self, callback, query_text, locale)."""
    import inspect

    from telegram_bot.bot import PropertyBot

    sig = inspect.signature(PropertyBot.handle_menu_action)
    params = list(sig.parameters.keys())
    assert "callback" in params
    assert "query_text" in params
    assert "locale" in params
    assert sig.parameters["locale"].default == "ru"


async def test_handle_menu_action_returns_early_if_no_from_user():
    """handle_menu_action returns without error if callback.from_user is None."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)

        callback = MagicMock()
        callback.from_user = None
        callback.message = MagicMock()

        # Should not raise
        await bot.handle_menu_action(callback, "some query")


async def test_handle_menu_action_returns_early_if_no_message():
    """handle_menu_action returns without error if callback.message is None."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)

        callback = MagicMock()
        callback.from_user = MagicMock()
        callback.message = None

        # Should not raise
        await bot.handle_menu_action(callback, "some query")
