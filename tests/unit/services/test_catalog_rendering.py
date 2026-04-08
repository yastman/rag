"""Shared catalog rendering contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.catalog_rendering import send_catalog_results


@pytest.mark.asyncio
async def test_send_catalog_results_cards_uses_property_card_sender() -> None:
    property_bot = MagicMock()
    property_bot._send_property_card = AsyncMock()
    message = MagicMock()
    message.answer = AsyncMock()

    await send_catalog_results(
        message=message,
        property_bot=property_bot,
        results=[{"id": "a1"}, {"id": "a2"}],
        total_count=20,
        view_mode="cards",
        shown_start=1,
        telegram_id=42,
    )

    assert property_bot._send_property_card.await_count == 2
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_catalog_results_list_mode_sends_formatted_text() -> None:
    from aiogram.types import ReplyKeyboardMarkup

    message = MagicMock()
    message.answer = AsyncMock()
    reply_markup = ReplyKeyboardMarkup(keyboard=[])

    with patch(
        "telegram_bot.services.catalog_rendering.format_apartment_list", return_value="LIST"
    ):
        await send_catalog_results(
            message=message,
            property_bot=None,
            results=[{"id": "a1"}],
            total_count=20,
            view_mode="list",
            shown_start=1,
            telegram_id=42,
            reply_markup=reply_markup,
        )

    message.answer.assert_awaited_once_with("LIST", parse_mode="HTML", reply_markup=reply_markup)


@pytest.mark.asyncio
async def test_render_catalog_results_with_keyboard_cards_mode_adds_keyboard_shell() -> None:
    from telegram_bot.dialogs.catalog_transport import render_catalog_results_with_keyboard

    message = MagicMock()
    message.answer = AsyncMock()
    property_bot = MagicMock()
    property_bot._send_property_card = AsyncMock()

    await render_catalog_results_with_keyboard(
        message=message,
        property_bot=property_bot,
        results=[{"id": "apt-1"}],
        total_count=12,
        view_mode="cards",
        shown_start=1,
        shown_count=10,
        telegram_id=123,
    )

    assert property_bot._send_property_card.await_count == 1
    assert message.answer.await_args.kwargs["reply_markup"] is not None
