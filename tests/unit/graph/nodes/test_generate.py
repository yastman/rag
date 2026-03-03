"""Tests for _generate_streaming in voice path — native sendMessageDraft (Bot API 9.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockStreamChunk:
    """Mock OpenAI streaming chunk."""

    def __init__(self, content: str | None = None, model: str | None = None) -> None:
        delta = MagicMock()
        delta.content = content
        choice = MagicMock()
        choice.delta = delta
        self.choices = [choice] if content is not None else []
        self.model = model
        self.usage = None


class _MockAsyncStream:
    """Async iterator yielding mock stream chunks."""

    def __init__(self, texts: list[str]) -> None:
        self._chunks = [_MockStreamChunk(t) for t in texts]
        self._index = 0

    def __aiter__(self) -> _MockAsyncStream:
        return self

    async def __anext__(self) -> _MockStreamChunk:
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def _make_mocks(
    chunks: list[str] | None = None,
    stream_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock, AsyncMock, AsyncMock]:
    """Return (llm, config, message, sent_msg) mocks for _generate_streaming tests."""
    if chunks is None:
        chunks = ["Hello ", "world!"]

    mock_sent_msg = AsyncMock()
    mock_sent_msg.chat = MagicMock(id=123)
    mock_sent_msg.message_id = 456

    mock_bot = AsyncMock()
    mock_bot.send_message_draft = AsyncMock(return_value=True)

    mock_message = AsyncMock()
    mock_message.chat = MagicMock(id=123)
    mock_message.bot = mock_bot
    mock_message.answer = AsyncMock(return_value=mock_sent_msg)

    mock_stream = _MockAsyncStream(chunks)
    mock_llm = MagicMock()
    if stream_error is not None:
        mock_llm.chat.completions.create = AsyncMock(side_effect=stream_error)
    else:
        mock_llm.chat.completions.create = AsyncMock(return_value=mock_stream)

    mock_config = MagicMock()
    mock_config.llm_model = "gpt-4o-mini"
    mock_config.llm_temperature = 0.7
    mock_config.generate_max_tokens = 2048

    return mock_llm, mock_config, mock_message, mock_sent_msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_streaming_uses_send_message_draft() -> None:
    """Voice path streaming uses bot.send_message_draft instead of edit_text."""
    mock_llm, mock_config, mock_message, _ = _make_mocks()

    from telegram_bot.graph.nodes.generate import _generate_streaming

    result = await _generate_streaming(
        llm=mock_llm,
        config=mock_config,
        llm_messages=[{"role": "user", "content": "test"}],
        message=mock_message,
    )

    assert result[0] == "Hello world!"
    mock_message.bot.send_message_draft.assert_called()
    mock_message.answer.assert_called_once()


async def test_stream_failure_raises() -> None:
    """LLM stream creation failure raises the exception."""
    mock_llm, mock_config, mock_message, _ = _make_mocks(
        stream_error=ConnectionError("LLM unavailable"),
    )

    from telegram_bot.graph.nodes.generate import _generate_streaming

    with pytest.raises(ConnectionError, match="LLM unavailable"):
        await _generate_streaming(
            llm=mock_llm,
            config=mock_config,
            llm_messages=[{"role": "user", "content": "test"}],
            message=mock_message,
        )


async def test_streaming_retries_without_name_kwarg_for_plain_openai() -> None:
    """Voice-path streaming retries without Langfuse `name` kwarg when unsupported."""
    mock_llm, mock_config, mock_message, _ = _make_mocks(chunks=["Voice ", "ok"])
    mock_stream = _MockAsyncStream(["Voice ", "ok"])
    mock_llm.chat.completions.create = AsyncMock(
        side_effect=[
            TypeError("create() got an unexpected keyword argument 'name'"),
            mock_stream,
        ]
    )

    from telegram_bot.graph.nodes.generate import _generate_streaming

    result = await _generate_streaming(
        llm=mock_llm,
        config=mock_config,
        llm_messages=[{"role": "user", "content": "test"}],
        message=mock_message,
    )

    assert result[0] == "Voice ok"
    assert mock_llm.chat.completions.create.await_count == 2
    first_call = mock_llm.chat.completions.create.await_args_list[0].kwargs
    second_call = mock_llm.chat.completions.create.await_args_list[1].kwargs
    assert first_call.get("name") == "generate-answer"
    assert "name" not in second_call
