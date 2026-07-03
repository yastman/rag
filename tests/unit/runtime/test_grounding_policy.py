"""Tests for the canonical runtime grounding policy module."""

from __future__ import annotations

import pytest

from src.runtime.grounding.policy import (
    build_safe_fallback_response,
    get_grounding_mode,
    semantic_cache_safe_reuse_allowed,
    should_safe_fallback,
)


def test_grounding_policy_behavior_is_preserved() -> None:
    """Canonical runtime policy should preserve strict/normal decisions."""
    assert get_grounding_mode(query_type="FAQ", topic_hint="legal") == "strict"
    assert get_grounding_mode(query_type="GENERAL", topic_hint=None) == "normal"
    assert should_safe_fallback(
        grounding_mode="strict",
        documents=[{"text": "fact"}],
        sources_enabled=True,
        grade_confidence=0.1,
    )
    assert not semantic_cache_safe_reuse_allowed(
        grounding_mode="strict",
        grounded=True,
        legal_answer_safe=True,
        semantic_cache_safe_reuse=False,
        safe_fallback_used=False,
    )
    assert "Не могу дать надежный ответ" in build_safe_fallback_response([])


# ---------------------------------------------------------------------------
# G-C: Grounding policy router (clean unit tests)
# ---------------------------------------------------------------------------


def test_get_grounding_mode_legal_topic_hint_returns_strict() -> None:
    """G-C: LEGAL topic_hint → strict mode."""
    assert get_grounding_mode(query_type="FAQ", topic_hint="legal") == "strict"


def test_get_grounding_mode_legal_query_type_returns_strict() -> None:
    """G-C: LEGAL query_type → strict mode."""
    assert get_grounding_mode(query_type="LEGAL", topic_hint=None) == "strict"


def test_get_grounding_mode_general_query_returns_normal() -> None:
    """G-C: General query → normal mode."""
    assert get_grounding_mode(query_type="GENERAL", topic_hint=None) == "normal"


def test_get_grounding_mode_faq_no_topic_hint_returns_normal() -> None:
    """G-C: FAQ query type with no risky topic hint → normal mode."""
    assert get_grounding_mode(query_type="FAQ", topic_hint=None) == "normal"


def test_should_safe_fallback_normal_mode_empty_docs_invariant() -> None:
    """G-C INVARIANT: normal mode does NOT trigger safe fallback on empty docs.

    Design intent: safe fallback is only for strict grounding mode.
    This test must NOT be changed to make it pass — it documents intent.
    """
    result = should_safe_fallback(
        grounding_mode="normal",
        documents=[],
        sources_enabled=True,
    )
    assert result is False, (
        "INVARIANT VIOLATION: normal mode must never trigger safe fallback on empty docs"
    )


@pytest.mark.parametrize(
    "grade_confidence,expected_fallback",
    [
        (0.5, False),  # at threshold → grounded (safe)
        (0.49, True),  # below threshold → fallback
    ],
)
def test_should_safe_fallback_threshold(grade_confidence: float, expected_fallback: bool) -> None:
    """G-C: Threshold test — score 0.5 → no fallback, score 0.49 → fallback."""
    result = should_safe_fallback(
        grounding_mode="strict",
        documents=[{"text": "fact", "score": grade_confidence}],
        sources_enabled=True,
        grade_confidence=grade_confidence,
    )
    assert result is expected_fallback
