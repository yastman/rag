"""Shared helpers for sending catalog results as chat history messages."""

from __future__ import annotations

from typing import Any

from aiogram.types import Message

from telegram_bot.dialogs.funnel import format_apartment_list


async def send_catalog_results(
    *,
    message: Message,
    property_bot: Any,
    results: list[dict[str, Any]],
    total_count: int,
    view_mode: str,
    shown_start: int,
    telegram_id: int,
    reply_markup: Any = None,
) -> None:
    if view_mode == "list" or property_bot is None:
        text = format_apartment_list(results, shown_start=shown_start, total=total_count)
        await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
        return

    for result in results:
        await property_bot._send_property_card(message, result, telegram_id)
