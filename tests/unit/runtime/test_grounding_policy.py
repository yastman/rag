"""Tests for the canonical runtime grounding policy module."""

from __future__ import annotations


def test_telegram_grounding_policy_is_compatibility_shim() -> None:
    """Old Telegram file should re-export the canonical runtime functions.

    Load the shim file directly so this lightweight test does not import the
    heavy ``telegram_bot.services`` package initializer.
    """
    import importlib.util
    from pathlib import Path

    from src.runtime.grounding import policy as canonical

    shim_path = Path("telegram_bot/services/grounding_policy.py")
    spec = importlib.util.spec_from_file_location("_grounding_policy_shim", shim_path)
    assert spec is not None
    assert spec.loader is not None
    shim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shim)

    assert shim.get_grounding_mode is canonical.get_grounding_mode
    assert shim.is_high_risk_grounding_request is canonical.is_high_risk_grounding_request
    assert shim.is_strict_grounding_safe is canonical.is_strict_grounding_safe
    assert shim.semantic_cache_safe_reuse_allowed is canonical.semantic_cache_safe_reuse_allowed
    assert shim.should_safe_fallback is canonical.should_safe_fallback
    assert shim.build_safe_fallback_response is canonical.build_safe_fallback_response


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
