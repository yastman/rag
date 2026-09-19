"""Run production main with a deterministic Telegram transport, only in the E2E container."""

import asyncio
from pathlib import Path
from unittest.mock import patch

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import User


POLLING_MARKER = Path("/tmp/e2e-polling")


class LocalTelegramSession(BaseSession):
    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 - aiogram interface
        name = method.__api_method__
        if name == "getMe":
            return User(
                id=bot.id, is_bot=True, first_name="Deterministic E2E", username="local_e2e_bot"
            )
        if name in {"setMyCommands", "setChatMenuButton", "deleteWebhook"}:
            return True
        if name == "getUpdates":
            # Only the actual Dispatcher polling loop reaches this boundary.
            # No service readiness is inferred merely from a running process.
            POLLING_MARKER.touch()
            await asyncio.sleep(1)
            return []
        raise RuntimeError(f"Unexpected Telegram method in idle E2E runtime: {name}")

    async def stream_content(self, url, **kwargs):
        raise RuntimeError("Idle E2E bot must not download external content")
        yield b""  # pragma: no cover - BaseSession requires an async iterator


def local_bot(*args, **kwargs):
    return Bot(*args, **kwargs, session=LocalTelegramSession())


if __name__ == "__main__":
    from telegram_bot.main import main

    with patch("telegram_bot.bot.Bot", new=local_bot):
        asyncio.run(main())
