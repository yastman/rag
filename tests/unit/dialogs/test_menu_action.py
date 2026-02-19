"""Tests for menu button on_click -> handle_menu_action flow (#444)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


async def test_on_menu_action_calls_manager_done_and_handle_menu_action():
    """on_menu_action closes dialog, then calls handle_menu_action with mapped query and locale."""
    from telegram_bot.dialogs.client_menu import _BUTTON_QUERIES, on_menu_action

    mock_bot = AsyncMock()
    mock_bot.handle_menu_action = AsyncMock()

    callback = MagicMock()
    button = MagicMock()
    button.widget_id = "catalog"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "locale": "en"}

    await on_menu_action(callback, button, manager)

    manager.done.assert_called_once()
    mock_bot.handle_menu_action.assert_called_once_with(
        callback, _BUTTON_QUERIES["catalog"], locale="en"
    )


async def test_on_menu_action_no_bot_silently_skips():
    """on_menu_action skips handle_menu_action when property_bot not in middleware."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    callback = MagicMock()
    button = MagicMock()
    button.widget_id = "catalog"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {}  # no property_bot

    # Should not raise
    await on_menu_action(callback, button, manager)

    manager.done.assert_called_once()


async def test_on_manager_action_calls_manager_done_and_handle_menu_action():
    """on_manager_action closes dialog, then calls handle_menu_action with mapped query and locale."""
    from telegram_bot.dialogs.manager_menu import _BUTTON_QUERIES, on_manager_action

    mock_bot = AsyncMock()
    mock_bot.handle_menu_action = AsyncMock()

    callback = MagicMock()
    button = MagicMock()
    button.widget_id = "mgr_deals"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "locale": "uk"}

    await on_manager_action(callback, button, manager)

    manager.done.assert_called_once()
    mock_bot.handle_menu_action.assert_called_once_with(
        callback, _BUTTON_QUERIES["mgr_deals"], locale="uk"
    )


async def test_on_crm_action_calls_manager_done_and_handle_menu_action():
    """on_crm_action closes dialog, then calls handle_menu_action with mapped query and locale."""
    from telegram_bot.dialogs.crm_submenu import _BUTTON_QUERIES, on_crm_action

    mock_bot = AsyncMock()
    mock_bot.handle_menu_action = AsyncMock()

    callback = MagicMock()
    button = MagicMock()
    button.widget_id = "crm_create_deal"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "locale": "ru"}

    await on_crm_action(callback, button, manager)

    manager.done.assert_called_once()
    mock_bot.handle_menu_action.assert_called_once_with(
        callback, _BUTTON_QUERIES["crm_create_deal"], locale="ru"
    )


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
