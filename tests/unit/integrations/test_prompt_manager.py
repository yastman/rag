"""Tests for Langfuse Prompt Management integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from telegram_bot.integrations.prompt_manager import (
    DEFAULT_CACHE_TTL,
    _apply_fallback_vars,
    _reset_client,
    get_prompt,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset prompt TTL caches before each test."""
    _reset_client()
    yield
    _reset_client()


class TestGetPrompt:
    def test_returns_fallback_when_langfuse_unavailable(self):
        mock_client = MagicMock()
        mock_client.api = None
        mock_client.get_prompt.side_effect = Exception("Langfuse disabled")

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt("test-prompt", fallback="default prompt text")
        assert result == "default prompt text"

    def test_returns_fallback_with_vars_when_langfuse_unavailable(self):
        mock_client = MagicMock()
        mock_client.api = None
        mock_client.get_prompt.side_effect = Exception("Langfuse disabled")

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt(
                "test-prompt",
                fallback="Hello {{name}}, welcome to {{place}}!",
                variables={"name": "John", "place": "Sofia"},
            )
        assert result == "Hello John, welcome to Sofia!"

    def test_fetches_prompt_from_langfuse(self):
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "Langfuse prompt text"
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt("my-prompt", fallback="fallback text")

        assert result == "Langfuse prompt text"
        mock_client.get_prompt.assert_called_once_with(
            "my-prompt", cache_ttl_seconds=DEFAULT_CACHE_TTL
        )
        mock_prompt.compile.assert_called_once_with()

    def test_compiles_with_variables(self):
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "Ассистент по недвижимость"
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt(
                "generate",
                fallback="Ассистент по {{domain}}",
                variables={"domain": "недвижимость"},
            )

        assert result == "Ассистент по недвижимость"
        mock_prompt.compile.assert_called_once_with(domain="недвижимость")

    def test_custom_cache_ttl(self):
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "cached"
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            get_prompt("test", fallback="fb", cache_ttl=60)

        mock_client.get_prompt.assert_called_once_with("test", cache_ttl_seconds=60)

    def test_falls_back_on_exception(self):
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = Exception("API error")

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt("broken", fallback="safe fallback")

        assert result == "safe fallback"

    def test_falls_back_with_vars_on_exception(self):
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = Exception("API error")

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt("broken", fallback="Hello {{name}}", variables={"name": "World"})

        assert result == "Hello World"

    def test_not_found_error_is_temporarily_cached(self):
        mock_client = MagicMock()
        mock_client.get_prompt.side_effect = Exception(
            "status_code: 404, body: {'message': \"Prompt not found: 'generate'\"}"
        )

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            first = get_prompt("generate", fallback="fallback", cache_ttl=60)
            second = get_prompt("generate", fallback="fallback", cache_ttl=60)

        assert first == "fallback"
        assert second == "fallback"
        # 2nd call should use local missing-cache and skip Langfuse call.
        assert mock_client.get_prompt.call_count == 1

    def test_no_manual_api_probe_for_missing_prompt(self):
        mock_client = MagicMock()
        mock_client.api.prompts.get.side_effect = RuntimeError("must not be called")
        mock_client.get_prompt.side_effect = Exception(
            "status_code: 404, body: {'message': \"Prompt not found: 'generate'\"}"
        )

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt("generate", fallback="fallback", cache_ttl=60)

        assert result == "fallback"
        mock_client.get_prompt.assert_called_once()
        mock_client.api.prompts.get.assert_not_called()

    def test_forwards_langfuse_prompt_label_from_env(self, monkeypatch: pytest.MonkeyPatch):
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "staging prompt"
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt
        monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "staging")

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            result = get_prompt("my-prompt", fallback="fallback text")

        assert result == "staging prompt"
        mock_client.get_prompt.assert_called_once_with(
            "my-prompt",
            cache_ttl_seconds=DEFAULT_CACHE_TTL,
            label="staging",
        )


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


class TestSpanOutputPromptVersion:
    def test_span_output_includes_prompt_version_from_langfuse(self):
        """Span output must include prompt_version when prompt is fetched from Langfuse."""
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "Langfuse prompt text"
        mock_prompt.version = 3
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            get_prompt("my-prompt", fallback="fallback text")

        output_calls = [
            c
            for c in mock_client.update_current_span.call_args_list
            if "output" in (c.kwargs or {})
        ]
        assert len(output_calls) == 1
        assert output_calls[0].kwargs["output"]["prompt_version"] == 3

    def test_span_output_includes_prompt_version_for_compiled_with_variables(self):
        """Span output must include prompt_version when compiling with variables."""
        mock_prompt = MagicMock()
        mock_prompt.compile.return_value = "Compiled with vars"
        mock_prompt.version = 7
        mock_client = MagicMock()
        mock_client.get_prompt.return_value = mock_prompt

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            get_prompt("my-prompt", fallback="fallback", variables={"domain": "real_estate"})

        output_calls = [
            c
            for c in mock_client.update_current_span.call_args_list
            if "output" in (c.kwargs or {})
        ]
        assert len(output_calls) == 1
        assert output_calls[0].kwargs["output"]["prompt_version"] == 7

    def test_span_output_has_no_prompt_version_for_fallback(self):
        """Span output must not include prompt_version when falling back."""
        mock_client = MagicMock()
        mock_client.api = None
        mock_client.get_prompt.side_effect = Exception("Langfuse disabled")

        with patch("telegram_bot.integrations.prompt_manager.get_client", return_value=mock_client):
            get_prompt("test-prompt", fallback="default prompt text")

        output_calls = [
            c
            for c in mock_client.update_current_span.call_args_list
            if "output" in (c.kwargs or {})
        ]
        assert len(output_calls) == 1
        assert "prompt_version" not in output_calls[0].kwargs["output"]


class TestResetClient:
    def test_reset_clears_missing_prompt_cache(self):
        from telegram_bot.integrations.prompt_manager import _missing_prompts_until

        _missing_prompts_until["some-prompt"] = 9999999999.0
        _reset_client()
        assert "some-prompt" not in _missing_prompts_until
