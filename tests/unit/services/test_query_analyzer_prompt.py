"""Regression guard for QueryAnalyzer SYSTEM_PROMPT (***REMOVED***1401).

The document/CSV pipeline canonical filter for furniture is
``furnished: bool`` (see docs/QDRANT_STACK.md). This test pins the prompt
contract so the LLM is instructed to emit a bool rather than the legacy
``furniture (string)`` "Есть"/"Нет" form.
"""

from telegram_bot.services.query_analyzer import SYSTEM_PROMPT


def test_prompt_mentions_furnished_filter() -> None:
    """SYSTEM_PROMPT must instruct the LLM about the ``furnished`` filter."""
    assert "furnished" in SYSTEM_PROMPT.lower(), (
        "SYSTEM_PROMPT must reference the canonical ``furnished`` field"
    )


def test_prompt_does_not_mention_legacy_furniture_string() -> None:
    """Legacy ``furniture (string)`` spec must be removed (case-insensitive)."""
    assert "furniture (string)" not in SYSTEM_PROMPT.lower(), (
        "SYSTEM_PROMPT still describes the legacy `furniture (string)` filter"
    )


def test_prompt_specifies_bool_type_for_furnished() -> None:
    """``bool`` must appear within 80 characters of ``furnished`` to lock the type spec."""
    lower = SYSTEM_PROMPT.lower()
    idx = lower.find("furnished")
    assert idx != -1, "SYSTEM_PROMPT must mention `furnished`"
    window = lower[idx : idx + 80]
    assert "bool" in window, (
        f"`bool` type spec must appear within 80 chars of `furnished`; window was {window!r}"
    )
