"""Cost tracking + configurable prompt contract tests (issue #1234).

These tests pin the cleanup contract from issue #1234:

1. ``ContextualizeProvider`` exposes a shared ``_calculate_token_cost`` helper
   so each provider does not redo the same ``(in*p_in + out*p_out)/1_000_000``
   formula. Per Context7 the OpenAI SDK only surfaces token counts via
   ``response.usage`` (``prompt_tokens``/``completion_tokens``); pricing is an
   application-level concern, so we own the helper.

2. ``_total_input_tokens_from_anthropic_usage`` adds the prompt-cache fields
   the Anthropic SDK documents on the ``Usage`` object::

       Total input tokens = input_tokens
                          + cache_creation_input_tokens
                          + cache_read_input_tokens

   (Source: ``anthropic-sdk-python/src/anthropic/types/message.py`` Usage
   docstring, fetched via Context7 /anthropics/anthropic-sdk-python.)
   The previous ``ClaudeContextualizer.contextualize_single`` summed only
   ``input_tokens + output_tokens`` and silently undercounted token usage
   (and cost) whenever Anthropic prompt caching kicked in. The helper makes
   the SDK-correct accounting reusable.

3. The system prompt used by every provider is configurable. The legacy
   hard-coded Ukrainian-legal prompt is preserved as the default so existing
   callers keep working, but ``ContextualizeProvider.get_system_prompt(...)``
   now also honours an explicit ``prompt`` argument.

The tests do not require live Anthropic / OpenAI / Groq SDKs — they exercise
the helpers directly with simple objects.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.contextualization.base import ContextualizeProvider


# ---------------------------------------------------------------------------
# 1. Shared cost helper
# ---------------------------------------------------------------------------


def test_calculate_token_cost_helper_exists() -> None:
    """The base provider must expose ``_calculate_token_cost`` so all three
    provider implementations share one cost formula (issue #1234)."""
    assert hasattr(ContextualizeProvider, "_calculate_token_cost"), (
        "ContextualizeProvider._calculate_token_cost must exist (issue #1234)"
    )


def test_calculate_token_cost_uses_per_million_pricing() -> None:
    """The standard SDK pricing convention is USD per 1M tokens."""
    cost = ContextualizeProvider._calculate_token_cost(
        input_tokens=1_000_000,
        output_tokens=0,
        input_price_per_mtok=5.0,
        output_price_per_mtok=15.0,
    )
    assert cost == pytest.approx(5.0), f"1M input tokens at $5/Mtok must equal $5.00; got {cost!r}"

    cost = ContextualizeProvider._calculate_token_cost(
        input_tokens=0,
        output_tokens=1_000_000,
        input_price_per_mtok=5.0,
        output_price_per_mtok=15.0,
    )
    assert cost == pytest.approx(15.0), (
        f"1M output tokens at $15/Mtok must equal $15.00; got {cost!r}"
    )


def test_calculate_token_cost_handles_zero_tokens() -> None:
    """Zero-token request (e.g. empty response) must return $0.00, not crash."""
    cost = ContextualizeProvider._calculate_token_cost(
        input_tokens=0,
        output_tokens=0,
        input_price_per_mtok=5.0,
        output_price_per_mtok=15.0,
    )
    assert cost == 0.0


def test_calculate_token_cost_charges_cache_creation_premium() -> None:
    """Anthropic charges 1.25× input price for cache creation tokens."""
    cost = ContextualizeProvider._calculate_token_cost(
        input_tokens=0,
        output_tokens=0,
        input_price_per_mtok=5.0,
        output_price_per_mtok=15.0,
        cache_creation_tokens=1_000_000,
    )
    # 1M cache_creation tokens × $5/Mtok × 1.25 = $6.25
    assert cost == pytest.approx(6.25), (
        f"1M cache_creation tokens at $5/Mtok with 1.25 multiplier must equal $6.25; got {cost!r}"
    )


def test_calculate_token_cost_discounts_cache_read() -> None:
    """Anthropic charges 0.1× input price for cache read tokens."""
    cost = ContextualizeProvider._calculate_token_cost(
        input_tokens=0,
        output_tokens=0,
        input_price_per_mtok=5.0,
        output_price_per_mtok=15.0,
        cache_read_tokens=1_000_000,
    )
    # 1M cache_read tokens × $5/Mtok × 0.1 = $0.50
    assert cost == pytest.approx(0.5), (
        f"1M cache_read tokens at $5/Mtok with 0.1 multiplier must equal $0.50; got {cost!r}"
    )


def test_calculate_token_cost_combines_all_components() -> None:
    """Combined invocation: regular input + output + cache creation + cache read."""
    cost = ContextualizeProvider._calculate_token_cost(
        input_tokens=1_000,
        output_tokens=500,
        input_price_per_mtok=5.0,
        output_price_per_mtok=15.0,
        cache_creation_tokens=2_000,
        cache_read_tokens=10_000,
    )
    expected = (1_000 * 5 + 500 * 15 + 2_000 * 5 * 1.25 + 10_000 * 5 * 0.1) / 1_000_000
    assert cost == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 2. Anthropic-style total_input_tokens helper
# ---------------------------------------------------------------------------


def test_total_input_tokens_from_anthropic_usage_helper_exists() -> None:
    """Helper must exist so Claude can correctly sum prompt-cache fields."""
    assert hasattr(ContextualizeProvider, "_total_input_tokens_from_anthropic_usage"), (
        "ContextualizeProvider._total_input_tokens_from_anthropic_usage must "
        "exist (issue #1234) so prompt caching is accounted for correctly"
    )


def test_total_input_tokens_includes_cache_creation_and_cache_read() -> None:
    """SDK contract: total = input + cache_creation + cache_read."""
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=200,
        cache_read_input_tokens=300,
    )
    total = ContextualizeProvider._total_input_tokens_from_anthropic_usage(usage)
    assert total == 100 + 200 + 300, (
        "Total input must include cache_creation + cache_read tokens (Anthropic "
        f"SDK contract). Got {total!r}; expected 600."
    )


