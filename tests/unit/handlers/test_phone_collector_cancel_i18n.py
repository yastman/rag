"""Tests for i18n cancel message in phone_collector (#938)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class _MockI18n:
    def get(self, key: str, **kwargs):
        return {
            "phone-cancelled": "Request cancelled.",
        }.get(key, key)


async def test_cancel_uses_i18n_message():
    """on_phone_received with cancel input uses i18n.get('phone-cancelled')."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    message = MagicMock()
    message.text = "Отмена"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    with (
        patch(
            "telegram_bot.keyboards.phone_keyboard.is_phone_cancel",
            return_value=True,
        ),
        patch(
            "telegram_bot.keyboards.client_keyboard.build_client_keyboard",
            return_value=MagicMock(),
        ),
    ):
        await on_phone_received(message, state, i18n=_MockI18n())

    message.answer.assert_called_once()
    text_called = message.answer.call_args[0][0]
    assert text_called == "Request cancelled."


async def test_cancel_falls_back_without_i18n():
    """on_phone_received with no i18n falls back to default cancel text."""
    from telegram_bot.handlers.phone_collector import on_phone_received

    message = MagicMock()
    message.text = "Отмена"
    message.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    state.get_data = AsyncMock(return_value={})

    with (
        patch(
            "telegram_bot.keyboards.phone_keyboard.is_phone_cancel",
            return_value=True,
        ),
        patch(
            "telegram_bot.keyboards.client_keyboard.build_client_keyboard",
            return_value=MagicMock(),
        ),
    ):
        await on_phone_received(message, state, i18n=None)

    message.answer.assert_called_once()
    # Falls back to non-empty text (no exception)
    text_called = message.answer.call_args[0][0]
    assert text_called  # non-empty
