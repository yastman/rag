"""Focused unit tests for the voice transcription service (#3388).

The service owns the official ``AsyncOpenAI`` client lifecycle: the client
must be opened and closed per request (``async with``), a missing key must
construct no client and touch no network, and download/provider failures
must keep the text-fallback contract (``None`` out, cancellation through).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest


def _voice_message() -> AsyncMock:
    message = AsyncMock()
    message.voice = MagicMock(file_id="f1")
    message.bot = AsyncMock()
    file_mock = AsyncMock()
    file_mock.file_path = "voice/test.ogg"
    message.bot.get_file.return_value = file_mock
    return message


def _ready_config(**overrides) -> SimpleNamespace:
    defaults = {
        "voice_enabled": True,
        "llm_api_key": "cfg-key",
        "stt_model": "whisper-large-v3",
        "voice_language": "bg",
        "voice_timeout": 30,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _client_factory(
    *,
    create_result: object | None = None,
    create_side_effect: object | None = None,
):
    """Build an ``openai.AsyncOpenAI`` stand-in with a real async-CM lifecycle."""
    created: dict = {}
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.audio.transcriptions.create = AsyncMock(
        return_value=create_result, side_effect=create_side_effect
    )

    def _factory(*args, **kwargs):
        created["args"] = args
        created["kwargs"] = kwargs
        created["client"] = client
        created["calls"] = created.get("calls", 0) + 1
        return client

    return _factory, created


@pytest.fixture()
def no_provider_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)


class TestClientLifecycle:
    """The official client is opened and closed per request (#3388)."""

    async def test_client_closed_after_success(self, monkeypatch, no_provider_env) -> None:
        from telegram_bot.services.voice_transcription import transcribe_voice

        factory, created = _client_factory(create_result=SimpleNamespace(text="здравей"))
        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

        result = await transcribe_voice(message=_voice_message(), config=_ready_config())

        assert result == "здравей"
        client = created["client"]
        client.__aenter__.assert_awaited_once()
        client.__aexit__.assert_awaited_once()

    async def test_client_closed_after_provider_failure(self, monkeypatch, no_provider_env) -> None:
        from telegram_bot.services.voice_transcription import transcribe_voice

        factory, created = _client_factory(create_side_effect=RuntimeError("provider 500"))
        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

        result = await transcribe_voice(message=_voice_message(), config=_ready_config())

        assert result is None  # text-fallback contract preserved
        created["client"].__aexit__.assert_awaited_once()

    async def test_client_closed_on_cancellation(self, monkeypatch, no_provider_env) -> None:
        from telegram_bot.services.voice_transcription import transcribe_voice

        factory, created = _client_factory(create_side_effect=asyncio.CancelledError())
        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

        with pytest.raises(asyncio.CancelledError):
            await transcribe_voice(message=_voice_message(), config=_ready_config())

        created["client"].__aexit__.assert_awaited_once()

    async def test_client_receives_key_only_no_hardcoded_url(
        self, monkeypatch, no_provider_env
    ) -> None:
        """No provider base URL may be hard-coded into the STT call (#3388)."""
        from telegram_bot.services.voice_transcription import transcribe_voice

        factory, created = _client_factory(create_result=SimpleNamespace(text="ok"))
        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

        await transcribe_voice(message=_voice_message(), config=_ready_config())

        kwargs = created["kwargs"]
        assert kwargs.get("api_key") == "cfg-key"
        assert "base_url" not in kwargs


class TestMissingKey:
    """A missing key is represented honestly: no client, no network (#3388)."""

    async def test_no_key_constructs_no_client_and_no_download(
        self, monkeypatch, no_provider_env
    ) -> None:
        from telegram_bot.services.voice_transcription import transcribe_voice

        factory, created = _client_factory(create_result=SimpleNamespace(text="x"))
        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

        message = _voice_message()
        config = _ready_config(llm_api_key="   ")

        result = await transcribe_voice(message=message, config=config)

        assert result is None
        assert created.get("calls", 0) == 0  # no client construction, no sk-dev
        message.bot.get_file.assert_not_awaited()  # no network at all

    async def test_no_config_and_no_env_constructs_no_client(
        self, monkeypatch, no_provider_env
    ) -> None:
        from telegram_bot.services.voice_transcription import transcribe_voice

        factory, created = _client_factory(create_result=SimpleNamespace(text="x"))
        monkeypatch.setattr(openai, "AsyncOpenAI", factory)

        result = await transcribe_voice(message=_voice_message(), config=None)

        assert result is None
        assert created.get("calls", 0) == 0


class TestTransportBoundaries:
    """STT stays on the official SDK: no LiteLLM, no hard-coded URL (#3388)."""

    def test_module_has_no_litellm_or_hardcoded_provider_url(self) -> None:
        import ast
        import inspect

        from telegram_bot.services import voice_transcription

        tree = ast.parse(inspect.getsource(voice_transcription))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            assert not any("litellm" in name.lower() for name in names), names
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "api.openai.com" not in node.value
            if isinstance(node, ast.keyword):
                assert node.arg != "base_url"
