"""Unit tests for shared generate_response service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.generate_response import generate_response


def _make_non_streaming_config(answer: str = "Ответ модели") -> tuple[MagicMock, MagicMock]:
    """Create mock config and OpenAI-compatible client for non-streaming generation."""
    mock_choice = MagicMock()
    mock_choice.message.content = answer
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-mini"
    mock_response.usage = None

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    mock_config = MagicMock()
    mock_config.domain = "недвижимость"
    mock_config.llm_model = "gpt-4o-mini"
    mock_config.llm_temperature = 0.1
    mock_config.generate_max_tokens = 128
    mock_config.streaming_enabled = False
    mock_config.show_sources = True
    mock_config.response_style_enabled = False
    mock_config.response_style_shadow_mode = False
    mock_config.create_llm.return_value = mock_client
    return mock_config, mock_client


class _StreamChunk:
    def __init__(self, content: str):
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        self.choices = [choice]
        self.model = "gpt-4o-mini"
        self.usage = None


class _AsyncStream:
    def __init__(self, chunks: list[_StreamChunk]):
        self._chunks = chunks
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


@pytest.mark.asyncio
async def test_generate_response_non_streaming_returns_llm_answer() -> None:
    config, client = _make_non_streaming_config(answer="Найдено 3 варианта.")
    lf = MagicMock()

    result = await generate_response(
        query="Что есть в Несебре?",
        documents=[{"text": "Тестовый документ", "score": 0.9, "metadata": {"city": "Несебр"}}],
        config=config,
        lf_client=lf,
        raw_messages=[{"role": "user", "content": "Что есть в Несебре?"}],
    )

    assert result["response"] == "Найдено 3 варианта."
    assert result["llm_call_count"] == 1
    assert "generate" in result["latency_stages"]
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_response_fallback_on_llm_error() -> None:
    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = RuntimeError("provider down")
    lf = MagicMock()

    with patch("telegram_bot.services.generate_response.get_client", return_value=lf):
        result = await generate_response(
            query="Запрос",
            documents=[],
            config=config,
            lf_client=lf,
        )

    assert "временно недоступен" in result["response"]
    assert result["llm_provider_model"] == "fallback"
    assert result["llm_timeout"] is True


@pytest.mark.asyncio
async def test_generate_response_streaming_sets_response_sent_and_message_ref() -> None:
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Часть 1 "), _StreamChunk("Часть 2")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=555)
    sent_msg.message_id = 777
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Стриминг?",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Стриминг?"}],
    )

    assert result["response"] == "Часть 1 Часть 2"
    assert result["response_sent"] is True
    assert result["sent_message"] == {"chat_id": 555, "message_id": 777}
