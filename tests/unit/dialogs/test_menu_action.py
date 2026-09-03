"""Tests for menu button on_click -> bot handler dispatch flow (#444).

#3216 removed the inline ``PropertyBot.handle_menu_action`` agent bridge;
these tests pin the surviving dialog dispatcher (``client_menu.on_menu_action``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


async def test_on_menu_action_services_closes_dialog_and_calls_handler():
    """Legacy non-dialog buttons should close the root dialog and call existing handlers."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    mock_bot = AsyncMock()
    mock_bot._handle_services = AsyncMock()

    callback = MagicMock()
    callback.from_user = None
    callback.message = MagicMock()
    button = MagicMock()
    button.widget_id = "services"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "i18n": "i18n-stub"}

    await on_menu_action(callback, button, manager)

    manager.done.assert_called_once()
    mock_bot._handle_services.assert_awaited_once_with(callback.message, i18n="i18n-stub")


async def test_on_menu_action_bookmarks_rebinds_from_user_to_callback_actor():
    """Bookmark handler must receive the clicking user, not the bot-authored message actor."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    mock_bot = AsyncMock()
    mock_bot._handle_bookmarks = AsyncMock()

    callback = MagicMock()
    callback.from_user = MagicMock(id=777)
    callback.message = MagicMock()
    callback.message.from_user = MagicMock(id=42)
    button = MagicMock()
    button.widget_id = "bookmarks"

    manager = AsyncMock()
    manager.done = AsyncMock()
    manager.middleware_data = {"property_bot": mock_bot, "state": "state-stub"}

    await on_menu_action(callback, button, manager)

    passed_message = mock_bot._handle_bookmarks.await_args.args[0]
    assert passed_message.from_user is callback.from_user
    assert mock_bot._handle_bookmarks.await_args.args[1] == "state-stub"


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
    callback.from_user = None
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


async def test_on_menu_action_manager_rebinds_from_user_to_callback_actor():
    """Manager handler fallback paths rely on the real clicking user in message.from_user."""
    from telegram_bot.dialogs.client_menu import on_menu_action

    mock_bot = AsyncMock()
    mock_bot._handle_manager = AsyncMock()

    callback = MagicMock()
    callback.from_user = MagicMock(id=888)
    callback.message = MagicMock()
    callback.message.from_user = MagicMock(id=99)
    button = MagicMock()
    button.widget_id = "manager"

    manager = AsyncMock()
    manager.middleware_data = {
        "property_bot": mock_bot,
        "i18n": "i18n-stub",
        "state": "state-stub",
    }

    await on_menu_action(callback, button, manager)

    passed_message = mock_bot._handle_manager.await_args.args[0]
    assert passed_message.from_user is callback.from_user

