"""User feedback utilities — inline keyboard builder and callback parser (***REMOVED***229, ***REMOVED***755).

Keyboards are constructed with :class:`aiogram.utils.keyboard.InlineKeyboardBuilder`
to follow the SDK convention enforced by issue ***REMOVED***1238.
"""

from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .callback_data import FeedbackCB, FeedbackReasonCB


logger = logging.getLogger(__name__)


***REMOVED*** 6 dislike reason codes → full category names (***REMOVED***755)
_REASON_CODES: dict[str, str] = {
    "wt": "wrong_topic",
    "mi": "missing_info",
    "bs": "bad_sources",
    "ha": "hallucination",
    "ic": "incomplete",
    "fm": "formatting",
}

***REMOVED*** Button labels for dislike reasons (displayed to user)
_REASON_LABELS: dict[str, str] = {
    "wt": "🎯 Не по теме",
    "mi": "🔍 Нет информации",
    "bs": "📚 Плохие источники",
    "ha": "🤥 Выдумал факты",
    "ic": "📝 Неполный ответ",
    "fm": "🎨 Плохой формат",
}


def build_feedback_keyboard(trace_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with like/dislike buttons encoding ``trace_id``.

    Layout: a single row of 2 buttons.
    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="\U0001f44d Полезно",
        callback_data=FeedbackCB(action="like", trace_id=trace_id),
    )
    builder.button(
        text="\U0001f44e Не помогло",
        callback_data=FeedbackCB(action="dislike", trace_id=trace_id),
    )
    builder.adjust(2)
    return builder.as_markup()


def build_dislike_reason_keyboard(trace_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with 6 dislike reason buttons (3 rows × 2) (***REMOVED***755).

    Button order follows :data:`_REASON_CODES` insertion order, which is
    guaranteed since Python 3.7.
    """
    builder = InlineKeyboardBuilder()
    for code in _REASON_CODES:
        builder.button(
            text=_REASON_LABELS[code],
            callback_data=FeedbackReasonCB(code=code, trace_id=trace_id),
        )
    builder.adjust(2)
    return builder.as_markup()


def build_feedback_confirmation(*, liked: bool) -> InlineKeyboardMarkup:
    """Build single-button confirmation keyboard after feedback submitted."""
    emoji = "\u2705" if liked else "\U0001f4dd"
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{emoji} Спасибо за отзыв!",
        callback_data=FeedbackCB(action="done", trace_id=""),
    )
    builder.adjust(1)
    return builder.as_markup()


def parse_feedback_callback(data: str) -> tuple[float, str, str | None] | None:
    """Parse callback_data from feedback button.

    Supports both new CallbackData format (fb:like/dislike:, fbr:code:) and
    legacy format (fb:1/0:, fb:r:code:) for backward compatibility.

    Returns (value, trace_id, reason) or None if not a feedback callback.
    """
    ***REMOVED*** New FeedbackReasonCB format: fbr:{code}:{trace_id}
    if data.startswith("fbr:"):
        try:
            reason_cb = FeedbackReasonCB.unpack(data)
        except Exception:
            return None
        if reason_cb.code not in _REASON_CODES:
            return None
        if not reason_cb.trace_id:
            return None
        return 0.0, reason_cb.trace_id, _REASON_CODES[reason_cb.code]

    if not data.startswith("fb:"):
        return None

    ***REMOVED*** New FeedbackCB format: fb:{like|dislike|done}:{trace_id}
    try:
        feedback_cb = FeedbackCB.unpack(data)
        if feedback_cb.action == "like":
            if not feedback_cb.trace_id:
                return None
            return 1.0, feedback_cb.trace_id, None
        if feedback_cb.action == "dislike":
            if not feedback_cb.trace_id:
                return None
            return 0.0, feedback_cb.trace_id, None
        if feedback_cb.action == "done":
            return None
        ***REMOVED*** Unknown action (legacy "1", "0") → fall through to legacy parser below
    except Exception:
        logger.warning("Failed to parse feedback callback %r", data, exc_info=True)

    ***REMOVED*** Legacy reason callback: fb:r:{code}:{trace_id}
    if data.startswith("fb:r:"):
        parts = data.split(":", 3)  ***REMOVED*** ["fb", "r", "code", "trace_id"]
        if len(parts) != 4:
            return None
        code, trace_id = parts[2], parts[3]
        if code not in _REASON_CODES:
            return None
        if not trace_id:
            return None
        return 0.0, trace_id, _REASON_CODES[code]

    ***REMOVED*** Legacy like/dislike callback: fb:{0|1}:{trace_id}
    parts = data.split(":", 2)  ***REMOVED*** ["fb", "0|1", "trace_id"]
    if len(parts) != 3:
        return None

    value_str, trace_id = parts[1], parts[2]
    if value_str not in ("0", "1"):
        return None
    if not trace_id:
        return None

    return float(value_str), trace_id, None
