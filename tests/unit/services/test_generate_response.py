"""Unit tests for shared generate_response service."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import telegram_bot.services as services
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


class _FailingAsyncStream(_AsyncStream):
    def __init__(self, chunks: list[_StreamChunk], error: Exception):
        super().__init__(chunks)
        self._error = error

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise self._error
        return await super().__anext__()


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


def test_services_package_exports_generate_response() -> None:
    assert "generate_response" in services.__all__
    assert services.generate_response is generate_response


@pytest.mark.asyncio
async def test_generate_response_retries_without_name_kwarg_non_streaming() -> None:
    """Fallback for plain OpenAI clients that reject Langfuse `name` kwarg."""
    config, client = _make_non_streaming_config(answer="Ответ plain-openai")
    lf = MagicMock()
    response_obj = client.chat.completions.create.return_value
    client.chat.completions.create = AsyncMock(
        side_effect=[
            TypeError("create() got an unexpected keyword argument 'name'"),
            response_obj,
        ]
    )
    config.create_llm.return_value = client

    result = await generate_response(
        query="Тест plain openai",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        raw_messages=[{"role": "user", "content": "Тест plain openai"}],
    )

    assert result["response"] == "Ответ plain-openai"
    assert client.chat.completions.create.await_count == 2
    first_call = client.chat.completions.create.await_args_list[0].kwargs
    second_call = client.chat.completions.create.await_args_list[1].kwargs
    assert first_call.get("name") == "generate-answer"
    assert "name" not in second_call


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
async def test_generate_response_returns_safe_fallback_when_strict_mode_has_weak_context() -> None:
    config, client = _make_non_streaming_config()
    lf = MagicMock()

    result = await generate_response(
        query="виды внж в болгарии",
        documents=[],
        grounding_mode="strict",
        config=config,
        lf_client=lf,
        raw_messages=[{"role": "user", "content": "виды внж в болгарии"}],
    )

    assert result["safe_fallback_used"] is True
    assert result["grounded"] is False
    assert result["legal_answer_safe"] is False
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_response_strict_mode_does_not_degrade_only_because_show_sources_disabled() -> (
    None
):
    config, client = _make_non_streaming_config(answer="Подтвержденный ответ по документам.")
    config.show_sources = False
    lf = MagicMock()

    result = await generate_response(
        query="Какие документы нужны для ВНЖ?",
        documents=[{"text": "Список документов", "score": 0.91, "metadata": {"title": "ВНЖ"}}],
        grounding_mode="strict",
        config=config,
        lf_client=lf,
        raw_messages=[{"role": "user", "content": "Какие документы нужны для ВНЖ?"}],
    )

    assert result["response"] == "Подтвержденный ответ по документам."
    assert result["safe_fallback_used"] is False
    assert result["grounded"] is True
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_response_streaming_sets_response_sent_and_message_ref() -> None:
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Часть 1 "), _StreamChunk("Часть 2")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=555)
    sent_msg.message_id = 777
    message = AsyncMock()
    message.chat = MagicMock(id=555)
    message.bot = bot
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
async def test_generate_response_retries_without_name_kwarg_streaming() -> None:
    """Streaming path retries without Langfuse `name` for plain OpenAI clients."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Поток "), _StreamChunk("без name")])
    client.chat.completions.create = AsyncMock(
        side_effect=[
            TypeError("create() got an unexpected keyword argument 'name'"),
            stream,
        ]
    )
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=111)
    sent_msg.message_id = 222
    message = AsyncMock()
    message.chat = MagicMock(id=111)
    message.bot = bot
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Стрим plain-openai",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Стрим plain-openai"}],
    )

    assert result["response"] == "Поток без name"
    assert result["response_sent"] is True
    assert client.chat.completions.create.await_count == 2
    first_call = client.chat.completions.create.await_args_list[0].kwargs
    second_call = client.chat.completions.create.await_args_list[1].kwargs
    assert first_call.get("name") == "generate-answer"
    assert "name" not in second_call


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
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=555)
    sent_msg.message_id = 777
    message = AsyncMock()
    message.chat = MagicMock(id=555)
    message.bot = bot
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
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=555)
    sent_msg.message_id = 777
    message = AsyncMock()
    message.chat = MagicMock(id=555)
    message.bot = bot
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
async def test_reasoning_effort_passed_to_llm_create() -> None:
    """reasoning_effort from config is forwarded to chat.completions.create()."""
    config, client = _make_non_streaming_config(answer="Краткий ответ")
    config.get_reasoning_kwargs.return_value = {"reasoning_effort": "low"}
    lf = MagicMock()

    await generate_response(
        query="Тест reasoning",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
    )

    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert call_kwargs["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_disable_reasoning_passed_to_llm_create() -> None:
    """disable_reasoning from config is forwarded to chat.completions.create()."""
    config, client = _make_non_streaming_config(answer="Ответ без reasoning")
    config.get_reasoning_kwargs.return_value = {"disable_reasoning": True}
    lf = MagicMock()

    await generate_response(
        query="Тест disable reasoning",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
    )

    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert call_kwargs["disable_reasoning"] is True


@pytest.mark.asyncio
async def test_no_reasoning_kwargs_when_none() -> None:
    """When all reasoning fields are None, no extra kwargs are passed."""
    config, client = _make_non_streaming_config(answer="Обычный ответ")
    config.get_reasoning_kwargs.return_value = {}
    lf = MagicMock()

    await generate_response(
        query="Без reasoning",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
    )

    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert "reasoning_effort" not in call_kwargs
    assert "disable_reasoning" not in call_kwargs
    assert "reasoning_format" not in call_kwargs


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
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=100)
    sent_msg.message_id = 200
    message = AsyncMock()
    message.chat = MagicMock(id=100)
    message.bot = bot
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
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=100)
    sent_msg.message_id = 200
    message = AsyncMock()
    message.chat = MagicMock(id=100)
    message.bot = bot
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
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=100)
    sent_msg.message_id = 200
    message = AsyncMock()
    message.chat = MagicMock(id=100)
    message.bot = bot
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
async def test_streaming_answer_failure_degrades_gracefully() -> None:
    """When final message.answer fails, stream still completes but response_sent=False.

    LLM stream runs, draft updates are sent via send_message_draft, but if the
    final message.answer() to persist the message fails, the response is still
    generated — downstream sender must deliver it.
    """
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Ответ несмотря на ошибку доставки")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    message = AsyncMock()
    message.chat = MagicMock(id=999)
    message.bot = bot
    message.answer = AsyncMock(side_effect=RuntimeError("telegram send failed"))

    result = await generate_response(
        query="Тест ошибки доставки",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест ошибки доставки"}],
    )

    # Stream ran successfully — no non-streaming recovery needed
    assert result["response"] == "Ответ несмотря на ошибку доставки"
    assert result["llm_stream_recovery"] is False
    # Final message was never delivered, downstream sender must deliver it
    assert result["response_sent"] is False
    # LLM was called exactly once (streaming path, no separate fallback call)
    assert client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_stream_failure_raises_and_triggers_fallback() -> None:
    """LLM stream exception propagates from gather → triggers non-streaming fallback (#683)."""
    config, client = _make_non_streaming_config(answer="Нестриминговый fallback")
    config.streaming_enabled = True
    # First call (stream=True) raises; second call (non-streaming fallback) succeeds
    mock_fallback_response = MagicMock()
    mock_fallback_response.choices = [MagicMock()]
    mock_fallback_response.choices[0].message.content = "Нестриминговый fallback"
    mock_fallback_response.model = "gpt-4o-mini"
    mock_fallback_response.usage = None
    client.chat.completions.create = AsyncMock(
        side_effect=[RuntimeError("LLM сервис недоступен"), mock_fallback_response]
    )
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=1)
    sent_msg.message_id = 2
    message = AsyncMock()
    message.chat = MagicMock(id=1)
    message.bot = bot
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Тест ошибки стрима",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест ошибки стрима"}],
    )

    assert result["response"] == "Нестриминговый fallback"
    assert result["llm_stream_recovery"] is True


