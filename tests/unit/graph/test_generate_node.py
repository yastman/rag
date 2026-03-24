"""Tests for generate_node — LLM answer generation with conversation history."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.graph.state import make_initial_state


def _make_mock_config(
    llm_answer: str = "Ответ.",
    streaming_enabled: bool = True,
    response_model: str = "cerebras/gpt-oss-120b",
) -> tuple[MagicMock, MagicMock]:
    """Create mock GraphConfig + AsyncOpenAI client for generate_node tests."""
    mock_choice = MagicMock()
    mock_choice.message.content = llm_answer
    mock_response = MagicMock(choices=[mock_choice])
    mock_response.model = response_model

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    mock_config = MagicMock()
    mock_config.domain = "недвижимость"
    mock_config.llm_model = "gpt-4o-mini"
    mock_config.llm_temperature = 0.7
    mock_config.llm_max_tokens = 4096
    mock_config.generate_max_tokens = 2048
    mock_config.streaming_enabled = streaming_enabled
    mock_config.create_llm.return_value = mock_client

    return mock_config, mock_client


class _MockStreamChunk:
    """Mock OpenAI streaming chunk with delta content."""

    def __init__(self, content: str | None = None, model: str | None = None):
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        self.choices = [choice] if content is not None else []
        self.model = model
        self.usage = None


class _MockReasoningStreamChunk:
    """Mock streaming chunk with reasoning content instead of delta.content.

    Simulates Cerebras gpt-oss-120b behavior where LiteLLM's
    merge_reasoning_content_in_choices fails in streaming mode —
    delta.content is None while reasoning tokens arrive via
    delta.reasoning_content or delta.reasoning.
    """

    def __init__(
        self,
        *,
        reasoning_content: str | None = None,
        reasoning: str | None = None,
        model: str | None = None,
    ):
        delta = MagicMock(spec=[])  # spec=[] prevents auto-attribute creation
        delta.content = None
        delta.reasoning_content = reasoning_content
        delta.reasoning = reasoning
        choice = MagicMock()
        choice.delta = delta
        self.choices = [choice]
        self.model = model
        self.usage = None


class _MockAsyncStream:
    """Async iterator that yields mock stream chunks."""

    def __init__(self, texts: list[str]):
        self._chunks = [_MockStreamChunk(t) for t in texts]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class _MockAsyncStreamFromChunks:
    """Async iterator over pre-built chunk objects (supports mixed chunk types)."""

    def __init__(self, chunks: list):
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class _MockStreamChunkWithUsage:
    """Final mock streaming chunk that includes token usage."""

    def __init__(self, completion_tokens: int, prompt_tokens: int = 100):
        self.choices = []  # no content in usage-only chunk
        self.model = None
        usage = MagicMock()
        usage.completion_tokens = completion_tokens
        usage.prompt_tokens = prompt_tokens
        usage.total_tokens = prompt_tokens + completion_tokens
        self.usage = usage


class _MockAsyncStreamWithUsage:
    """Async iterator that yields content chunks then a usage-only chunk."""

    def __init__(self, texts: list[str], completion_tokens: int):
        from typing import Any

        self._chunks: list[Any] = [_MockStreamChunk(t) for t in texts]
        self._chunks.append(_MockStreamChunkWithUsage(completion_tokens))
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


class _MockFailingStream:
    """Async iterator that yields some chunks then raises RuntimeError."""

    def __init__(self, good_texts: list[str]):
        self._chunks = [_MockStreamChunk(t) for t in good_texts]
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise RuntimeError("stream connection lost")
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def _make_streaming_client(chunks: list[str]) -> MagicMock:
    """Create mock client that returns a streaming response."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_MockAsyncStream(chunks),
    )
    return mock_client


def _make_streaming_config(
    mock_client: MagicMock | None = None,
    *,
    chunks: list[str] | None = None,
    generate_max_tokens: int = 2048,
) -> tuple[MagicMock, MagicMock]:
    """Create mock config for streaming tests.

    If ``mock_client`` is None and ``chunks`` are given, creates a simple streaming client.
    """
    if mock_client is None:
        mock_client = _make_streaming_client(chunks or [])
    mock_config = MagicMock()
    mock_config.domain = "недвижимость"
    mock_config.llm_model = "gpt-4o-mini"
    mock_config.llm_temperature = 0.7
    mock_config.llm_max_tokens = 4096
    mock_config.generate_max_tokens = generate_max_tokens
    mock_config.streaming_enabled = True
    mock_config.create_llm.return_value = mock_client
    return mock_config, mock_client


