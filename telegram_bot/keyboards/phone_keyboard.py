"""Shared phone keyboard and validation utilities.

Used by phone_collector FSM and viewing dialog to avoid duplication.

Phone normalization itself lives in ``telegram_bot.phone_utils`` (UI-free) so
that ``mini_app/phone.py`` can reuse it without dragging in aiogram. This
module re-exports ``normalize_phone`` / ``validate_phone`` for backward
compatibility with existing callers.
"""

from __future__ import annotations

import re

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from telegram_bot.phone_utils import normalize_phone, validate_phone


__all__ = [
    "build_phone_keyboard",
    "is_phone_attempt",
    "is_phone_cancel",
    "normalize_phone",
    "validate_phone",
]


_DIGITS_RE = re.compile(r"\D")
_CANCEL_TEXTS = frozenset({"❌ отмена", "отмена"})


def build_phone_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with 'Share contact' + 'Cancel' buttons."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="\U0001f4f1 Поделиться контактом", request_contact=True)],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def is_phone_cancel(text: str) -> bool:
    """Check if text is a cancel command from reply keyboard."""
    return text.strip().lower() in _CANCEL_TEXTS


def is_phone_attempt(text: str) -> bool:
    """Check if text looks like a phone number attempt (5+ digits)."""
    digits = _DIGITS_RE.sub("", text)
    return len(digits) >= 5
