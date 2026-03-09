"""Shared phone keyboard and validation utilities.

Used by phone_collector FSM and viewing dialog to avoid duplication.
"""

from __future__ import annotations

import re

import phonenumbers
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


_PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")
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


def validate_phone(text: str) -> bool:
    """Validate phone number format (7-15 digits, optional +)."""
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    return bool(_PHONE_PATTERN.match(cleaned))


def normalize_phone(raw: str, default_region: str = "BG") -> str | None:
    """Parse and normalize phone to E164 format. Returns None if invalid."""
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)
    for region in (default_region, None):
        try:
            parsed = phonenumbers.parse(cleaned, region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            continue
    return None
