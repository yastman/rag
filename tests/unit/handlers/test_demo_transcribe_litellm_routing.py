"""demo_handler.transcribe_voice must route Whisper through the LiteLLM proxy (#2214).

The default (no-injected-llm) client is a bare ``AsyncOpenAI()``, which targets
the public OpenAI endpoint. The transcription uses ``model="whisper"`` — a
LiteLLM alias — so it must go through the LiteLLM proxy (``LLM_BASE_URL``), which
also carries the ``success_callback: ["langfuse"]`` config. Without
``base_url``/``api_key`` the call hits public OpenAI (404 on the alias) and
bypasses the proxy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestTranscribeVoiceLiteLLMRouting:
    async def test_transcribe_voice_default_client_uses_litellm_proxy_env(
        self, monkeypatch
    ) -> None:
        import langfuse.openai as lf_openai

        from telegram_bot.handlers.demo_handler import transcribe_voice

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", "http://litellm:4000/v1")

        created: dict = {}
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=MagicMock(text="привет"))

        def _factory(*args, **kwargs):
            created["kwargs"] = kwargs
            return mock_client

        monkeypatch.setattr(lf_openai, "AsyncOpenAI", _factory)

        message = AsyncMock()
        message.voice = MagicMock(file_id="f1")
        message.bot = AsyncMock()
        file_mock = AsyncMock()
        file_mock.file_path = "voice/test.ogg"
        message.bot.get_file.return_value = file_mock

        result = await transcribe_voice(message)  # llm=None -> default client path

        assert result == "привет"
        assert created.get("kwargs", {}).get("api_key") == "test-key"
        assert created.get("kwargs", {}).get("base_url") == "http://litellm:4000/v1"
