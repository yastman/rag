"""Tests for contract-style prompt templates."""

from __future__ import annotations

from telegram_bot.integrations.prompt_templates import (
    CONTRACT_PROMPTS,
    build_system_prompt,
    build_system_prompt_with_manager,
    get_token_limit,
    get_word_limit,
)


class TestTokenLimits:
    """LASER-D inspired token budgets."""

    def test_short_easy_is_most_aggressive(self) -> None:
        assert get_token_limit("short", "easy") == 100

    def test_detailed_hard_is_most_generous(self) -> None:
        assert get_token_limit("detailed", "hard") == 350

    def test_balanced_medium_middle_ground(self) -> None:
        assert get_token_limit("balanced", "medium") == 150

    def test_unknown_combo_returns_default(self) -> None:
        assert get_token_limit("short", "unknown") == 150  # type: ignore[arg-type]

    def test_word_limit_approximation(self) -> None:
        wl = get_word_limit("short", "easy")
        assert 70 <= wl <= 90  # 100 tokens / 1.3 ~ 76


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
        # word_limit for short/easy = 100/1.3 ~ 76
        assert "76" in prompt

    def test_balanced_prompt_renders(self) -> None:
        prompt = build_system_prompt("balanced", "medium", "недвижимость")
        assert "недвижимость" in prompt

    def test_detailed_prompt_renders(self) -> None:
        prompt = build_system_prompt("detailed", "hard", "недвижимость")
        assert "недвижимость" in prompt


class TestBuildSystemPromptWithManager:
    """build_system_prompt_with_manager delegates to local build_system_prompt (#2628)."""

    def test_returns_rendered_contract_prompt(self) -> None:
        prompt = build_system_prompt_with_manager("short", "easy", "недвижимость")
        assert "недвижимость" in prompt
        assert "OUTPUT CONTRACT" in prompt

    def test_equivalent_to_build_system_prompt(self) -> None:
        expected = build_system_prompt("short", "easy", "тест")
        result = build_system_prompt_with_manager("short", "easy", "тест")
        assert result == expected

    def test_no_langfuse_routing(self) -> None:
        """No external prompt manager is imported in prompt_templates."""
        import src.runtime.integrations.prompt_templates as pt_module

        assert not hasattr(pt_module, "get_prompt"), (
            "get_prompt should not be imported into prompt_templates after #2628"
        )
        prompt = build_system_prompt_with_manager("balanced", "medium", "недвижимость")
        assert "недвижимость" in prompt
