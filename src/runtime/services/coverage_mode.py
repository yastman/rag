"""Coverage-mode detection for RAG retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CoverageDecision:
    """Result of coverage-mode detection for a user query.

    Attributes:
        needs_coverage: True when the query requests an exhaustive listing.
        reason: Human-readable label for the matched pattern, or None.

    """

    needs_coverage: bool
    reason: str | None = None


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("какие виды", re.compile(r"\bкакие\s+виды\b", re.IGNORECASE)),
    ("какие варианты", re.compile(r"\bкакие\s+варианты\b", re.IGNORECASE)),
    ("какие еще есть", re.compile(r"\bкакие\s+еще\s+есть\b", re.IGNORECASE)),
    ("полный список", re.compile(r"\bполный\s+список\b", re.IGNORECASE)),
    ("перечисли все", re.compile(r"\bперечисли\s+все\b", re.IGNORECASE)),
    ("все основания", re.compile(r"\bвсе\s+основан", re.IGNORECASE)),
    ("все способы", re.compile(r"\bвсе\s+способы\b", re.IGNORECASE)),
)


def detect_coverage_mode(query: str) -> CoverageDecision:
    """Return a CoverageDecision indicating whether the query needs exhaustive coverage.

    Args:
        query: Raw user query text.

    Returns:
        A CoverageDecision with ``needs_coverage=True`` and the matched pattern
        label when the query contains a Russian enumeration phrase, otherwise
        ``needs_coverage=False``.

    """
    text = (query or "").strip()
    if not text:
        return CoverageDecision(False, None)

    for label, pattern in _PATTERNS:
        if pattern.search(text):
            return CoverageDecision(True, f"regex:{label}")

    return CoverageDecision(False, None)
