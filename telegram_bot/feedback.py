"""User feedback utilities — inline keyboard builder and callback parser (#229)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


_FB_PREFIX = "fb:"


def build_feedback_keyboard(trace_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with like/dislike buttons encoding trace_id."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\U0001f44d Полезно",
                    callback_data=f"{_FB_PREFIX}1:{trace_id}",
                ),
                InlineKeyboardButton(
                    text="\U0001f44e Не помогло",
                    callback_data=f"{_FB_PREFIX}0:{trace_id}",
                ),
            ]
        ]
    )


def build_feedback_confirmation(*, liked: bool) -> InlineKeyboardMarkup:
    """Build single-button confirmation keyboard after feedback submitted."""
    emoji = "\u2705" if liked else "\U0001f4dd"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{emoji} Спасибо за отзыв!",
                    callback_data="fb:done",
                ),
            ]
        ]
    )


def parse_feedback_callback(data: str) -> tuple[float, str] | None:
    """Parse callback_data from feedback button.

    Returns (value, trace_id) or None if not a feedback callback.
    Format: fb:{0|1}:{trace_id}
    """
    if not data.startswith(_FB_PREFIX):
        return None

    parts = data.split(":", 2)  # ["fb", "0|1", "trace_id"]
    if len(parts) != 3:
        return None

    value_str, trace_id = parts[1], parts[2]
    if value_str not in ("0", "1"):
        return None
    if not trace_id:
        return None

    return float(value_str), trace_id