@pytest.mark.asyncio
async def test_partial_stream_recovery_edits_existing_message_instead_of_sending_duplicate() -> (
    None
):
    """Partial stream recovery should reuse the persisted message, not send a duplicate."""
    config, client = _make_non_streaming_config(answer="Полный ответ после recovery")
    config.streaming_enabled = True

    partial_stream = _FailingAsyncStream([_StreamChunk("Частичный ответ")], RuntimeError("boom"))
    fallback_response = MagicMock()
    fallback_response.choices = [MagicMock()]
    fallback_response.choices[0].message.content = "Полный ответ после recovery"
    fallback_response.model = "gpt-4o-mini"
    fallback_response.usage = None
    client.chat.completions.create = AsyncMock(side_effect=[partial_stream, fallback_response])
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=10)
    sent_msg.message_id = 20
    message = AsyncMock()
    message.chat = MagicMock(id=10)
    message.bot = bot
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Тест partial recovery",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест partial recovery"}],
    )

    assert result["response"] == "Полный ответ после recovery"
    assert result["llm_stream_recovery"] is True
    assert result["response_sent"] is True
    assert message.answer.await_count == 1
    sent_msg.edit_text.assert_awaited_once_with(
        "Полный ответ после recovery",
        parse_mode="HTML",
    )


