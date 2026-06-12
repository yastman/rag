"""demo_handler.transcribe_voice uses direct OpenAI Whisper after proxy removal."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestTranscribeVoiceOpenAIRouting:
    async def test_transcribe_voice_default_client_uses_openai_api_key(self, monkeypatch) -> None:
        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        created: dict = {}
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=MagicMock(text="привет"))

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

    async def test_transcribe_voice_default_client_falls_back_to_dev_key(self, monkeypatch) -> None:
        import openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        monkeypatch.delenv("LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        created: dict = {}
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=MagicMock(text="привет"))

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

        result = await transcribe_voice(message)

        assert result == "привет"
        assert created.get("kwargs", {}).get("api_key") == "sk-dev"
