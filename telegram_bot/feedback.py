"""User feedback utilities — inline keyboard builder and callback parser (#229, #755)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


_FB_PREFIX = "fb:"

# 6 dislike reason codes → full category names (#755)
_REASON_CODES: dict[str, str] = {
    "wt": "wrong_topic",
    "mi": "missing_info",
    "bs": "bad_sources",
    "ha": "hallucination",
    "ic": "incomplete",
    "fm": "formatting",
}

# Button labels for dislike reasons (displayed to user)
_REASON_LABELS: dict[str, str] = {
    "wt": "🎯 Не по теме",
    "mi": "🔍 Нет информации",
    "bs": "📚 Плохие источники",
    "ha": "🤥 Выдумал факты",
    "ic": "📝 Неполный ответ",
    "fm": "🎨 Плохой формат",
}


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


def build_dislike_reason_keyboard(trace_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with 6 dislike reason buttons (3 rows × 2) (#755)."""
    # dict insertion order guaranteed in Python 3.7+; layout follows _REASON_CODES order
    codes = list(_REASON_CODES.keys())
    rows = []
    for i in range(0, len(codes), 2):
        row = []
        for code in codes[i : i + 2]:
            row.append(
                InlineKeyboardButton(
                    text=_REASON_LABELS[code],
                    callback_data=f"{_FB_PREFIX}r:{code}:{trace_id}",
                )
            )
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def parse_feedback_callback(data: str) -> tuple[float, str, str | None] | None:
    """Parse callback_data from feedback button.

    Returns (value, trace_id, reason) or None if not a feedback callback.

    Formats:
      fb:{0|1}:{trace_id}          — initial like/dislike (reason=None)
      fb:r:{code}:{trace_id}       — dislike reason selection (value=0.0)
    """
    if not data.startswith(_FB_PREFIX):
        return None

    # Reason callback: fb:r:{code}:{trace_id}
    if data.startswith(f"{_FB_PREFIX}r:"):
        parts = data.split(":", 3)  # ["fb", "r", "code", "trace_id"]
        if len(parts) != 4:
            return None
        code, trace_id = parts[2], parts[3]
        if code not in _REASON_CODES:
            return None
        if not trace_id:
            return None
        return 0.0, trace_id, _REASON_CODES[code]

    # Initial like/dislike callback: fb:{0|1}:{trace_id}
    parts = data.split(":", 2)  # ["fb", "0|1", "trace_id"]
    if len(parts) != 3:
        return None

    value_str, trace_id = parts[1], parts[2]
    if value_str not in ("0", "1"):
        return None
    if not trace_id:
        return None

    return float(value_str), trace_id, None