@pytest.mark.asyncio
async def test_ttft_drift_warn_ms_config() -> None:
    """TTFT drift warning threshold is read from config.ttft_drift_warn_ms (#675)."""
    from telegram_bot.graph.config import GraphConfig

    # Default value
    gc = GraphConfig()
    assert gc.ttft_drift_warn_ms == 500

    # Reads from env
    gc_env = GraphConfig.from_env()
    assert isinstance(gc_env.ttft_drift_warn_ms, int)

    # Low threshold (0) triggers warning for any drift
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    config.ttft_drift_warn_ms = 0  # any drift triggers warning

    stream = _AsyncStream([_StreamChunk("Ответ")])

    async def _delayed_create(*_args: object, **_kwargs: object) -> _AsyncStream:
        await asyncio.sleep(0.05)
        return stream

    client.chat.completions.create = AsyncMock(side_effect=_delayed_create)
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=1)
    sent_msg.message_id = 2
    message = AsyncMock()
    message.chat = MagicMock(id=1)
    message.bot = bot
    message.answer = AsyncMock(return_value=sent_msg)

    await generate_response(
        query="Тест TTFT drift",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Тест TTFT drift"}],
    )

    warning_calls = [
        c
        for c in lf.update_current_span.call_args_list
        if c.kwargs.get("level") == "WARNING"
        and "TTFT drift" in (c.kwargs.get("status_message") or "")
    ]
    assert len(warning_calls) >= 1


@pytest.mark.asyncio
async def test_streaming_uses_send_message_draft() -> None:
    """Streaming path uses bot.send_message_draft instead of edit_text."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Часть 1 "), _StreamChunk("Часть 2")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    lf = MagicMock()
    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)

    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=555)
    sent_msg.message_id = 777

    message = AsyncMock()
    message.chat = MagicMock(id=555)
    message.bot = bot
    message.answer = AsyncMock(return_value=sent_msg)

    result = await generate_response(
        query="Стриминг draft?",
        documents=[{"text": "Контекст", "score": 0.7, "metadata": {}}],
        config=config,
        lf_client=lf,
        message=message,
        raw_messages=[{"role": "user", "content": "Стриминг draft?"}],
    )

    assert result["response"] == "Часть 1 Часть 2"
    assert result["response_sent"] is True
    assert result["sent_message"] == {"chat_id": 555, "message_id": 777}
    # Должен вызвать send_message_draft, а НЕ edit_text
    bot.send_message_draft.assert_called()
    # Финальный ответ через message.answer (не edit_text)
    message.answer.assert_called_once()
    call_kwargs = message.answer.call_args
    assert "Часть 1 Часть 2" in str(call_kwargs)