def test_total_input_tokens_handles_missing_cache_fields() -> None:
    """Older Usage objects (or non-cached responses) may omit cache fields."""
    usage = SimpleNamespace(input_tokens=100, output_tokens=50)
    total = ContextualizeProvider._total_input_tokens_from_anthropic_usage(usage)
    assert total == 100, (
        "When cache fields are absent the helper must fall back to "
        f"input_tokens. Got {total!r}; expected 100."
    )


def test_total_input_tokens_handles_none_cache_fields() -> None:
    """SDK sometimes returns ``None`` for unset cache fields."""
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=None,
        cache_read_input_tokens=None,
    )
    total = ContextualizeProvider._total_input_tokens_from_anthropic_usage(usage)
    assert total == 100


# ---------------------------------------------------------------------------
# 3. Configurable system prompt
# ---------------------------------------------------------------------------


def test_get_system_prompt_returns_default_when_no_argument() -> None:
    """Default behaviour preserves the legacy Ukrainian-legal prompt."""
    prompt = ContextualizeProvider.get_system_prompt()
    assert "Ukrainian law" in prompt, (
        "Default system prompt must remain backward-compatible with existing "
        "callers (Ukrainian legal domain)."
    )


def test_get_system_prompt_accepts_explicit_override() -> None:
    """Issue #1234: callers should be able to pass a custom prompt."""
    custom = "You are an expert in property listings."
    prompt = ContextualizeProvider.get_system_prompt(custom)
    assert prompt == custom, (
        "When an explicit prompt is supplied it must be returned unchanged so "
        f"non-legal domains can reuse the contextualizers. Got {prompt!r}."
    )


def test_get_system_prompt_treats_empty_string_as_no_override() -> None:
    """Whitespace-only / empty overrides fall back to the default to avoid
    silently sending an empty system prompt to the LLM."""
    prompt = ContextualizeProvider.get_system_prompt("")
    assert "Ukrainian law" in prompt, (
        f"Empty override must fall back to the default prompt; got {prompt!r}"
    )

    prompt = ContextualizeProvider.get_system_prompt("   \n\n  ")
    assert "Ukrainian law" in prompt


# ---------------------------------------------------------------------------
# 4. Provider wiring for configurable prompts
# ---------------------------------------------------------------------------


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        anthropic_api_key="anthropic-key",
        openai_api_key="openai-key",
        groq_api_key="groq-key",
        model_name=None,
        temperature=0.2,
    )


async def test_openai_contextualizer_uses_constructor_system_prompt_override() -> None:
    """OpenAI provider must send the configured prompt to the SDK request."""
    from src.contextualization.openai import OpenAIContextualizer

    custom_prompt = "You summarize real-estate listing fragments."
    async_client = MagicMock()
    async_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))],
        )
    )

    with (
        patch("src.contextualization.openai.AsyncOpenAI", return_value=async_client),
        patch("src.contextualization.openai.OpenAI", return_value=MagicMock()),
    ):
        contextualizer = OpenAIContextualizer(settings=_settings(), system_prompt=custom_prompt)
        await contextualizer.contextualize_single("text", "article-1")

    kwargs = async_client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"][0]["content"] == custom_prompt


async def test_claude_contextualizer_uses_constructor_system_prompt_override() -> None:
    """Claude provider must send the configured prompt to the SDK request."""
    from src.contextualization.claude import ClaudeContextualizer

    custom_prompt = "You summarize product support documents."
    async_client = MagicMock()
    async_client.messages.create = AsyncMock(
        return_value=SimpleNamespace(
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            content=[SimpleNamespace(text="summary")],
        )
    )

    with (
        patch("src.contextualization.claude.AsyncAnthropic", return_value=async_client),
        patch("src.contextualization.claude.Anthropic", return_value=MagicMock()),
    ):
        contextualizer = ClaudeContextualizer(
            settings=_settings(),
            use_cache=False,
            system_prompt=custom_prompt,
        )
        await contextualizer.contextualize_single("text", "article-1")

    kwargs = async_client.messages.create.call_args.kwargs
    assert kwargs["system"] == custom_prompt


async def test_groq_contextualizer_uses_constructor_system_prompt_override() -> None:
    """Groq provider must send the configured prompt to the SDK request."""
    from src.contextualization.groq import GroqContextualizer

    custom_prompt = "You summarize engineering runbooks."
    async_client = MagicMock()
    async_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            usage=SimpleNamespace(total_tokens=15),
            choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))],
        )
    )

    with (
        patch("src.contextualization.groq.AsyncGroq", return_value=async_client),
        patch("src.contextualization.groq.Groq", return_value=MagicMock()),
    ):
        contextualizer = GroqContextualizer(settings=_settings(), system_prompt=custom_prompt)
        await contextualizer.contextualize_single("text", "article-1")

    kwargs = async_client.chat.completions.create.call_args.kwargs
    assert kwargs["messages"][0]["content"] == custom_prompt
