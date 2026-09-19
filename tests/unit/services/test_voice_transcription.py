"""The direct audio adapter owns its official SDK client's lifetime."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from telegram_bot.services.voice_transcription import transcribe_voice


def _message():
    return SimpleNamespace(
        voice=SimpleNamespace(file_id="voice-id"),
        bot=SimpleNamespace(
            get_file=AsyncMock(return_value=SimpleNamespace(file_path="voice.ogg")),
            download_file=AsyncMock(),
        ),
    )


@pytest.mark.parametrize("outcome", ["success", "provider_error", "timeout", "cancel"])
async def test_official_client_closes_on_every_exit(monkeypatch, outcome):
    client = openai.AsyncOpenAI(api_key="test-key")
    close = AsyncMock(wraps=client.close)
    monkeypatch.setattr(client, "close", close)
    started = asyncio.Event()

    async def transcribe(**kwargs):
        started.set()
        if outcome == "provider_error":
            raise RuntimeError("provider failure")
        if outcome in {"timeout", "cancel"}:
            await asyncio.Event().wait()
        return SimpleNamespace(text="transcribed")

    monkeypatch.setattr(client.audio.transcriptions, "create", transcribe)
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    config = SimpleNamespace(llm_api_key="test-key", voice_timeout=0.05)
    try:
        task = asyncio.create_task(transcribe_voice(_message(), config=config))
        if outcome == "cancel":
            await asyncio.wait_for(started.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert result == ("transcribed" if outcome == "success" else None)
        factory.assert_called_once_with(api_key="test-key")
        close.assert_awaited_once()
        assert client.is_closed()
    finally:
        if not client.is_closed():
            await close()


@pytest.mark.parametrize("key", ["", "   "])
async def test_missing_key_never_constructs_client_or_downloads(monkeypatch, key):
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setenv("LLM_API_KEY", key)
    factory = MagicMock(side_effect=AssertionError("no client without a key"))
    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    message = _message()

    assert await transcribe_voice(message) is None
    factory.assert_not_called()
    message.bot.get_file.assert_not_awaited()
    message.bot.download_file.assert_not_awaited()
