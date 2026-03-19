"""Transport-level helpers for catalog rendering flows."""

from __future__ import annotations

from typing import Any

from telegram_bot.dialogs.funnel import format_apartment_list
from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard
from telegram_bot.services.catalog_rendering import send_catalog_results


async def render_catalog_results_with_keyboard(
    *,
    message: Any,
    property_bot: Any,
    results: list[dict[str, Any]],
    total_count: int,
    view_mode: str,
    shown_start: int,
    shown_count: int,
    telegram_id: int,
) -> None:
    keyboard = build_catalog_keyboard(shown=shown_count, total=total_count)
    if view_mode == "list" or property_bot is None:
        text = format_apartment_list(results, shown_start=shown_start, total=total_count)
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        return

    await send_catalog_results(
        message=message,
        property_bot=property_bot,
        results=results,
        total_count=total_count,
        view_mode=view_mode,
        shown_start=shown_start,
        telegram_id=telegram_id,
    )
    await message.answer("\u200b", reply_markup=keyboard)