def _make_message_mock(**sent_kwargs: object) -> tuple[AsyncMock, AsyncMock]:
    """Create mock Telegram (message, sent_msg) pair.

    Extra ``sent_kwargs`` are set on ``sent_msg`` (e.g. ``message_id=77``).
    """
    sent_msg = AsyncMock()
    sent_msg.edit_text = AsyncMock()
    for k, v in sent_kwargs.items():
        setattr(sent_msg, k, v)
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)
    message.chat = MagicMock(id=12345)
    message.bot = MagicMock()
    message.bot.send_message_draft = AsyncMock(return_value=True)
    return message, sent_msg


def _make_state_with_docs(
    query: str = "Какие квартиры в Несебре?",
    documents: list | None = None,
    conversation_history: list | None = None,
) -> dict:
    """Helper: create a state with documents and optional conversation history."""
    state = make_initial_state(user_id=123, session_id="s-test", query=query)
    state["query_type"] = "GENERAL"
    state["documents"] = documents or [
        {
            "text": "Квартира в Несебре, 2 комнаты, 65000€",
            "score": 0.92,
            "metadata": {"title": "Апартамент Несебр", "city": "Несебр", "price": 65000},
        },
        {
            "text": "Студия в Несебре, 35000€, вид на море",
            "score": 0.87,
            "metadata": {"title": "Студия с видом", "city": "Несебр", "price": 35000},
        },
    ]
    if conversation_history:
        state["messages"] = conversation_history + state["messages"]
    return state


