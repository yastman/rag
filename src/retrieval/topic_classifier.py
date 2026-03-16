"""Lightweight topic/doc-type classification helpers for retrieval."""

from __future__ import annotations

import re
from enum import StrEnum


class TopicLabel(StrEnum):
    FINANCE = "finance"
    LEGAL = "legal"
    PROPERTY = "property"
    RELOCATION = "relocation"
    GENERAL = "general"


class DocType(StrEnum):
    FAQ = "faq"
    TRANSCRIPT = "transcript"
    ARTICLE = "article"
    CHECKLIST = "checklist"
    LEGAL = "legal"


_FINANCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bрассроч\w*",
        r"\bипотек\w*",
        r"\bкредит\w*",
        r"\bплатеж\w*",
        r"\bвзнос\w*",
        r"\bпроцент\w*",
        r"\bдоход\w*",
    )
]
_LEGAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bвнж\b",
        r"вид на жительств",
        r"\bпмж\b",
        r"\bгражданств\w*",
        r"\bнотари\w*",
        r"\bдокумент\w*",
        r"\bлегализац\w*",
    )
]
_PROPERTY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bквартир\w*",
        r"\bапартамент\w*",
        r"\bнедвижимост\w*",
        r"\bкомплекс\w*",
        r"\bобъект\w*",
        r"\bстуди\w*",
    )
]
_RELOCATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bпереезд\w*",
        r"\bинфотур\w*",
        r"\bадаптац\w*",
    )
]


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def classify_chunk_topic(text: str) -> TopicLabel:
    """Classify chunk text into a coarse retrieval topic."""
    if _matches_any(text, _FINANCE_PATTERNS):
        return TopicLabel.FINANCE
    if _matches_any(text, _LEGAL_PATTERNS):
        return TopicLabel.LEGAL
    if _matches_any(text, _PROPERTY_PATTERNS):
        return TopicLabel.PROPERTY
    if _matches_any(text, _RELOCATION_PATTERNS):
        return TopicLabel.RELOCATION
    return TopicLabel.GENERAL


def classify_doc_type(source_path: str, mime_type: str) -> DocType:
    """Infer document type from source path and mime type."""
    source_lower = source_path.lower()
    mime_lower = mime_type.lower()
    if "faq" in source_lower or "services.yaml" in source_lower:
        return DocType.FAQ
    if any(token in source_lower for token in ("checklist", "check-list", "steps")):
        return DocType.CHECKLIST
    if any(token in source_lower for token in ("contract", "agreement", "template")):
        return DocType.LEGAL
    if mime_lower.startswith("audio/") or "transcript" in source_lower:
        return DocType.TRANSCRIPT
    if mime_lower == "application/pdf":
        return DocType.LEGAL
    return DocType.ARTICLE


def get_query_topic_hint(query: str) -> TopicLabel | None:
    """Return a conservative topic hint for short intent-style queries."""
    normalized = query.strip().lower()
    if not normalized:
        return None
    if _matches_any(normalized, _FINANCE_PATTERNS):
        return TopicLabel.FINANCE
    if _matches_any(normalized, _LEGAL_PATTERNS):
        return TopicLabel.LEGAL
    if _matches_any(normalized, _RELOCATION_PATTERNS):
        return TopicLabel.RELOCATION
    return None


def detect_score_gap(
    scores: list[float], gap_ratio_threshold: float = 0.15
) -> dict[str, float | bool]:
    """Evaluate whether the top result is sufficiently separated from the runner-up."""
    if not scores:
        return {
            "confident": False,
            "gap": 0.0,
            "gap_ratio": 0.0,
            "top_score": 0.0,
            "second_score": 0.0,
            "threshold": gap_ratio_threshold,
        }
    top_score = scores[0]
    second_score = scores[1] if len(scores) > 1 else 0.0
    gap = max(top_score - second_score, 0.0)
    gap_ratio = gap / top_score if top_score > 0 else 0.0
    return {
        "confident": len(scores) == 1 or gap_ratio >= gap_ratio_threshold,
        "gap": gap,
        "gap_ratio": gap_ratio,
        "top_score": top_score,
        "second_score": second_score,
        "threshold": gap_ratio_threshold,
    }
