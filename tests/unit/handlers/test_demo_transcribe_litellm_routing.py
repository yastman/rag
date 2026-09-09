"""demo_handler.transcribe_voice uses direct OpenAI Whisper after proxy removal.

#3388: the official ``AsyncOpenAI`` client lifecycle is scoped per request
(``async with``) and a missing key constructs no client at all — the old
``sk-dev`` fallback is gone.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def _async_cm_client(create_result=None, create_side_effect=None) -> MagicMock:
    """Build an ``AsyncOpenAI`` stand-in honouring the async context manager."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.audio.transcriptions.create = AsyncMock(
        return_value=create_result, side_effect=create_side_effect
    )
    return client


class TestTranscribeVoiceOpenAIRouting:
    async def test_transcribe_voice_default_client_uses_openai_api_key(self, monkeypatch) -> None:
        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        created: dict = {}
        mock_client = _async_cm_client(create_result=MagicMock(text="привет"))

        def _factory(*args, **kwargs):
            created["kwargs"] = kwargs
            return mock_client

        monkeypatch.setattr(openai, "AsyncOpenAI", _factory)

        message = AsyncMock()
        message.voice = MagicMock(file_id="f1")
        message.bot = AsyncMock()
        file_mock = AsyncMock()
        file_mock.file_path = "voice/test.ogg"
        message.bot.get_file.return_value = file_mock

        result = await transcribe_voice(message)  # llm=None -> default client path

        assert result == "привет"
        assert created.get("kwargs", {}).get("api_key") == "test-key"
        mock_client.__aexit__.assert_awaited_once()  # client closed per request

    async def test_transcribe_voice_without_key_constructs_no_client(self, monkeypatch) -> None:
        """Missing key is honest: no client construction, no network (#3388)."""
        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        created: dict = {}

        def _factory(*args, **kwargs):
            created["kwargs"] = kwargs
            return _async_cm_client(create_result=MagicMock(text="привет"))

        monkeypatch.setattr(openai, "AsyncOpenAI", _factory)

        message = AsyncMock()
        message.voice = MagicMock(file_id="f1")
        message.bot = AsyncMock()

        result = await transcribe_voice(message)

        assert result is None
        assert created == {}  # AsyncOpenAI never constructed — no sk-dev
        message.bot.get_file.assert_not_awaited()  # no network at all
