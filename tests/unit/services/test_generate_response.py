"""Unit tests for shared generate_response service."""

from __future__ import annotations

import asyncio
from typing import Any
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
    def __init__(self, content: str, usage: Any | None = None):
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        self.choices = [choice]
        self.model = "gpt-4o-mini"
        self.usage = usage


class _ReasoningStreamChunk:
    """Mock streaming chunk where content arrives via reasoning fields (Cerebras gpt-oss-120b).

    LiteLLM merge_reasoning_content_in_choices is buggy in streaming mode
    (issues #9578, #15690) — delta.content is None/empty while reasoning tokens
    appear in delta.reasoning_content (LiteLLM standardized) or delta.reasoning
    (raw Cerebras).
    """

    def __init__(
        self,
        *,
        reasoning_content: str | None = None,
        reasoning: str | None = None,
    ):
        delta = MagicMock(spec=[])  # spec=[] prevents auto-attribute creation
        delta.content = None
        delta.reasoning_content = reasoning_content
        delta.reasoning = reasoning
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


@pytest.mark.asyncio
async def test_generate_response_streaming_ttft_includes_pre_stream_wait() -> None:
    """TTFT must include provider wait before stream object is returned."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Часть 1 "), _StreamChunk("Часть 2")])

    async def _delayed_stream_create(*_args, **_kwargs):
        await asyncio.sleep(0.05)  # emulate provider wait before first stream chunk
        return stream

    client.chat.completions.create = AsyncMock(side_effect=_delayed_stream_create)
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
    assert result["llm_ttft_ms"] >= 45.0
    assert result["llm_stream_only_ttft_ms"] is not None
    assert result["llm_stream_only_ttft_ms"] < result["llm_ttft_ms"]
    assert result["llm_ttft_drift_ms"] is not None
    assert result["llm_ttft_drift_ms"] >= 40.0


@pytest.mark.asyncio
async def test_generate_response_non_streaming_has_ttft_ms() -> None:
    """Non-streaming path must report ttft_ms > 0 from LLM call wall time (#571)."""
    config, _client = _make_non_streaming_config(answer="Ответ без стриминга")
    lf = MagicMock()

    result = await generate_response(
        query="Тест таймингов",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
    )

    # ttft_ms must be populated (non-zero) in non-streaming mode
    assert result["llm_ttft_ms"] > 0, "ttft_ms should be > 0 in non-streaming mode"
    # llm_decode_ms is None for non-streaming (no decode/prefill distinction)
    assert result["llm_decode_ms"] is None
    # streaming_enabled must be False
    assert result["streaming_enabled"] is False


@pytest.mark.asyncio
async def test_generate_response_non_streaming_computes_tps_from_usage() -> None:
    """Non-streaming path computes llm_tps when completion_tokens available (#571)."""
    mock_choice = MagicMock()
    mock_choice.message.content = "Ответ с 10 токенами"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-mini"
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 20
    mock_usage.completion_tokens = 10
    mock_usage.total_tokens = 30
    mock_response.usage = mock_usage

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    mock_config = MagicMock()
    mock_config.domain = "недвижимость"
    mock_config.llm_model = "gpt-4o-mini"
    mock_config.llm_temperature = 0.1
    mock_config.generate_max_tokens = 128
    mock_config.streaming_enabled = False
    mock_config.show_sources = False
    mock_config.response_style_enabled = False
    mock_config.response_style_shadow_mode = False
    mock_config.create_llm.return_value = mock_client

    lf = MagicMock()

    result = await generate_response(
        query="Тест TPS",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=mock_config,
        lf_client=lf,
    )

    assert result["llm_ttft_ms"] > 0
    # TPS = completion_tokens / (ttft_ms / 1000)
    assert result["llm_tps"] is not None
    assert result["llm_tps"] > 0
    # decode_ms is None for non-streaming
    assert result["llm_decode_ms"] is None
    lf.update_current_generation.assert_any_call(
        model="gpt-4o-mini",
        usage_details={"input": 20, "output": 10, "total": 30},
    )


@pytest.mark.asyncio
async def test_generate_response_streaming_updates_generation_usage_details() -> None:
    """Streaming path should persist usage_details to Langfuse generation."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    usage = MagicMock()
    usage.prompt_tokens = 11
    usage.completion_tokens = 7
    usage.total_tokens = 18
    stream = _AsyncStream([_StreamChunk("Потоковый ответ", usage=usage)])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=555)
    sent_msg.message_id = 777
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    await generate_response(
        query="Стриминг usage",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Стриминг usage"}],
    )

    lf.update_current_generation.assert_any_call(
        model="gpt-4o-mini",
        usage_details={"input": 11, "output": 7, "total": 18},
    )


@pytest.mark.asyncio
async def test_generate_response_non_streaming_tps_none_when_no_usage() -> None:
    """Non-streaming path sets llm_tps=None when usage is not available (#571)."""
    config, _client = _make_non_streaming_config(answer="Ответ")
    # usage=None set in _make_non_streaming_config already
    lf = MagicMock()

    result = await generate_response(
        query="Тест без usage",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
    )

    # No usage → no TPS, fallback to llm_tps_unavailable score
    assert result["llm_tps"] is None
    assert result["llm_decode_ms"] is None


@pytest.mark.asyncio
async def test_streaming_reasoning_content_merged_into_response() -> None:
    """Streaming with delta.reasoning_content (LiteLLM standardized) produces response.

    Cerebras gpt-oss-120b sends reasoning tokens; LiteLLM standardizes them as
    delta.reasoning_content. When merge_reasoning_content_in_choices is buggy in
    streaming mode, delta.content is None — our client-side merge must catch this.
    """
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    chunks = [
        _ReasoningStreamChunk(reasoning_content="Рассуждение "),
        _ReasoningStreamChunk(reasoning_content="и ответ"),
    ]
    stream = _AsyncStream(chunks)
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=100)
    sent_msg.message_id = 200
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Тест reasoning_content",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест reasoning_content"}],
    )

    assert result["response"] == "Рассуждение и ответ"
    assert result["response_sent"] is True