class TestGenerateNode:
    """Test generate_node produces answers from retrieved documents."""

    async def test_generates_from_docs(self) -> None:
        """generate_node calls LLM with formatted context and returns response."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config(
            "В Несебре есть квартира за 65000€ и студия за 35000€."
        )
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response"] == "В Несебре есть квартира за 65000€ и студия за 35000€."
        assert "generate" in result["latency_stages"]
        mock_client.chat.completions.create.assert_called_once()

        # Verify prompt contains context from docs
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        messages_text = " ".join(m["content"] for m in messages)
        assert "Несебр" in messages_text

    async def test_uses_conversation_history(self) -> None:
        """generate_node includes conversation history in the prompt."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Ответ с учётом контекста разговора.")

        history = [
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте! Чем могу помочь?"},
        ]
        state = _make_state_with_docs(
            query="А что есть в Несебре?",
            conversation_history=history,
        )

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response"] == "Ответ с учётом контекста разговора."
        # Verify conversation history is included in messages
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        messages_text = " ".join(m["content"] for m in messages)
        assert "Привет" in messages_text
        assert "Здравствуйте" in messages_text

    async def test_limits_long_conversation_history_window(self) -> None:
        """generate_node keeps only recent history messages before LLM call."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Ответ на вопрос.")

        # Create state with 30 message pairs (60 messages total) — way more than 10-15
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"Вопрос {i} о недвижимости"})
            history.append({"role": "assistant", "content": f"Ответ {i} про квартиры"})

        state = _make_state_with_docs(
            query="А подешевле есть?",
            conversation_history=history,
        )

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")

        # Should NOT contain all 60 history messages — only recent window
        # system(1) + history(trimmed) + user_with_context(1)
        history_messages = [m for m in messages if m["role"] != "system"]
        # At most 13 messages (12 history + final user), not 61
        assert len(history_messages) <= 13, (
            f"Expected limited history, got {len(history_messages)} messages"
        )
        # First history message should NOT be "Вопрос 0" (it was trimmed)
        user_history = [m for m in history_messages[:-1] if m["role"] == "user"]
        if user_history:
            assert "Вопрос 0" not in user_history[0]["content"], "Old messages should be trimmed"

    async def test_system_prompt_includes_history_instruction(self) -> None:
        """generate_node system prompt instructs LLM to use conversation history."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]["content"]
        assert "истори" in system_msg.lower(), (
            f"System prompt should mention conversation history, got: {system_msg[:200]}"
        )

    async def test_injects_history_instruction_when_managed_prompt_missing_it(self) -> None:
        """Legacy managed prompt must still include history instruction if remote prompt lacks it."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        state = _make_state_with_docs()

        with (
            patch(
                "telegram_bot.graph.nodes.generate._get_config",
                return_value=mock_config,
            ),
            patch(
                "telegram_bot.graph.nodes.generate.get_prompt",
                return_value="Ты — ассистент по недвижимости.",
            ),
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]["content"]
        assert "истори" in system_msg.lower()

    async def test_fallback_on_error(self) -> None:
        """generate_node returns fallback response when LLM fails."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM unavailable"))

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response"] != ""
        assert "generate" in result["latency_stages"]
        # Fallback should mention found objects or service unavailability
        assert "Несебр" in result["response"] or "недоступен" in result["response"]

    async def test_system_prompt_uses_domain(self) -> None:
        """generate_node builds system prompt with domain from config."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        # System prompt should contain domain
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]
        assert "недвижимость" in system_msg["content"]

    async def test_limits_to_top_5_docs(self) -> None:
        """generate_node formats only top-5 documents for context."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()

        docs = [
            {"text": f"Doc {i}", "score": 1.0 - i * 0.1, "metadata": {"title": f"Doc {i}"}}
            for i in range(10)
        ]
        state = _make_state_with_docs(documents=docs)

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        # Check that context has at most 5 documents
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        messages_text = " ".join(m["content"] for m in messages)
        assert "Doc 0" in messages_text
        assert "Doc 4" in messages_text
        assert "Doc 5" not in messages_text

    async def test_respects_generate_max_tokens(self) -> None:
        """generate_node passes generate_max_tokens from config to LLM call."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Short answer.")
        mock_config.generate_max_tokens = 512
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("max_tokens") == 512

    async def test_empty_documents_fallback(self) -> None:
        """generate_node handles empty documents gracefully."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("К сожалению, информации не найдено.")
        state = _make_state_with_docs(documents=[])

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response"] != ""

    async def test_non_streaming_returns_response_sent_false(self) -> None:
        """generate_node without message sets response_sent=False."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("Ответ.")
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response_sent"] is False


class TestGenerateNodeStreaming:
    """Test generate_node streaming delivery to Telegram."""

    async def test_streaming_uses_drafts_and_final_persisted_message(self) -> None:
        """Streaming sends draft updates, then persists the final answer as a real message."""
        from telegram_bot.graph.nodes.generate import generate_node

        chunks = ["Квартира ", "в Несебре ", "стоит 65000€."]
        mock_config, mock_client = _make_streaming_config(chunks=chunks)
        message, sent_msg = _make_message_mock()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        # Draft updates are used during generation.
        message.bot.send_message_draft.assert_awaited()
        draft_call = message.bot.send_message_draft.call_args
        assert draft_call.kwargs["chat_id"] == 12345
        assert draft_call.kwargs["text"].startswith("Квартира")

        # Final persisted message uses message.answer with Markdown.
        full_text = "Квартира в Несебре стоит 65000€."
        message.answer.assert_awaited_once()
        assert message.answer.call_args.args[0] == full_text
        assert message.answer.call_args.kwargs["parse_mode"] == "Markdown"

        # Response contains all chunks
        assert result["response"] == full_text
        assert result["response_sent"] is True
        assert "generate" in result["latency_stages"]

        sent_msg.edit_text.assert_not_called()

        # stream=True was passed to LLM
        create_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert create_kwargs["stream"] is True

    async def test_streaming_returns_serializable_sent_message_ref(self) -> None:
        """Streaming path stores serializable message reference for checkpointer safety."""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        from telegram_bot.graph.nodes.generate import generate_node

        chunks = ["Ответ ", "готов."]
        mock_config, _mock_client = _make_streaming_config(chunks=chunks)
        message, _sent_msg = _make_message_mock(
            message_id=77,
            chat=MagicMock(id=12345),
        )

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["response_sent"] is True
        assert result["sent_message"] == {"chat_id": 12345, "message_id": 77}
        # Regression guard: this value is persisted by checkpointer and must be msgpack-safe.
        JsonPlusSerializer().dumps_typed(result["sent_message"])

    async def test_streaming_fallback_on_stream_error(self) -> None:
        """When streaming fails, falls back to non-streaming LLM call."""
        from telegram_bot.graph.nodes.generate import generate_node

        # First call (stream=True) raises, second call (non-stream) succeeds
        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback answer."
        mock_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[Exception("stream error"), mock_response],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message = AsyncMock()
        message.answer = AsyncMock(return_value=AsyncMock())
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["response"] == "Fallback answer."
        assert result["response_sent"] is False

    async def test_streaming_disabled_uses_non_streaming(self) -> None:
        """When streaming_enabled=False, uses non-streaming even with message."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("Non-stream answer.", streaming_enabled=False)

        message = AsyncMock()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["response"] == "Non-stream answer."
        assert result["response_sent"] is False
        # message.answer should NOT have been called (respond_node handles it)
        message.answer.assert_not_called()

    async def test_streaming_empty_response_falls_back(self) -> None:
        """Streaming with empty chunks falls back to non-streaming."""
        from telegram_bot.graph.nodes.generate import generate_node

        # Stream produces no content
        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback from empty stream."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_MockAsyncStream([]), mock_fallback_response],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, _sent_msg = _make_message_mock(delete=AsyncMock())

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["response"] == "Fallback from empty stream."
        assert result["response_sent"] is False

    async def test_stream_error_before_visible_output(self) -> None:
        """Stream fails before any real content is visible: response_sent=False."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback answer."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[_MockFailingStream([]), mock_fallback_response],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, _sent_msg = _make_message_mock(delete=AsyncMock())

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["response"] == "Fallback answer."
        assert result["response_sent"] is False

    async def test_stream_error_after_visible_output(self) -> None:
        """Visible draft output then failed stream falls back to a final persisted message."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback complete answer."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _MockFailingStream(["Квартира ", "в Несебре "]),
                mock_fallback_response,
            ],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, sent_msg = _make_message_mock()

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        # Fallback answer is the response
        assert result["response"] == "Fallback complete answer."
        assert result["response_sent"] is True
        message.bot.send_message_draft.assert_awaited()
        assert message.answer.await_count == 1
        assert message.answer.await_args_list[0].args[0] == "Квартира в Несебре "
        sent_msg.edit_text.assert_awaited_once_with(
            "Fallback complete answer.",
            parse_mode="HTML",
        )

    async def test_stream_error_partial_and_final_delivery_fails_falls_back_to_respond_node(
        self,
    ) -> None:
        """If final delivery fails after partial draft output, respond_node must send answer."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Final fallback answer."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _MockFailingStream(["partial "]),
                mock_fallback_response,
            ],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, sent_msg = _make_message_mock()
        sent_msg.edit_text = AsyncMock(
            side_effect=[
                Exception("markdown edit failed"),
                Exception("plain edit failed"),
            ]
        )
        message.answer = AsyncMock(
            side_effect=[
                sent_msg,
                Exception("markdown send failed"),
                Exception("plain send failed"),
            ]
        )

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["response"] == "Final fallback answer."
        assert result["response_sent"] is False
        assert message.answer.await_count == 3


class TestGenerateNodeProviderMetadata:
    """Test provider metadata and TTFT tracking in generate_node."""

    async def test_non_streaming_captures_provider_model(self) -> None:
        """Non-streaming path captures response.model and one-shot TTFT."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config(
            "Ответ.",
            response_model="cerebras/gpt-oss-120b",
        )
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["llm_provider_model"] == "cerebras/gpt-oss-120b"
        assert result["llm_response_duration_ms"] > 0
        assert result["llm_ttft_ms"] > 0.0

    async def test_streaming_captures_ttft(self) -> None:
        """Streaming path measures TTFT > 0 on first content chunk."""
        from telegram_bot.graph.nodes.generate import generate_node

        chunks = ["Квартира ", "стоит ", "65000€."]
        mock_config, _mock_client = _make_streaming_config(chunks=chunks)
        message, _sent_msg = _make_message_mock()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_ttft_ms"] >= 0.0  # should be > 0 in real scenario
        assert result["llm_response_duration_ms"] > 0

    async def test_streaming_captures_model_from_chunk(self) -> None:
        """Streaming path extracts model from chunk.model attribute."""
        from telegram_bot.graph.nodes.generate import generate_node

        # Build chunks with model info
        chunk1 = _MockStreamChunk("Hello ", model="groq/llama-3.1-70b")
        chunk2 = _MockStreamChunk("world.", model="groq/llama-3.1-70b")
        stream = _MockAsyncStream.__new__(_MockAsyncStream)
        stream._chunks = [chunk1, chunk2]
        stream._index = 0

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=stream)
        mock_config, _ = _make_streaming_config(mock_client)
        message, _sent_msg = _make_message_mock()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_provider_model"] == "groq/llama-3.1-70b"

    async def test_fallback_sets_fallback_model(self) -> None:
        """When LLM fails completely, llm_provider_model = 'fallback'."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("LLM unavailable"),
        )

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["llm_provider_model"] == "fallback"
        assert result["llm_ttft_ms"] == 0.0
        assert result["llm_response_duration_ms"] > 0

    async def test_partial_stream_fallback_preserves_token_usage_in_span(self) -> None:
        """StreamingPartialDeliveryError fallback should keep token_usage in curated span output."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback complete answer."
        usage = MagicMock(prompt_tokens=123, completion_tokens=45, total_tokens=168)
        mock_fallback_response = MagicMock(choices=[mock_choice], model="gpt-4o-mini", usage=usage)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _MockFailingStream(["Квартира ", "в Несебре "]),  # partial stream then error
                mock_fallback_response,  # non-stream fallback response
            ],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, _sent_msg = _make_message_mock()
        mock_lf = MagicMock()

        state = _make_state_with_docs()

        with (
            patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            await generate_node(state, message=message)

        output_calls = [
            c.kwargs["output"]
            for c in mock_lf.update_current_span.call_args_list
            if "output" in c.kwargs
        ]
        assert output_calls, "generate_node must emit output span"
        final_output = output_calls[-1]
        assert final_output["token_usage"]["prompt_tokens"] == 123
        assert final_output["token_usage"]["completion_tokens"] == 45
        assert final_output["token_usage"]["total_tokens"] == 168


class TestGenerateNodeLatencyBreakdown:
    """Test decode_ms, tps, queue_ms, and flag computation (#147)."""

    async def test_streaming_computes_decode_ms(self) -> None:
        """Streaming path: decode_ms = response_duration_ms - ttft_ms."""
        from telegram_bot.graph.nodes.generate import generate_node

        chunks = ["Квартира ", "в Несебре ", "стоит 65000€."]
        mock_config, _mock_client = _make_streaming_config(chunks=chunks)
        message, _sent_msg = _make_message_mock()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_decode_ms"] is not None
        assert result["llm_decode_ms"] >= 0
        assert result["streaming_enabled"] is True

    async def test_streaming_with_usage_computes_tps(self) -> None:
        """Streaming with token usage: tps = completion_tokens / (decode_s)."""
        from telegram_bot.graph.nodes.generate import generate_node

        stream = _MockAsyncStreamWithUsage(
            texts=["Квартира ", "стоит ", "65000€."],
            completion_tokens=42,
        )
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=stream)
        mock_config, _ = _make_streaming_config(mock_client)
        message, _sent_msg = _make_message_mock()

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_tps"] is not None
        assert result["llm_tps"] > 0

    async def test_non_streaming_decode_and_tps_are_none(self) -> None:
        """Non-streaming: decode_ms and tps are None."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("Ответ.", streaming_enabled=False)
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["llm_decode_ms"] is None
        assert result["llm_tps"] is None
        assert result["streaming_enabled"] is False

    async def test_streaming_without_usage_tps_is_none(self) -> None:
        """Streaming without token usage: tps is None."""
        from telegram_bot.graph.nodes.generate import generate_node

        chunks = ["Hello ", "world."]
        mock_config, _mock_client = _make_streaming_config(chunks=chunks)
        message, _sent_msg = _make_message_mock()

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_decode_ms"] is not None
        assert result["llm_tps"] is None

    async def test_stream_recovery_sets_flags(self) -> None:
        """Streaming fails before content → non-streaming saves → recovery flags set."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback answer."
        mock_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[Exception("stream error"), mock_response],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message = AsyncMock()
        message.answer = AsyncMock(return_value=AsyncMock())
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_stream_recovery"] is True
        assert result["llm_timeout"] is False
        assert result["streaming_enabled"] is True

    async def test_hard_fail_sets_timeout(self) -> None:
        """Complete LLM failure: llm_timeout=True, fallback_used."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("LLM unavailable"),
        )

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["llm_timeout"] is True
        assert result["llm_stream_recovery"] is False
        assert result["llm_decode_ms"] is None
        assert result["llm_tps"] is None

    async def test_partial_stream_recovery_sets_flags(self) -> None:
        """StreamingPartialDeliveryError → non-streaming fallback: recovery=True."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback complete answer."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _MockFailingStream(["partial "]),
                mock_fallback_response,
            ],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, _sent_msg = _make_message_mock()
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_stream_recovery"] is True
        assert result["llm_timeout"] is False

    async def test_partial_stream_recovery_true_even_if_final_delivery_fails(self) -> None:
        """Fallback generation still counts as recovery when final delivery fails."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback complete answer."
        mock_fallback_response = MagicMock(choices=[mock_choice])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _MockFailingStream(["partial "]),
                mock_fallback_response,
            ],
        )
        mock_config, _ = _make_streaming_config(mock_client)
        message, sent_msg = _make_message_mock()
        sent_msg.edit_text = AsyncMock(
            side_effect=[
                Exception("markdown edit failed"),
                Exception("plain edit failed"),
            ]
        )
        message.answer = AsyncMock(
            side_effect=[
                sent_msg,
                Exception("markdown send failed"),
                Exception("plain send failed"),
            ]
        )

        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state, message=message)

        assert result["llm_stream_recovery"] is True
        assert result["response_sent"] is False
        assert result["llm_timeout"] is False


class TestGenerateNodeResponseStyle:
    """Test adaptive response length control (#129)."""

    async def test_short_query_sets_response_style(self) -> None:
        """Short factoid query -> response_style='short', metrics present."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("73,000€ в Солнечном берегу.")
        state = _make_state_with_docs(query="сколько стоит студия")

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response_style"] == "short"
        assert result["response_difficulty"] == "easy"
        assert result["response_style_reasoning"] == "explicit_short_trigger"
        assert result["answer_words"] > 0
        assert result["answer_chars"] > 0
        assert result["answer_to_question_ratio"] > 0

    async def test_detailed_query_sets_response_style(self) -> None:
        """Comparison query -> response_style='detailed'."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config(
            "Несебр дешевле, но Равда ближе к пляжу. Вот таблица сравнения..."
        )
        state = _make_state_with_docs(query="сравни цены Несебр vs Равда подробно")

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            result = await generate_node(state)

        assert result["response_style"] == "detailed"
        assert result["answer_words"] > 0
        assert result["answer_to_question_ratio"] > 0

    async def test_style_budget_capped_by_generate_max_tokens(self) -> None:
        """Budget must be detector-derived but never exceed config.generate_max_tokens."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Short answer.")
        mock_config.response_style_enabled = True
        mock_config.response_style_shadow_mode = False
        mock_config.generate_max_tokens = 40
        # "сколько стоит" -> short/easy baseline budget=100, capped to 40
        state = _make_state_with_docs(query="сколько стоит студия")

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("max_tokens") == 40

    async def test_shadow_mode_keeps_legacy_prompt(self) -> None:
        """Shadow mode computes style metrics but uses legacy prompt/tokens."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Legacy answer.")
        mock_config.response_style_enabled = True
        mock_config.response_style_shadow_mode = True
        mock_config.generate_max_tokens = 2048
        state = _make_state_with_docs(query="сколько стоит студия")

        with (
            patch(
                "telegram_bot.graph.nodes.generate._get_config",
                return_value=mock_config,
            ),
            patch(
                "telegram_bot.graph.nodes.generate.build_system_prompt_with_manager",
            ) as mock_style_prompt,
        ):
            result = await generate_node(state)

        # Style fields are populated (shadow collects metrics)
        assert result["response_style"] == "short"
        assert result["response_policy_mode"] == "shadow"
        # But legacy max_tokens is used
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("max_tokens") == 2048
        # No style prompt manager call in shadow mode (avoid unnecessary overhead)
        mock_style_prompt.assert_not_called()

    async def test_disabled_mode_keeps_legacy_prompt_without_style_lookup(self) -> None:
        """Disabled mode should skip style prompt manager path entirely."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Legacy answer.")
        mock_config.response_style_enabled = False
        mock_config.response_style_shadow_mode = False
        mock_config.generate_max_tokens = 2048
        state = _make_state_with_docs(query="сколько стоит студия")

        with (
            patch(
                "telegram_bot.graph.nodes.generate._get_config",
                return_value=mock_config,
            ),
            patch(
                "telegram_bot.graph.nodes.generate.build_system_prompt_with_manager",
            ) as mock_style_prompt,
        ):
            result = await generate_node(state)

        assert result["response_policy_mode"] == "disabled"
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("max_tokens") == 2048
        mock_style_prompt.assert_not_called()

    async def test_style_mode_injects_history_instruction_if_missing(self) -> None:
        """Style-mode prompt must include history instruction even if style template lacks it."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config("Styled answer.")
        mock_config.response_style_enabled = True
        mock_config.response_style_shadow_mode = False
        mock_config.generate_max_tokens = 2048
        state = _make_state_with_docs(query="сколько стоит студия")

        with (
            patch(
                "telegram_bot.graph.nodes.generate._get_config",
                return_value=mock_config,
            ),
            patch(
                "telegram_bot.graph.nodes.generate.build_system_prompt_with_manager",
                return_value="STYLE PROMPT WITHOUT HISTORY",
            ),
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]["content"]
        assert "истори" in system_msg.lower()


