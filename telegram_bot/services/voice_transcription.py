"""Voice transcription service — shared by demo and catalog dialogs (#3238).

Whisper STT remains a direct OpenAI SDK call because the LiteLLM Docker
proxy has been removed; the module is transport-neutral so neither dialog
needs to import the demo handler implementation.
"""

from __future__ import annotations

import io
import os
from typing import Any

from aiogram.types import Message


async def transcribe_voice(message: Message, *, llm: Any = None) -> str | None:
    """Download a Telegram voice message and transcribe via Whisper.

    The optional ``llm`` parameter accepts an audio transcription client so
    tests can inject a mock.
    """
    from openai import AsyncOpenAI

    async def _run() -> str | None:
        bot = message.bot
        if bot is None or message.voice is None:
            return None
        file = await bot.get_file(message.voice.file_id)
        data = io.BytesIO()
        await bot.download_file(file.file_path, data)  # type: ignore[arg-type]
        data.seek(0)
        data.name = "voice.ogg"  # type: ignore[attr-defined]

        # Whisper STT is intentionally direct OpenAI SDK usage. LiteLLM chat
        # routing now happens in-process via src.runtime.llm.router, and the
        # removed Docker proxy no longer hosts a Whisper alias.
        client = (
            llm
            if llm is not None
            else AsyncOpenAI(
                api_key=os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or "sk-dev",
            )
        )
        transcript = await client.audio.transcriptions.create(
            model="whisper",
            file=data,
            language="ru",
        )
        return transcript.text or None  # type: ignore[no-any-return]

    return await _run()  # type: ignore[no-any-return]


__all__ = ["transcribe_voice"]
