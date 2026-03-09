"""Tests for bot menu handler edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")


@pytest.mark.asyncio()
async def test_handle_manager_no_forum_bridge_starts_phone_collection():
    """Without forum_bridge, manager button should start phone collection."""
    with patch("telegram_bot.bot.PropertyBot.__init__", return_value=None):
        from telegram_bot.bot import PropertyBot

        bot = PropertyBot.__new__(PropertyBot)
        bot._forum_bridge = None

    message = MagicMock()
    message.answer = AsyncMock()
    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    with patch("telegram_bot.handlers.phone_collector.start_phone_collection") as mock_phone:
        mock_phone.return_value = None
        await bot._handle_manager(message, state=state)

    mock_phone.assert_awaited_once()
    call_kwargs = mock_phone.call_args
    assert call_kwargs.kwargs.get("service_key") == "manager"
