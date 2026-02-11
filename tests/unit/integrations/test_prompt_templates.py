"""Tests for contract-style prompt templates."""

from __future__ import annotations

from telegram_bot.integrations.prompt_templates import (
    CONTRACT_PROMPTS,
    build_system_prompt,
    get_token_limit,
    get_word_limit,
)


class TestTokenLimits:
    """LASER-D inspired token budgets."""

    def test_short_easy_is_most_aggressive(self) -> None:
        assert get_token_limit("short", "easy") == 50

    def test_detailed_hard_is_most_generous(self) -> None:
        assert get_token_limit("detailed", "hard") == 350

    def test_balanced_medium_middle_ground(self) -> None:
        assert get_token_limit("balanced", "medium") == 150

    def test_unknown_combo_returns_default(self) -> None:
        assert get_token_limit("short", "unknown") == 150  # type: ignore[arg-type]

    def test_word_limit_approximation(self) -> None:
        wl = get_word_limit("short", "easy")
        assert 30 <= wl <= 50  # 50 tokens / 1.3 ~ 38


class TestContractPrompts:
    """All three styles have contract prompts."""

    def test_all_styles_exist(self) -> None:
        assert "short" in CONTRACT_PROMPTS
        assert "balanced" in CONTRACT_PROMPTS
        assert "detailed" in CONTRACT_PROMPTS

    def test_short_prompt_has_contract(self) -> None:
        assert "OUTPUT CONTRACT" in CONTRACT_PROMPTS["short"]
        assert "{word_limit}" in CONTRACT_PROMPTS["short"]

    def test_balanced_prompt_has_contract(self) -> None:
        assert "OUTPUT CONTRACT" in CONTRACT_PROMPTS["balanced"]


class TestBuildSystemPrompt:
    """build_system_prompt renders templates correctly."""

    def test_short_prompt_renders_domain(self) -> None:
        prompt = build_system_prompt("short", "easy", "недвижимость")
        assert "недвижимость" in prompt
        assert "OUTPUT CONTRACT" in prompt

    def test_short_prompt_has_word_limit(self) -> None:
        prompt = build_system_prompt("short", "easy", "недвижимость")
        # word_limit for short/easy = 50/1.3 ~ 38
        assert "38" in prompt

    def test_balanced_prompt_renders(self) -> None:
        prompt = build_system_prompt("balanced", "medium", "недвижимость")
        assert "недвижимость" in prompt

    def test_detailed_prompt_renders(self) -> None:
        prompt = build_system_prompt("detailed", "hard", "недвижимость")
        assert "недвижимость" in prompt
