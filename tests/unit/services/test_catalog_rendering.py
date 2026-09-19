"""Shared catalog rendering contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.handlers import catalog as catalog_handlers
from telegram_bot.services.apartment.catalog_rendering import send_catalog_results


@pytest.mark.asyncio
async def test_send_catalog_results_cards_uses_property_card_sender(monkeypatch) -> None:
    property_bot = MagicMock()
    monkeypatch.setattr(catalog_handlers, "_send_property_card", AsyncMock())
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

    assert catalog_handlers._send_property_card.await_count == 2
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_catalog_results_list_mode_sends_formatted_text() -> None:
    from aiogram.types import ReplyKeyboardMarkup

    message = MagicMock()
    message.answer = AsyncMock()
    reply_markup = ReplyKeyboardMarkup(keyboard=[])

    with patch("telegram_bot.dialogs.funnel.format_apartment_list", return_value="LIST"):
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
