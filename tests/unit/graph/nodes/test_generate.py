"""Tests for _generate_streaming parallelization in voice path (#685).

Issue #685: parallelize placeholder send + LLM stream creation via asyncio.gather.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
    placeholder_error: Exception | None = None,
    stream_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock, AsyncMock, AsyncMock]:
    """Return (llm, config, message, sent_msg) mocks for _generate_streaming tests."""
    if chunks is None:
        chunks = ["Hello ", "world!"]

    mock_sent_msg = AsyncMock()
    mock_sent_msg.edit_text = AsyncMock()
    mock_sent_msg.delete = AsyncMock()

    mock_message = AsyncMock()
    if placeholder_error is not None:
        mock_message.answer = AsyncMock(side_effect=placeholder_error)
    else:
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


async def test_placeholder_and_stream_parallel() -> None:
    """asyncio.gather is called to run placeholder send and LLM stream concurrently."""
    mock_llm, mock_config, mock_message, _ = _make_mocks()

    with patch(
        "telegram_bot.graph.nodes.generate.asyncio.gather", wraps=asyncio.gather
    ) as mock_gather:
        from telegram_bot.graph.nodes.generate import _generate_streaming

        await _generate_streaming(
            llm=mock_llm,
            config=mock_config,
            llm_messages=[{"role": "user", "content": "test"}],
            message=mock_message,
        )

    assert mock_gather.called, "asyncio.gather must be used for parallel execution (#685)"
    # gather should receive exactly 2 coroutines: LLM stream create + placeholder answer
    args = mock_gather.call_args[0]
    assert len(args) == 2, f"Expected 2 coroutines in gather, got {len(args)}"


async def test_placeholder_failure_graceful_degradation() -> None:
    """Placeholder send failure degrades gracefully: stream continues, sent_msg is None."""
    mock_llm, mock_config, mock_message, _ = _make_mocks(
        chunks=["Response text"],
        placeholder_error=Exception("Telegram rate limit"),
    )

    from telegram_bot.graph.nodes.generate import _generate_streaming

    result = await _generate_streaming(
        llm=mock_llm,
        config=mock_config,
        llm_messages=[{"role": "user", "content": "test"}],
        message=mock_message,
    )

    response_text = result[0]
    sent_msg = result[-1]

    assert response_text == "Response text", "Stream response must still be returned"
    assert sent_msg is None, "sent_msg must be None when placeholder fails (graceful degradation)"


async def test_stream_failure_raises() -> None:
    """LLM stream creation failure raises the exception and cleans up placeholder."""
    mock_llm, mock_config, mock_message, mock_sent_msg = _make_mocks(
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

    # Placeholder must be cleaned up when stream creation fails (#685 safety)
    mock_sent_msg.delete.assert_called_once()


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
