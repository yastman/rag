"""Tests for the canonical runtime grounding policy module."""

from __future__ import annotations


def test_grounding_policy_behavior_is_preserved() -> None:
    """Canonical runtime policy should preserve strict/normal decisions."""
    from src.runtime.grounding.policy import (
        build_safe_fallback_response,
        get_grounding_mode,
        semantic_cache_safe_reuse_allowed,
        should_safe_fallback,
    )

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
