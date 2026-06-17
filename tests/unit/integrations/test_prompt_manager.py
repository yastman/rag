"""Tests for local prompt management (no Langfuse dependency)."""

from __future__ import annotations

from src.runtime.integrations.prompt_manager import (
    _apply_fallback_vars,
    get_prompt,
    get_prompt_with_config,
    get_prompt_with_object,
)


class TestGetPrompt:
    def test_returns_fallback_text(self):
        result = get_prompt("any-name", fallback="default prompt text")
        assert result == "default prompt text"

    def test_applies_variables_to_fallback(self):
        result = get_prompt(
            "test-prompt",
            fallback="Hello {{name}}, welcome to {{place}}!",
            variables={"name": "John", "place": "Sofia"},
        )
        assert result == "Hello John, welcome to Sofia!"

    def test_returns_plain_string(self):
        result = get_prompt("my-prompt", fallback="fallback text")
        assert isinstance(result, str)

    def test_cache_ttl_param_accepted_and_ignored(self):
        result = get_prompt("test", fallback="fb", cache_ttl=60)
        assert result == "fb"

    def test_no_variables_returns_fallback_unchanged(self):
        fallback = "Ты — ассистент по {{domain}}."
        result = get_prompt("generate", fallback=fallback)
        assert result == fallback

    def test_partial_variable_substitution(self):
        result = get_prompt(
            "test",
            fallback="Hello {{name}} from {{missing}}",
            variables={"name": "World"},
        )
        assert result == "Hello World from {{missing}}"


class TestGetPromptWithConfig:
    def test_returns_tuple_of_text_and_empty_dict(self):
        text, config = get_prompt_with_config("generate", fallback="prompt text")
        assert text == "prompt text"
        assert config == {}

    def test_applies_variables(self):
        text, config = get_prompt_with_config(
            "generate",
            fallback="Ты — ассистент по {{domain}}.",
            variables={"domain": "недвижимость"},
        )
        assert text == "Ты — ассистент по недвижимость."
        assert config == {}

    def test_cache_ttl_accepted(self):
        text, config = get_prompt_with_config("test", fallback="fb", cache_ttl=60)
        assert text == "fb"
        assert config == {}


class TestGetPromptWithObject:
    def test_returns_tuple_with_none_object(self):
        text, prompt_obj = get_prompt_with_object("my-prompt", fallback="fallback text")
        assert text == "fallback text"
        assert prompt_obj is None

    def test_applies_variables_and_returns_none_object(self):
        text, prompt_obj = get_prompt_with_object(
            "generate",
            fallback="Ассистент по {{domain}}",
            variables={"domain": "недвижимость"},
        )
        assert text == "Ассистент по недвижимость"
        assert prompt_obj is None

    def test_cache_ttl_accepted(self):
        text, obj = get_prompt_with_object("test", fallback="fb", cache_ttl=60)
        assert text == "fb"
        assert obj is None

    def test_fallback_with_variables_compiled(self):
        text, obj = get_prompt_with_object(
            "generate",
            fallback="Hello {{name}}",
            variables={"name": "World"},
        )
        assert text == "Hello World"
        assert obj is None


class TestApplyFallbackVars:
    def test_no_vars(self):
        assert _apply_fallback_vars("hello", {}) == "hello"

    def test_single_var(self):
        assert _apply_fallback_vars("hi {{name}}", {"name": "Bob"}) == "hi Bob"

    def test_multiple_vars(self):
        result = _apply_fallback_vars("{{a}} and {{b}}", {"a": "X", "b": "Y"})
        assert result == "X and Y"

    def test_missing_var_unchanged(self):
        result = _apply_fallback_vars("{{missing}}", {"other": "val"})
        assert result == "{{missing}}"
