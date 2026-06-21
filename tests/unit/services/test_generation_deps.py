"""Tests for GenerationDeps DI container (#2958)."""

from __future__ import annotations

from telegram_bot.services.generate_response import GenerationDeps


def test_generation_deps_is_importable() -> None:
    deps = GenerationDeps()
    assert deps is not None


def test_generation_deps_accepts_style_prompt_builder() -> None:
    def builder(*_args: object, **_kw: object) -> str:
        return "prompt"

    deps = GenerationDeps(style_prompt_builder=builder)
    assert deps.style_prompt_builder is builder


def test_generation_deps_has_all_expected_fields() -> None:
    """GenerationDeps must expose the 13 injectable fields (all optional with module defaults)."""
    deps = GenerationDeps()
    fields = [
        "max_context_docs",
        "format_context",
        "select_recent_history",
        "build_system_prompt",
        "ensure_history_instruction",
        "build_fallback_response",
        "generate_streaming",
        "style_detector",
        "style_prompt_builder",
        "style_token_limit",
        "extract_queue_ms",
        "extract_sent_message_ref",
        "citation_instruction",
    ]
    for field in fields:
        assert hasattr(deps, field), f"GenerationDeps missing field: {field}"
