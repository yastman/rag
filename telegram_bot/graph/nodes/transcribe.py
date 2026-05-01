"""transcribe_node — voice-to-text via Whisper API (LiteLLM proxy).

Receives voice audio bytes from RAGState, calls OpenAI Whisper API
through the existing AsyncOpenAI client (LiteLLM proxy), returns
transcribed text that feeds into the classify → ... pipeline.
"""

from __future__ import annotations

import html
import io
import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


def make_transcribe_node(
    *,
    llm: Any,
    voice_language: str = "ru",
    stt_model: str = "whisper",
    show_transcription: bool = True,
    message: Any | None = None,
):
    """Create transcribe_node with injected dependencies.

    Args:
        llm: AsyncOpenAI client (same as generate_node uses).
        voice_language: ISO language code for Whisper hint.
        stt_model: Model name in LiteLLM config.
        show_transcription: Send transcription preview to user.
        message: aiogram Message for sending preview.
    """

    @observe(name="transcribe", capture_input=False, capture_output=False)
    async def transcribe_node(state: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()

        voice_audio = state["voice_audio"]
        if voice_audio is None:
            raise ValueError("voice_audio is None — transcribe_node requires audio data")

        # Curated span input (no raw bytes!)
        lf = get_client()
        lf.update_current_span(
            input={
                "audio_size_bytes": len(voice_audio),
                "voice_language": voice_language,
                "stt_model": stt_model,
                "voice_duration_s": state.get("voice_duration_s"),
            }
        )

        buf = io.BytesIO(voice_audio)
        buf.name = "voice.ogg"

        # Best-effort Langfuse generation observation — must not break STT
        import contextlib

        gen_obs_ctx = None
        gen_obs = None
        with contextlib.suppress(Exception):
            gen_obs_ctx = lf.start_as_current_observation(
                name="transcribe-audio",
                as_type="generation",
                model=stt_model,
            )
            gen_obs = gen_obs_ctx.__enter__()

        try:
            transcript = await llm.audio.transcriptions.create(
                model=stt_model,
                file=buf,
                language=voice_language,
            )
            text = transcript.text.strip()
            if gen_obs is not None:
                with contextlib.suppress(Exception):
                    gen_obs.update(output={"text": text[:120]})
        except Exception as exc:
            lf.update_current_span(
                level="ERROR",
                status_message=f"Transcription failed: {str(exc)[:200]}",
            )
            raise
        finally:
            if gen_obs_ctx is not None:
                with contextlib.suppress(Exception):
                    gen_obs_ctx.__exit__(None, None, None)

        stt_duration_ms = (time.perf_counter() - start) * 1000

        if not text:
            raise ValueError("Empty transcription from Whisper API")

        logger.info(
            "Voice transcribed: %.0f ms, %d chars, lang=%s",
            stt_duration_ms,
            len(text),
            voice_language,
        )

        # Curated span output
        lf.update_current_span(
            output={
                "stt_duration_ms": round(stt_duration_ms, 1),
                "text_length": len(text),
                "text_preview": text[:120],
            }
        )

        # Send transcription preview (optional)
        if show_transcription and message is not None:
            try:
                await message.answer(
                    f"\U0001f3a4 <i>{html.escape(text)}</i>",
                    parse_mode="HTML",
                )
            except Exception:
                logger.warning("Failed to send transcription preview", exc_info=True)

        return {
            "stt_text": text,
            "stt_duration_ms": stt_duration_ms,
            "query": text,
            "messages": [{"role": "user", "content": text}],
            "voice_audio": None,  # Free memory — audio no longer needed
        }

    return transcribe_node
