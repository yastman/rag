"""Shared helpers for regex-based filter extractors."""

from __future__ import annotations

from telegram_bot.services.text_utils import parse_int_with_k_suffix


class BaseFilterExtractor:
    """Base class for extractors that need shared parsing helpers."""

    def _parse_number(self, text: str) -> int | None:
        return parse_int_with_k_suffix(text)