@pytest.mark.asyncio
async def test_streaming_raw_reasoning_merged_into_response() -> None:
    """Streaming with delta.reasoning (raw Cerebras) produces response.

    Raw Cerebras output uses delta.reasoning (not delta.reasoning_content).
    Our client-side merge must handle this as a second fallback.
    """
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    chunks = [
        _ReasoningStreamChunk(reasoning="Cerebras "),
        _ReasoningStreamChunk(reasoning="рассуждение"),
    ]
    stream = _AsyncStream(chunks)
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=100)
    sent_msg.message_id = 200
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Тест reasoning",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест reasoning"}],
    )

    assert result["response"] == "Cerebras рассуждение"
    assert result["response_sent"] is True


@pytest.mark.asyncio
async def test_streaming_mixed_content_and_reasoning() -> None:
    """Streaming with mixed delta.content and delta.reasoning_content works.

    Real-world scenario: some chunks have delta.content (after LiteLLM merge works),
    others have delta.reasoning_content (when merge fails mid-stream).
    """
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    chunks = [
        _ReasoningStreamChunk(reasoning_content="Думаю... "),
        _StreamChunk("Ответ: "),
        _StreamChunk("Болгария"),
    ]
    stream = _AsyncStream(chunks)
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=100)
    sent_msg.message_id = 200
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Тест mixed",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест mixed"}],
    )

    assert result["response"] == "Думаю... Ответ: Болгария"
    assert result["response_sent"] is True


