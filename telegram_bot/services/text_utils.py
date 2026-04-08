"""Small shared text utilities for regex-based query parsing."""

from __future__ import annotations


def parse_int_with_k_suffix(text: str) -> int | None:
    """Parse integer text, allowing spaces and Russian 'к' thousands suffix."""
    normalized = text.strip().replace(" ", "").replace("\xa0", "")
    if normalized.endswith("к"):
        normalized = normalized[:-1] + "000"

    try:
        return int(normalized)
    except ValueError:
        return None