class TestGenerateNodeCitationInstruction:
    """Test citation instruction injection (#225)."""

    async def test_citation_instruction_in_system_prompt(self) -> None:
        """System prompt includes citation instruction when show_sources=True."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_config.show_sources = True
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]["content"]
        assert "[1]" in system_msg
        assert "источник" in system_msg.lower()

    async def test_no_citation_instruction_when_disabled(self) -> None:
        """System prompt omits citation instruction when show_sources=False."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_config.show_sources = False
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]["content"]
        assert "[Объект 1] = [1]" not in system_msg

    async def test_context_omits_object_labels_when_sources_disabled(self) -> None:
        """Model-visible context must not contain numbered object labels when sources are hidden."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_config.show_sources = False
        state = _make_state_with_docs()

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_msg = messages[-1]["content"]
        assert "Фрагмент контекста" in user_msg
        assert "[Объект 1]" not in user_msg

    async def test_no_citation_instruction_without_documents(self) -> None:
        """No citation instruction when documents are empty."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, mock_client = _make_mock_config()
        mock_config.show_sources = True
        # Build state directly — _make_state_with_docs replaces [] with defaults
        state = make_initial_state(user_id=123, session_id="s-test", query="test")
        state["query_type"] = "GENERAL"
        state["documents"] = []

        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_config,
        ):
            await generate_node(state)

        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        system_msg = messages[0]["content"]
        assert "[Объект 1]" not in system_msg


