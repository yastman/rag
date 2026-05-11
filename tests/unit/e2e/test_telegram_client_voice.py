"""Unit tests for E2ETelegramClient voice-note delivery."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.e2e.config import E2EConfig
from scripts.e2e.telegram_client import BotResponse, E2ETelegramClient


class _Msg:
    def __init__(self, text: str, message_id: int = 1) -> None:
        self.text = text
        self.id = message_id


class _Conv:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send_message(self, _query: str) -> None:
        return None

    async def send_file(self, _path: str, *, voice_note: bool = False) -> None:
        self.last_path = _path
        self.last_voice_note = voice_note

    async def get_response(self):
        return _Msg("ok")

    async def get_edit(self, **_kwargs):
        raise TimeoutError


class _FakeClient:
    def __init__(self) -> None:
        self.last_username: str | None = None

    def conversation(self, username: str, timeout: int):
        self.last_username = username
        return _Conv()


def _cfg_with_voice(voice_path: str) -> E2EConfig:
    with patch.dict(os.environ, {"E2E_VOICE_NOTE_PATH": voice_path}, clear=False):
        return E2EConfig()


@pytest.mark.asyncio
async def test_send_voice_and_wait_uses_conversation_send_file(tmp_path: Path) -> None:
    fixture = tmp_path / "voice.mp3"
    fixture.write_text("fake audio")
    cfg = _cfg_with_voice(str(fixture))

    telethon_client = _FakeClient()
    client = E2ETelegramClient(cfg)
    client._client = telethon_client

    result = await client.send_voice_and_wait()

    assert isinstance(result, BotResponse)
    assert result.text == "ok"


@pytest.mark.asyncio
async def test_send_voice_and_wait_raises_when_path_not_configured() -> None:
    cfg = _cfg_with_voice("")
    client = E2ETelegramClient(cfg)
    client._client = _FakeClient()

    with pytest.raises(RuntimeError, match="E2E_VOICE_NOTE_PATH is not set"):
        await client.send_voice_and_wait()


@pytest.mark.asyncio
async def test_send_voice_and_wait_raises_when_fixture_missing() -> None:
    cfg = _cfg_with_voice("/nonexistent/path/to/voice.mp3")
    client = E2ETelegramClient(cfg)
    client._client = _FakeClient()

    with pytest.raises(RuntimeError, match="Voice note fixture not found"):
        await client.send_voice_and_wait()


def test_config_reads_e2e_voice_note_path() -> None:
    cfg = _cfg_with_voice("/tmp/e2e/voice_fixture.mp3")
    assert cfg.voice_note_path == "/tmp/e2e/voice_fixture.mp3"
