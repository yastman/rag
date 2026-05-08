from __future__ import annotations

import pytest

from scripts.e2e.config import E2EConfig
from scripts.e2e.telegram_client import E2ETelegramClient


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


@pytest.mark.asyncio
async def test_send_and_wait_targets_configured_e2e_bot_username() -> None:
    cfg = E2EConfig(
        telegram_api_id=1,
        telegram_api_hash="hash",
        bot_username="@my_target_bot",
    )
    telethon_client = _FakeClient()

    client = E2ETelegramClient(cfg)
    client._client = telethon_client  # inject fake connected client

    _ = await client.send_and_wait("hello")

    assert telethon_client.last_username == "@my_target_bot"