class TestGenerateNodeEvalFields:
    """Test eval_query/eval_answer/eval_context fields for managed evaluators (#386)."""

    async def test_span_output_includes_eval_fields(self) -> None:
        """Curated span output must include eval_ fields for Langfuse evaluators."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("Квартира в Несебре стоит 65000€.")
        state = _make_state_with_docs()
        state["retrieved_context"] = [
            {"content": "Квартира в Несебре, 2 комнаты", "score": 0.92},
            {"content": "Студия в Несебре, вид на море", "score": 0.87},
        ]

        mock_lf = MagicMock()

        with (
            patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            await generate_node(state)

        # Find the span output call with eval_ fields
        output_calls = [
            c.kwargs["output"]
            for c in mock_lf.update_current_span.call_args_list
            if "output" in c.kwargs
        ]
        assert output_calls, "generate_node must emit output span"
        final_output = output_calls[-1]

        assert "eval_query" in final_output
        assert "eval_answer" in final_output
        assert "eval_context" in final_output
        assert "Несебр" in final_output["eval_query"]
        assert final_output["eval_answer"] == "Квартира в Несебре стоит 65000€."
        assert "0.92" in final_output["eval_context"]

    async def test_eval_fields_truncated(self) -> None:
        """eval_query and eval_answer are truncated to prevent huge spans."""
        from telegram_bot.graph.nodes.generate import generate_node

        long_query = "x" * 5000
        mock_config, _mock_client = _make_mock_config("y" * 5000)
        state = _make_state_with_docs(query=long_query)

        mock_lf = MagicMock()

        with (
            patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            await generate_node(state)

        output_calls = [
            c.kwargs["output"]
            for c in mock_lf.update_current_span.call_args_list
            if "output" in c.kwargs
        ]
        final_output = output_calls[-1]
        assert len(final_output["eval_query"]) <= 2000
        assert len(final_output["eval_answer"]) <= 3000

    async def test_eval_context_empty_when_no_retrieved_context(self) -> None:
        """eval_context is empty string when no retrieved_context in state."""
        from telegram_bot.graph.nodes.generate import generate_node

        mock_config, _mock_client = _make_mock_config("Ответ.")
        state = _make_state_with_docs()
        # No retrieved_context in state

        mock_lf = MagicMock()

        with (
            patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
            patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        ):
            await generate_node(state)

        output_calls = [
            c.kwargs["output"]
            for c in mock_lf.update_current_span.call_args_list
            if "output" in c.kwargs
        ]
        final_output = output_calls[-1]
        assert final_output["eval_context"] == ""


def test_format_context_no_raw_score():
    """_format_context in generate.py must NOT expose raw RRF scores to LLM."""
    from telegram_bot.graph.nodes.generate import _format_context

    docs = [
        {"text": "ВНЖ по работе", "score": 0.0167, "metadata": {"title": "Виды ВНЖ"}},
        {"text": "ВНЖ пенсионеры", "score": 0.0161, "metadata": {}},
    ]
    result = _format_context(docs, max_docs=5)
    # Must NOT contain raw RRF scores like "0.02" or "0.017"
    assert "0.02" not in result
    assert "0.017" not in result
    # Must contain object markers
    assert "[Объект 1]" in result
    assert "[Объект 2]" in result


# --- Reasoning content streaming tests (Cerebras gpt-oss-120b via LiteLLM) ---


async def test_streaming_reasoning_content_merged(monkeypatch):
    """Streaming with delta.reasoning_content (LiteLLM standardized) produces response.

    When LiteLLM merge_reasoning_content_in_choices is buggy in streaming mode,
    delta.content is None but delta.reasoning_content carries the tokens.
    """
    from telegram_bot.graph.nodes.generate import generate_node

    mock_config, mock_client = _make_mock_config()

    chunks = [
        _MockReasoningStreamChunk(reasoning_content="Рассуждение "),
        _MockReasoningStreamChunk(reasoning_content="и ответ"),
    ]
    stream = _MockAsyncStreamFromChunks(chunks)
    mock_client.chat.completions.create = AsyncMock(return_value=stream)

    mock_lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=1)
    sent_msg.message_id = 2
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    state = _make_state_with_docs(query="Тест reasoning_content")

    with (
        patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
        patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
    ):
        result = await generate_node(state, message=message)

    assert result["response"] == "Рассуждение и ответ"
    assert result["response_sent"] is True


async def test_streaming_raw_cerebras_reasoning_merged(monkeypatch):
    """Streaming with delta.reasoning (raw Cerebras field) produces response.

    Raw Cerebras gpt-oss-120b uses delta.reasoning (not reasoning_content).
    Our client-side merge must handle this as a second fallback.
    """
    from telegram_bot.graph.nodes.generate import generate_node

    mock_config, mock_client = _make_mock_config()

    chunks = [
        _MockReasoningStreamChunk(reasoning="Cerebras "),
        _MockReasoningStreamChunk(reasoning="рассуждение"),
    ]
    stream = _MockAsyncStreamFromChunks(chunks)
    mock_client.chat.completions.create = AsyncMock(return_value=stream)

    mock_lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=1)
    sent_msg.message_id = 2
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    state = _make_state_with_docs(query="Тест reasoning")

    with (
        patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
        patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
    ):
        result = await generate_node(state, message=message)

    assert result["response"] == "Cerebras рассуждение"
    assert result["response_sent"] is True


async def test_streaming_mixed_content_and_reasoning(monkeypatch):
    """Streaming with mixed delta.content and delta.reasoning_content works.

    Some chunks have delta.content (LiteLLM merge works), others have
    delta.reasoning_content (merge fails mid-stream). All must be accumulated.
    """
    from telegram_bot.graph.nodes.generate import generate_node

    mock_config, mock_client = _make_mock_config()

    chunks = [
        _MockReasoningStreamChunk(reasoning_content="Думаю... "),
        _MockStreamChunk("Ответ: "),
        _MockStreamChunk("Болгария"),
    ]
    stream = _MockAsyncStreamFromChunks(chunks)
    mock_client.chat.completions.create = AsyncMock(return_value=stream)

    mock_lf = MagicMock()
    sent_msg = AsyncMock()
    sent_msg.chat = MagicMock(id=1)
    sent_msg.message_id = 2
    sent_msg.edit_text = AsyncMock()
    message = AsyncMock()
    message.answer = AsyncMock(return_value=sent_msg)

    state = _make_state_with_docs(query="Тест mixed")

    with (
        patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
        patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
    ):
        result = await generate_node(state, message=message)

    assert result["response"] == "Думаю... Ответ: Болгария"
    assert result["response_sent"] is True
