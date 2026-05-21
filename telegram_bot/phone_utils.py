"""Shared phone-normalization helpers.

Single source of truth for phone validation/normalization. Used by:
- ``telegram_bot/keyboards/phone_keyboard.py`` (bot reply-keyboard flow)
- ``mini_app/phone.py`` (Mini App ``/api/phone`` Pydantic validator)

Closes the duplication called out in ***REMOVED***1614 — Mini App previously redeclared a
``_PHONE_RE = ^\\+?\\d{7,15}$`` regex that accepted impossible numbers like
``+11111111111`` and never normalized to E.164. This module routes both
consumers through ``phonenumbers.is_valid_number`` and E.164 formatting.

This module is intentionally UI-free (no aiogram / no FastAPI) so it can be
imported from either context without side-effects.
"""

from __future__ import annotations

import re

import phonenumbers


_SEPARATORS_RE = re.compile(r"[\s\-\(\)]")


def _strip_separators(raw: str) -> str:
    """Remove whitespace, dashes, and parentheses commonly typed by users."""
    return _SEPARATORS_RE.sub("", raw)


def normalize_phone(raw: str, default_region: str = "BG") -> str | None:
    """Parse and normalize ``raw`` to E.164 format.

    Tries the supplied ``default_region`` first (Bulgaria, the primary user
    base) and then attempts a region-less parse (which works when the input
    is already in international ``+CC...`` form).

    Returns
    -------
    str | None
        E.164 string (e.g. ``"+359888123456"``) on a valid number, ``None``
        otherwise.
    """
    cleaned = _strip_separators(raw)
    for region in (default_region, None):
        try:
            parsed = phonenumbers.parse(cleaned, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return None


def validate_phone(text: str, default_region: str = "BG") -> bool:
    """Return ``True`` iff ``text`` parses to a valid phone number.

    Backed by :func:`normalize_phone`, so impossible-but-digit-count-valid
    inputs like ``+11111111111`` correctly return ``False``.
    """
    return normalize_phone(text, default_region=default_region) is not None
