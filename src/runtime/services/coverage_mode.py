"""Coverage-mode detection and result capping for RAG retrieval."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


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


def cap_results_per_doc(
    results: list[dict[str, Any]],
    *,
    max_per_doc: int = 2,
    metadata_key: str = "doc_id",
) -> list[dict[str, Any]]:
    """Cap the number of result chunks returned per source document.

    Args:
        results: Flat list of retrieval result dicts, each optionally containing
            a ``metadata`` sub-dict and/or a top-level ``id`` field.
        max_per_doc: Maximum chunks to keep for any single document key.
        metadata_key: Metadata field used to group chunks by document identity.

    Returns:
        A filtered list preserving original order, with at most ``max_per_doc``
        entries per unique document key.

    """
    counts: dict[str, int] = defaultdict(int)
    capped: list[dict[str, Any]] = []

    for doc in results:
        metadata = doc.get("metadata", {}) or {}
        doc_key = str(metadata.get(metadata_key) or doc.get("id") or "")
        if counts[doc_key] >= max_per_doc:
            continue
        counts[doc_key] += 1
        capped.append(doc)

    return capped
