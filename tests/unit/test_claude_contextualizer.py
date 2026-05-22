"""Tests for ClaudeContextualizer — verifies system prompt placement."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.contextualization.claude import ClaudeContextualizer


def _make_response(text: str = "Summary") -> MagicMock:
    content_block = MagicMock()
    content_block.text = text
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 20
    response = MagicMock()
    response.content = [content_block]
    response.usage = usage
    return response


@pytest.fixture()
def contextualizer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with (
        patch("src.contextualization.claude.AsyncAnthropic"),
        patch("src.contextualization.claude.Anthropic"),
    ):
        return ClaudeContextualizer(use_cache=True)


@pytest.fixture()
def contextualizer_no_cache(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with (
        patch("src.contextualization.claude.AsyncAnthropic"),
        patch("src.contextualization.claude.Anthropic"),
    ):
        return ClaudeContextualizer(use_cache=False)


@pytest.mark.asyncio
async def test_async_uses_system_param_not_messages(contextualizer):
    """Async method must pass system prompt via system= param, not inside messages."""
    response = _make_response("Test context")
    contextualizer.client.messages.create = AsyncMock(return_value=response)

    await contextualizer.contextualize_single("Some legal text", "art_1")

    call_kwargs = contextualizer.client.messages.create.call_args.kwargs
    assert "system" in call_kwargs, "system= param must be present"
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    # User content should be a plain string, not a list containing the system prompt
    user_content = messages[0]["content"]
    assert isinstance(user_content, str), "user content must be a plain string"
    assert "legal text" in user_content


@pytest.mark.asyncio
async def test_async_system_param_with_cache(contextualizer):
    """With use_cache=True, system= must be a list with cache_control."""
    response = _make_response()
    contextualizer.client.messages.create = AsyncMock(return_value=response)

    await contextualizer.contextualize_single("text", "art_1")

    system = contextualizer.client.messages.create.call_args.kwargs["system"]
    assert isinstance(system, list), "system must be list when caching enabled"
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_async_system_param_without_cache(contextualizer_no_cache):
    """With use_cache=False, system= must be a plain string."""
    response = _make_response()
    contextualizer_no_cache.client.messages.create = AsyncMock(return_value=response)

    await contextualizer_no_cache.contextualize_single("text", "art_1")

    system = contextualizer_no_cache.client.messages.create.call_args.kwargs["system"]
    assert isinstance(system, str), "system must be string when caching disabled"


@pytest.mark.asyncio
async def test_async_returns_contextualized_chunk(contextualizer):
    """Async method must return ContextualizedChunk with correct fields."""
    response = _make_response("Generated summary")
    contextualizer.client.messages.create = AsyncMock(return_value=response)

    result = await contextualizer.contextualize_single("legal clause text", "art_5")

    assert result.original_text == "legal clause text"
    assert result.contextual_summary == "Generated summary"
    assert result.article_number == "art_5"
    assert result.context_method == "claude"
