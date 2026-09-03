"""Voice transcription service — shared by demo and catalog dialogs (#3238, #3240).

Whisper STT remains a direct OpenAI SDK call because the LiteLLM Docker
proxy has been removed and the in-process LiteLLM chat client exposes no
transcription API; the module is transport-neutral so neither dialog needs
to import handler implementations.

Configuration-driven (#3240): model, language, key, and timeout come from
``BotConfig`` (``stt_model``, ``voice_language``, ``llm_api_key``,
``voice_timeout``). With ``config=None`` the historical defaults apply
(model ``whisper``, language ``ru``, key from ``OPENAI_API_KEY`` /
``LLM_API_KEY``).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from typing import Any

from aiogram.types import Message


logger = logging.getLogger(__name__)


def voice_ready(config: Any) -> bool:
    """Voice input may be exposed only when explicitly enabled and keyed (#3240).

    Voice is an optional adapter: without ``VOICE_ENABLED`` and a transcription
    key the dialogs must not advertise, accept, or attempt voice — they route
    users to the proven typed-input path instead. Duck-typed so tests can pass
    lightweight config stubs.
    """
    if config is None:
        return False
    if not getattr(config, "voice_enabled", False):
        return False
    return bool(str(getattr(config, "llm_api_key", "") or "").strip())



async def transcribe_voice(message: Message, *, config: Any = None) -> str | None:
    """Download a Telegram voice message and transcribe it via direct OpenAI STT.

    Configuration-driven (#3240): model, language, key, and timeout come from
    ``BotConfig`` (``stt_model``, ``voice_language``, ``llm_api_key``,
    ``voice_timeout``). With ``config=None`` the historical defaults apply
    (model ``whisper``, language ``ru``, key from ``OPENAI_API_KEY`` /
    ``LLM_API_KEY``). Whisper STT remains a direct OpenAI SDK call because the
    LiteLLM Docker proxy has been removed and the in-process LiteLLM chat
    client exposes no transcription API.

    Text-fallback safe: Telegram download failures, provider errors, and
    timeouts are logged and returned as ``None`` — this helper never raises,
    so dialogs can offer typed input instead of blocking.
    """
    bot = getattr(message, "bot", None)
    voice = getattr(message, "voice", None)
    if bot is None or voice is None:
        return None

    stt_model = str(getattr(config, "stt_model", "") or "whisper")
    voice_language = str(getattr(config, "voice_language", "") or "ru")
    api_key = (
        str(getattr(config, "llm_api_key", "") or "").strip()
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or "sk-dev"
    )
    try:
        timeout_seconds = float(getattr(config, "voice_timeout", None) or 30)
    except (TypeError, ValueError):
        timeout_seconds = 30.0

    async def _run() -> str | None:
        file = await bot.get_file(voice.file_id)
        data = io.BytesIO()
        await bot.download_file(file.file_path, data)  # type: ignore[arg-type]
        data.seek(0)
        data.name = "voice.ogg"  # type: ignore[attr-defined]

        # Direct official OpenAI transcription (#3240 keeps this strategy).
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        transcript = await client.audio.transcriptions.create(
            model=stt_model,
            file=data,
            language=voice_language,
        )
        return transcript.text or None  # type: ignore[no-any-return]

    try:
        return await asyncio.wait_for(_run(), timeout=timeout_seconds)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "Voice transcription failed (download/provider/timeout); "
            "falling back to typed input",
            exc_info=True,
        )
        return None


