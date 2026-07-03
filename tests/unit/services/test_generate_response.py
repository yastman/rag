"""Unit tests for shared generate_response service."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import telegram_bot.services as services
from telegram_bot.services.generation.generate_response import GenerationDeps, generate_response


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
    MagicMock()

    result = await generate_response(
        query="Что есть в Несебре?",
        documents=[{"text": "Тестовый документ", "score": 0.9, "metadata": {"city": "Несебр"}}],
        config=config,
        raw_messages=[{"role": "user", "content": "Что есть в Несебре?"}],
    )

    assert result["response"] == "Найдено 3 варианта."
    assert result["llm_call_count"] == 1
    assert "generate" in result["latency_stages"]
    client.chat.completions.create.assert_awaited_once()


def test_services_package_exports_generate_response() -> None:
    assert "generate_response" in services.__all__
    exported = services.generate_response
    assert exported is generate_response


@pytest.mark.asyncio
async def test_generate_response_retries_without_name_kwarg_non_streaming() -> None:
    """Fallback for plain OpenAI clients that reject Langfuse `name` kwarg."""
    config, client = _make_non_streaming_config(answer="Ответ plain-openai")
    MagicMock()
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
    result = await generate_response(
        query="Запрос",
        documents=[],
        config=config,
    )

    assert "временно недоступен" in result["response"]
    assert result["fallback_used"] is True
    assert result["safe_fallback_used"] is False
    assert result["llm_provider_model"] == "fallback"
    assert result["llm_timeout"] is True


@pytest.mark.asyncio
async def test_generate_response_returns_safe_fallback_when_strict_mode_has_weak_context() -> None:
    config, client = _make_non_streaming_config()
    MagicMock()

    result = await generate_response(
        query="виды внж в болгарии",
        documents=[],
        grounding_mode="strict",
        config=config,
        raw_messages=[{"role": "user", "content": "виды внж в болгарии"}],
    )

    assert result["fallback_used"] is False
    assert result["safe_fallback_used"] is True
    assert result["llm_provider_model"] == "safe_fallback"
    assert result["llm_timeout"] is False
    assert result["grounded"] is False
    assert result["legal_answer_safe"] is False
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_response_returns_safe_fallback_when_strict_mode_has_low_confidence() -> (
    None
):
    config, client = _make_non_streaming_config()
    MagicMock()

    result = await generate_response(
        query="виды внж в болгарии",
        documents=[{"text": "Документ", "score": 0.2, "metadata": {"title": "ВНЖ"}}],
        grounding_mode="strict",
        grade_confidence=0.1,
        config=config,
        raw_messages=[{"role": "user", "content": "виды внж в болгарии"}],
    )

    assert result["safe_fallback_used"] is True
    assert result["legal_answer_safe"] is False
    assert result["semantic_cache_safe_reuse"] is False
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_response_routes_coverage_query_to_exhaustive_prompt() -> None:
    from unittest.mock import ANY

    config, _client = _make_non_streaming_config(answer="Полный список оснований.")
    MagicMock()

    with patch(
        "telegram_bot.services.generation.generate_response.get_prompt_with_config",
        side_effect=[
            ("EXHAUSTIVE PROMPT", {"temperature": 0.2, "max_tokens": 512}),
        ],
    ) as mock_get_prompt:
        result = await generate_response(
            query="какие еще есть виды внж в болгарии? напиши полный список",
            documents=[{"text": "Контекст", "score": 0.9, "metadata": {"doc_id": "a"}}],
            config=config,
            raw_messages=[{"role": "user", "content": "какие еще есть виды внж"}],
        )

    assert result["needs_coverage"] is True
    assert result["response"] == "Полный список оснований."
    mock_get_prompt.assert_called_once_with(
        "generate_exhaustive_list",
        fallback=ANY,
        variables={"domain": "недвижимость"},
    )


@pytest.mark.asyncio
async def test_generate_response_coverage_mode_bypasses_style_prompt_builder() -> None:
    config, _client = _make_non_streaming_config(answer="Развернутый список.")
    config.response_style_enabled = True
    MagicMock()
    style_prompt_builder = MagicMock(side_effect=AssertionError("style builder must be skipped"))

    result = await generate_response(
        query="перечисли все виды внж",
        documents=[{"text": "Контекст", "score": 0.9, "metadata": {"doc_id": "a"}}],
        config=config,
        deps=GenerationDeps(style_prompt_builder=style_prompt_builder),
        raw_messages=[{"role": "user", "content": "перечисли все виды внж"}],
    )

    assert result["needs_coverage"] is True
    style_prompt_builder.assert_not_called()


@pytest.mark.asyncio
async def test_generate_response_honors_explicit_coverage_override() -> None:
    from unittest.mock import ANY

    config, _client = _make_non_streaming_config(answer="Полный список оснований.")
    MagicMock()

    with patch(
        "telegram_bot.services.generation.generate_response.get_prompt_with_config",
        return_value=("EXHAUSTIVE PROMPT", {"temperature": 0.2, "max_tokens": 512}),
    ) as mock_get_prompt:
        result = await generate_response(
            query="основания для внж в болгарии",
            documents=[{"text": "Контекст", "score": 0.9, "metadata": {"doc_id": "a"}}],
            config=config,
            raw_messages=[{"role": "user", "content": "основания для внж в болгарии"}],
            needs_coverage=True,
        )

    assert result["needs_coverage"] is True
    mock_get_prompt.assert_called_once_with(
        "generate_exhaustive_list",
        fallback=ANY,
        variables={"domain": "недвижимость"},
    )


@pytest.mark.asyncio
async def test_generate_response_coverage_mode_includes_all_retrieved_docs_in_prompt() -> None:
    config, client = _make_non_streaming_config(answer="Полный список.")
    MagicMock()
    docs = [
        {"text": f"Doc {i}", "score": 0.95 - i * 0.01, "metadata": {"doc_id": str(i)}}
        for i in range(8)
    ]

    with patch(
        "telegram_bot.services.generation.generate_response.get_prompt_with_config",
        return_value=("EXHAUSTIVE PROMPT", {"temperature": 0.2, "max_tokens": 512}),
    ):
        result = await generate_response(
            query="перечисли все основания для внж",
            documents=docs,
            config=config,
            raw_messages=[{"role": "user", "content": "перечисли все основания для внж"}],
        )

    assert result["needs_coverage"] is True
    user_prompt = client.chat.completions.create.await_args.kwargs["messages"][-1]["content"]
    assert user_prompt.count("[Объект ") == 8
    assert "Doc 7" in user_prompt


@pytest.mark.asyncio
async def test_generate_response_strict_mode_does_not_degrade_only_because_show_sources_disabled() -> (
    None
):
    config, client = _make_non_streaming_config(answer="Подтвержденный ответ по документам.")
    config.show_sources = False
    MagicMock()

    result = await generate_response(
        query="Какие документы нужны для ВНЖ?",
        documents=[{"text": "Список документов", "score": 0.91, "metadata": {"title": "ВНЖ"}}],
        grounding_mode="strict",
        config=config,
        raw_messages=[{"role": "user", "content": "Какие документы нужны для ВНЖ?"}],
    )

    assert result["response"] == "Подтвержденный ответ по документам."
    assert result["safe_fallback_used"] is False
    assert result["grounded"] is True
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_response_strips_citation_artifacts_when_sources_disabled() -> None:
    config, client = _make_non_streaming_config(
        answer="Потребуется также счёт в болгарском банке 1.\nИ подтверждение дохода [2]."
    )
    config.show_sources = False
    MagicMock()

    result = await generate_response(
        query="Что нужно для ВНЖ?",
        documents=[{"text": "Документ", "score": 0.91, "metadata": {"title": "ВНЖ"}}],
        config=config,
        raw_messages=[{"role": "user", "content": "Что нужно для ВНЖ?"}],
    )

    assert result["response"] == (
        "Потребуется также счёт в болгарском банке\nИ подтверждение дохода."
    )
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_response_keeps_citations_when_sources_enabled() -> None:
    config, client = _make_non_streaming_config(
        answer="Потребуется также счёт в болгарском банке [1]."
    )
    config.show_sources = True
    MagicMock()

    result = await generate_response(
        query="Что нужно для ВНЖ?",
        documents=[{"text": "Документ", "score": 0.91, "metadata": {"title": "ВНЖ"}}],
        config=config,
        raw_messages=[{"role": "user", "content": "Что нужно для ВНЖ?"}],
    )

    assert result["response"] == "Потребуется также счёт в болгарском банке [1]."
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_response_formats_context_without_sources_when_sources_disabled() -> None:
    config, client = _make_non_streaming_config(answer="Ответ.")
    config.show_sources = False
    MagicMock()

    await generate_response(
        query="Что нужно для ВНЖ?",
        documents=[{"text": "Описание ВНЖ", "score": 0.91, "metadata": {"title": "ВНЖ"}}],
        config=config,
        raw_messages=[{"role": "user", "content": "Что нужно для ВНЖ?"}],
    )

    client.chat.completions.create.assert_awaited_once()
    called_messages = client.chat.completions.create.await_args.kwargs["messages"]

    context_found = False
    for msg in called_messages:
        content = msg.get("content", "")
        if "Описание ВНЖ" in content:
            assert "Фрагмент контекста" in content
            assert "[Объект 1]" not in content
            context_found = True
            break

    assert context_found, "Expected to find the retrieved context in the LLM messages"


@pytest.mark.asyncio
async def test_generate_response_streaming_sets_response_sent_and_message_ref() -> None:
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Часть 1 "), _StreamChunk("Часть 2")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    MagicMock()
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
        message=message,
        raw_messages=[{"role": "user", "content": "Стриминг?"}],
    )

    assert result["response"] == "Часть 1 Часть 2"
    assert result["response_sent"] is True
    assert result["sent_message"] == {"chat_id": 555, "message_id": 777}


@pytest.mark.asyncio
async def test_generate_response_streaming_does_not_record_output_when_delivery_fails() -> None:
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Ответ без доставки")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    MagicMock()
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
        message=message,
        raw_messages=[{"role": "user", "content": "Тест ошибки доставки"}],
    )

    assert result["response_sent"] is False


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

    MagicMock()
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

    MagicMock()
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
    MagicMock()

    result = await generate_response(
        query="Тест таймингов",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
    )

    # ttft_ms must be populated (non-zero) in non-streaming mode
    assert result["llm_ttft_ms"] > 0, "ttft_ms should be > 0 in non-streaming mode"
    # llm_decode_ms is None for non-streaming (no decode/prefill distinction)
    assert result["llm_decode_ms"] is None
    # streaming_enabled must be False
    assert result["streaming_enabled"] is False


@pytest.mark.asyncio
async def test_generate_response_non_streaming_tps_none_when_no_usage() -> None:
    """Non-streaming path sets llm_tps=None when usage is not available (#571)."""
    config, _client = _make_non_streaming_config(answer="Ответ")
    # usage=None set in _make_non_streaming_config already
    MagicMock()

    result = await generate_response(
        query="Тест без usage",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
    )

    # No usage → no TPS, fallback to llm_tps_unavailable score
    assert result["llm_tps"] is None
    assert result["llm_decode_ms"] is None


@pytest.mark.asyncio
async def test_reasoning_effort_passed_to_llm_create() -> None:
    """reasoning_effort from config is forwarded to chat.completions.create()."""
    config, client = _make_non_streaming_config(answer="Краткий ответ")
    config.get_reasoning_kwargs.return_value = {"reasoning_effort": "low"}
    MagicMock()

    await generate_response(
        query="Тест reasoning",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
    )

    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert call_kwargs["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_disable_reasoning_passed_to_llm_create() -> None:
    """disable_reasoning is passed through SDK-supported extra_body."""
    config, client = _make_non_streaming_config(answer="Ответ без reasoning")
    config.get_reasoning_kwargs.return_value = {"extra_body": {"disable_reasoning": True}}
    MagicMock()

    await generate_response(
        query="Тест disable reasoning",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
    )

    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert call_kwargs["extra_body"] == {"disable_reasoning": True}
    assert "disable_reasoning" not in call_kwargs


@pytest.mark.asyncio
async def test_no_reasoning_kwargs_when_none() -> None:
    """When all reasoning fields are None, no extra kwargs are passed."""
    config, client = _make_non_streaming_config(answer="Обычный ответ")
    config.get_reasoning_kwargs.return_value = {}
    MagicMock()

    await generate_response(
        query="Без reasoning",
        documents=[{"text": "Контекст", "score": 0.8, "metadata": {}}],
        config=config,
    )

    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert "reasoning_effort" not in call_kwargs
    assert "disable_reasoning" not in call_kwargs
    assert "reasoning_format" not in call_kwargs
    assert "extra_body" not in call_kwargs


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

    MagicMock()
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

    MagicMock()
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

    MagicMock()
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

    MagicMock()
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

    MagicMock()
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

    MagicMock()
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
async def test_streaming_uses_send_message_draft() -> None:
    """Streaming path uses bot.send_message_draft instead of edit_text."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    stream = _AsyncStream([_StreamChunk("Часть 1 "), _StreamChunk("Часть 2")])
    client.chat.completions.create = AsyncMock(return_value=stream)
    config.create_llm.return_value = client

    MagicMock()
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


# ---------------------------------------------------------------------------
# prompt object linking — kwargs must not leak stale provider kwargs
# ---------------------------------------------------------------------------


class _FakePrompt:
    """Stand-in for a managed Prompt object."""

    def __init__(self, text: str = "Compiled system prompt", version: int = 7):
        self.compiled_text = text
        self.version = version
        self.config: dict[str, Any] = {}

    def compile(self, **_kwargs: Any) -> str:
        return self.compiled_text


@pytest.mark.asyncio
async def test_generate_response_does_not_forward_prompt_object_when_none() -> None:
    """No stale kwargs must be sent when prompt fell back to a hardcoded string (#1666)."""
    config, client = _make_non_streaming_config(answer="Ответ")
    MagicMock()

    with patch(
        "telegram_bot.services.generation.generate_response.get_prompt_with_object",
        return_value=("Hardcoded fallback prompt", None),
    ):
        await generate_response(
            query="Тест",
            documents=[{"text": "Doc", "score": 0.8, "metadata": {}}],
            config=config,
            raw_messages=[{"role": "user", "content": "Тест"}],
        )

    client.chat.completions.create.assert_awaited_once()
    call_kwargs = client.chat.completions.create.await_args.kwargs
    assert "langfuse_prompt" not in call_kwargs


@pytest.mark.asyncio
async def test_generate_response_works_when_prompt_object_unavailable() -> None:
    """Prompt linking must degrade gracefully when prompt object is unavailable."""
    config, client = _make_non_streaming_config(answer="Ответ без tracing")

    with patch(
        "telegram_bot.services.generation.generate_response.get_prompt_with_object",
        return_value=("Hardcoded fallback", None),
    ):
        result = await generate_response(
            query="Тест",
            documents=[{"text": "Doc", "score": 0.8, "metadata": {}}],
            config=config,
            raw_messages=[{"role": "user", "content": "Тест"}],
        )

    assert result["response"] == "Ответ без tracing"
    client.chat.completions.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# #1408 — reduce noisy tracebacks for LLM connection failures
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error_uses_logger_warning_not_exception() -> None:
    """httpx.ConnectError must log via logger.warning() without a full traceback."""
    from httpx import ConnectError

    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = ConnectError("connection refused")

    with patch("telegram_bot.services.generation.generate_response.logger") as mock_logger:
        result = await generate_response(
            query="Запрос",
            documents=[],
            config=config,
        )

    assert "временно недоступен" in result["response"]
    assert result["fallback_used"] is True
    assert result["llm_provider_model"] == "fallback"

    mock_logger.exception.assert_not_called()
    mock_logger.warning.assert_called()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "LLM connection" in warning_msg or "connection" in warning_msg.lower()


@pytest.mark.asyncio
async def test_openai_connection_error_uses_logger_warning_not_exception() -> None:
    """openai.APIConnectionError must log via logger.warning() without a full traceback."""
    from openai import APIConnectionError

    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = APIConnectionError(
        message="connection error", request=MagicMock()
    )

    with patch("telegram_bot.services.generation.generate_response.logger") as mock_logger:
        result = await generate_response(
            query="Запрос",
            documents=[],
            config=config,
        )

    assert "временно недоступен" in result["response"]
    assert result["fallback_used"] is True
    assert result["llm_provider_model"] == "fallback"

    mock_logger.exception.assert_not_called()
    mock_logger.warning.assert_called()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert "LLM connection" in warning_msg or "connection" in warning_msg.lower()


@pytest.mark.asyncio
async def test_unexpected_error_still_uses_logger_exception() -> None:
    """Non-connection exceptions (e.g. RuntimeError) must still log via logger.exception()."""
    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = RuntimeError("unexpected failure")

    with patch("telegram_bot.services.generation.generate_response.logger") as mock_logger:
        result = await generate_response(
            query="Запрос",
            documents=[],
            config=config,
        )

    assert "временно недоступен" in result["response"]
    assert result["fallback_used"] is True
    assert result["llm_provider_model"] == "fallback"

    mock_logger.exception.assert_called()
    exception_msg = mock_logger.exception.call_args[0][0]
    assert "LLM call failed" in exception_msg


@pytest.mark.asyncio
async def test_fallback_behavior_preserved_for_connection_error() -> None:
    """Fallback response must still be generated when connection error occurs."""
    from httpx import ConnectError

    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = ConnectError("connection refused")
    result = await generate_response(
        query="Запрос",
        documents=[],
        config=config,
    )

    assert result["response"] == (
        "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."
    )
    assert result["fallback_used"] is True
    assert result["safe_fallback_used"] is False
    assert result["llm_provider_model"] == "fallback"
    assert result["llm_timeout"] is True


@pytest.mark.asyncio
async def test_fallback_with_documents_preserved_for_connection_error() -> None:
    """Fallback with documents must still work when connection error occurs."""
    from httpx import ConnectError

    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = ConnectError("connection refused")
    result = await generate_response(
        query="Запрос",
        documents=[{"text": "Док", "score": 0.9, "metadata": {"title": "Тест"}}],
        config=config,
    )

    assert result["fallback_used"] is True
    assert "Тест" in result["response"]
    assert "Найденные результаты" in result["response"]


@pytest.mark.asyncio
async def test_connection_error_fallback_preserves_usage_and_timing_structure() -> None:
    """Result dict structure (latency_stages, llm_call_count, etc.) preserved on connection error."""
    from httpx import ConnectError

    config, _ = _make_non_streaming_config()
    config.create_llm.side_effect = ConnectError("connection refused")
    result = await generate_response(
        query="Запрос",
        documents=[],
        config=config,
        llm_call_count=3,
        latency_stages={"retrieve": 0.5},
    )

    assert result["fallback_used"] is True
    assert result["llm_call_count"] == 4  # input count (3) + 1
    assert "generate" in result["latency_stages"]
    assert "retrieve" in result["latency_stages"]
    assert result["response_sent"] is False
    assert result["sent_message"] is None
    assert result["llm_ttft_ms"] == 0.0
    assert result["grounding_mode"] == "normal"


@pytest.mark.asyncio
async def test_streaming_connection_error_logs_concise_warning() -> None:
    """Streaming path connection error must log via logger.warning() without full traceback."""
    from httpx import ConnectError

    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    client.chat.completions.create = AsyncMock(side_effect=ConnectError("connection refused"))
    config.create_llm.return_value = client

    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    message = AsyncMock()
    message.chat = MagicMock(id=1)
    message.bot = bot
    message.answer = AsyncMock(return_value=None)

    with patch("telegram_bot.services.generation._stream_execution.logger") as mock_logger:
        result = await generate_response(
            query="Запрос",
            documents=[],
            config=config,
            message=message,
            raw_messages=[{"role": "user", "content": "Запрос"}],
        )

    assert result["fallback_used"] is True
    assert result["llm_provider_model"] == "fallback"

    mock_logger.exception.assert_not_called()
    mock_logger.warning.assert_called()


@pytest.mark.asyncio
async def test_streaming_non_connection_error_still_uses_exception() -> None:
    """Streaming path unexpected error must still log via logger.exception() with full traceback."""
    config, client = _make_non_streaming_config()
    config.streaming_enabled = True
    client.chat.completions.create = AsyncMock(side_effect=ValueError("invalid model"))
    config.create_llm.return_value = client

    bot = AsyncMock()
    bot.send_message_draft = AsyncMock(return_value=True)
    message = AsyncMock()
    message.chat = MagicMock(id=1)
    message.bot = bot
    message.answer = AsyncMock(return_value=None)

    with patch("telegram_bot.services.generation._stream_execution.logger") as mock_logger:
        result = await generate_response(
            query="Запрос",
            documents=[],
            config=config,
            message=message,
            raw_messages=[{"role": "user", "content": "Запрос"}],
        )

    assert result["fallback_used"] is True

    mock_logger.exception.assert_called()
    exception_msg = mock_logger.exception.call_args[0][0]
    assert "LLM call failed" in exception_msg


# ---------------------------------------------------------------------------
# G-A (P0) — Grounded answer carries citation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grounded_answer_carries_citation() -> None:
    """G-A: LLM call succeeds with docs → grounded=True, citation in response, llm_call_count=1."""
    doc_title = "Апартамент у моря"
    config, client = _make_non_streaming_config(
        answer=f"Квартира стоит 80 000€. Источник: {doc_title} [1]."
    )

    result = await generate_response(
        query="Сколько стоит квартира?",
        documents=[{"text": "Цена 80 000€", "score": 0.9, "metadata": {"title": doc_title}}],
        grounding_mode="normal",
        config=config,
        raw_messages=[{"role": "user", "content": "Сколько стоит квартира?"}],
    )

    assert result["grounded"] is True
    assert result["safe_fallback_used"] is False
    assert result["llm_call_count"] == 1
    # Citation from the mocked document must appear in the response
    assert doc_title in result["response"]
    client.chat.completions.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# G-B (P0) — Strict mode + empty docs → safe fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strict_empty_safe_fallback_gate() -> None:
    """G-B: strict mode + empty docs → safe fallback at the runtime generate_answer layer.

    Tests generate_answer directly (the runtime layer).
    generate_answer uses _build_fallback_response from src.runtime.generation.policy
    (not build_safe_fallback_response from src.runtime.grounding.policy) — they are
    different functions. This test asserts the actual runtime behaviour:
    safe_fallback_used=True, llm_provider_model == "safe_fallback", LLM not called.
    """
    from src.runtime.generation.contracts import GenerationRequest
    from src.runtime.generation.policy import _build_fallback_response as runtime_fallback_builder
    from src.runtime.generation.service import generate_answer
    from src.runtime.services.coverage_mode import CoverageDecision
    from src.runtime.services.response_style_detector import StyleInfo

    llm_mock = MagicMock()
    llm_mock.chat.completions.create = AsyncMock()  # must NOT be called

    cfg = MagicMock()
    cfg.show_sources = True
    cfg.response_style_enabled = False
    cfg.response_style_shadow_mode = False
    cfg.generate_max_tokens = 512
    cfg.domain = "real-estate"
    cfg.llm_temperature = 0.2
    cfg.llm_model = "gpt-test"
    cfg.get_reasoning_kwargs.return_value = {}
    cfg.create_llm.return_value = llm_mock

    fake_style = StyleInfo(style="balanced", difficulty="medium", reasoning="test", word_count=3)
    detector = MagicMock()
    detector.detect.return_value = fake_style

    dyn: dict = {
        "ResponseStyleDetector": lambda: detector,
        "detect_coverage_mode": lambda _q: CoverageDecision(False, None),
        "get_prompt_with_config": lambda name, **_kw: (f"sys:{name}", {"max_tokens": 200}),
        "get_prompt_with_object": lambda _n, **_kw: (None, None),
        "build_system_prompt_with_manager": lambda **_kw: "style_sys",
        "get_token_limit": lambda _s, _d: 400,
        "PipelineMetrics": MagicMock(get=MagicMock(return_value=MagicMock(record=MagicMock()))),
    }

    request = GenerationRequest(
        query="Каков правовой статус объекта?",
        documents=[],
        grounding_mode="strict",
        llm_call_count=0,
        config=cfg,
        extra_kwargs=dyn,
    )

    result = await generate_answer(request)

    assert result.payload["safe_fallback_used"] is True
    assert result.payload["llm_provider_model"] == "safe_fallback"
    # Runtime uses _build_fallback_response (not the grounding policy one)
    assert result.payload["response"] == runtime_fallback_builder([])
    llm_mock.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# G-D (P1) — Anti-hallucination: prompt contains only grounded facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_contains_document_content_not_hallucinated_text() -> None:
    """G-D: LLM prompt must contain doc text from retrieved docs and a grounding instruction."""
    doc_text = "Рассрочка 0% доступна для объекта в Несебре"
    config, client = _make_non_streaming_config(answer="Рассрочка доступна.")

    await generate_response(
        query="Есть ли рассрочка?",
        documents=[{"text": doc_text, "score": 0.88, "metadata": {"title": "Объект Несебр"}}],
        grounding_mode="normal",
        config=config,
        raw_messages=[{"role": "user", "content": "Есть ли рассрочка?"}],
    )

    client.chat.completions.create.assert_awaited_once()
    messages = client.chat.completions.create.await_args.kwargs["messages"]

    # The user message must contain the actual document text (not hallucinated)
    user_msg = next(m for m in messages if m["role"] == "user")
    assert doc_text in user_msg["content"], (
        f"Document text '{doc_text}' not found in LLM prompt — anti-hallucination violated"
    )

    # The prompt must include a grounding instruction
    full_prompt = " ".join(m["content"] for m in messages)
    assert "на основе контекста" in full_prompt.lower(), (
        "Grounding instruction ('на основе контекста') missing from LLM prompt"
    )