@pytest.mark.asyncio
async def test_streaming_placeholder_and_llm_called_in_parallel() -> None:
    """Placeholder send and LLM stream creation run in parallel via asyncio.gather."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Параллельный ответ")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=10)
    sent_msg.message_id = 20
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Параллельный тест",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Параллельный тест"}],
    )

    # Both placeholder send and LLM create must have been called
    message.answer.assert_awaited_once()
    client.chat.completions.create.assert_awaited_once()
    assert result["response_sent"] is True


@pytest.mark.asyncio
async def test_generate_response_uses_provided_llm_without_creating_new() -> None:
    """When llm is passed explicitly, config.create_llm must NOT be called."""
    config, _unused_client = _make_non_streaming_config()

    # Build a separate explicit client
    mock_choice = MagicMock()
    mock_choice.message.content = "Синглтон ответ"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o-mini"
    mock_response.usage = None

    explicit_client = MagicMock()
    explicit_client.chat.completions.create = AsyncMock(return_value=mock_response)

    lf = MagicMock()

    result = await generate_response(
        query="Тест синглтона",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        llm=explicit_client,
    )

    # config.create_llm must NOT have been called — singleton was provided
    config.create_llm.assert_not_called()
    explicit_client.chat.completions.create.assert_awaited_once()
    assert result["response"] == "Синглтон ответ"


@pytest.mark.asyncio
async def test_drift_below_threshold_does_not_warn() -> None:
    """Drift below _DRIFT_WARN_THRESHOLD_MS (500ms) must not set WARNING level on span."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    # Stream that produces a small TTFT drift (well below 500ms)
    stream = _AsyncStream([_StreamChunk("Ответ без дрифта")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    # Reset call tracking to check update_current_span calls
    lf.update_current_span.reset_mock()

    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=1)
    sent_msg.message_id = 2
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    await generate_response(
        query="Тест порога дрифта",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест порога дрифта"}],
    )

    # No update_current_span call with level="WARNING" should have occurred
    for call in lf.update_current_span.call_args_list:
        kwargs = call.kwargs or (call.args[0] if call.args else {})
        assert kwargs.get("level") != "WARNING", (
            "Expected no WARNING level for small drift, but got one"
        )


@pytest.mark.asyncio
async def test_streaming_placeholder_failure_closes_precreated_stream() -> None:
    """If placeholder send fails, close pre-created stream before fallback path."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    stream = _AsyncStream([_StreamChunk("Не должен быть отправлен")])
    stream.aclose = AsyncMock()

    fallback_choice = MagicMock()
    fallback_choice.message.content = "Фолбэк после ошибки placeholder"
    fallback_response = MagicMock()
    fallback_response.choices = [fallback_choice]
    fallback_response.model = "gpt-4o-mini"
    fallback_response.usage = None

    client.chat.completions.create = AsyncMock(side_effect=[stream, fallback_response])
    config.create_llm.return_value = client

    lf = MagicMock()
    message = AsyncMock()
    message.answer = AsyncMock(side_effect=RuntimeError("telegram down"))

    result = await generate_response(
        query="Тест ошибки placeholder",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест ошибки placeholder"}],
    )

    assert result["response"] == "Фолбэк после ошибки placeholder"
    assert result["response_sent"] is False
    stream.aclose.assert_awaited_once()
    assert client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_streaming_placeholder_telegram_retry_after_falls_through_to_non_streaming() -> None:
    """TelegramRetryAfter from message.answer falls through to non-streaming fallback.

    Regression guard: without return_exceptions=True in asyncio.gather, the rate-limit
    exception would cancel the LLM stream task and leave sent_msg undefined in cleanup
    (UnboundLocalError). With return_exceptions=True the exception is caught, the stream
    is closed via aclose(), and the outer handler performs non-streaming fallback.
    """
    from aiogram.exceptions import TelegramRetryAfter

    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    stream = _AsyncStream([_StreamChunk("Не должен быть отправлен")])
    stream.aclose = AsyncMock()

    fallback_choice = MagicMock()
    fallback_choice.message.content = "Фолбэк после rate-limit"
    fallback_response = MagicMock()
    fallback_response.choices = [fallback_choice]
    fallback_response.model = "gpt-4o-mini"
    fallback_response.usage = None

    client.chat.completions.create = AsyncMock(side_effect=[stream, fallback_response])
    config.create_llm.return_value = client

    lf = MagicMock()
    message = AsyncMock()
    message.answer = AsyncMock(
        side_effect=TelegramRetryAfter(MagicMock(), "Too many requests: retry after 10", 10)
    )

    result = await generate_response(
        query="Тест rate-limit placeholder",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест rate-limit placeholder"}],
    )

    # Fallback non-streaming path taken; response delivered but not via streaming
    assert result["response"] == "Фолбэк после rate-limit"
    assert result["response_sent"] is False
    # Stream was cleaned up despite placeholder failure (requires return_exceptions=True)
    stream.aclose.assert_awaited_once()
    # LLM called twice: stream object + non-streaming fallback
    assert client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_streaming_create_failure_deletes_placeholder_before_fallback() -> None:
    """If stream creation fails, remove placeholder before non-streaming fallback."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True

    fallback_choice = MagicMock()
    fallback_choice.message.content = "Фолбэк после ошибки stream create"
    fallback_response = MagicMock()
    fallback_response.choices = [fallback_choice]
    fallback_response.model = "gpt-4o-mini"
    fallback_response.usage = None

    client.chat.completions.create = AsyncMock(
        side_effect=[RuntimeError("stream create failed"), fallback_response]
    )
    config.create_llm.return_value = client

    lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.delete = AsyncMock()
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Тест ошибки stream create",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест ошибки stream create"}],
    )

    assert result["response"] == "Фолбэк после ошибки stream create"
    assert result["response_sent"] is False
    sent_msg.delete.assert_awaited_once()
    assert client.chat.completions.create.await_count == 2
