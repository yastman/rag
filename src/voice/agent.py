"""LiveKit Voice Agent — outbound calls with RAG Q&A."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobProcess,
    RunContext,
    cli,
    function_tool,
)
from livekit.plugins import elevenlabs, openai, silero

from src.voice.schemas import CallStatus
from src.voice.transcript_store import TranscriptStore


load_dotenv()
logger = logging.getLogger(__name__)

RAG_API_URL = os.getenv("RAG_API_URL", "http://rag-api:8080")
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("VOICE_DATABASE_URL", "")
_transcript_store: TranscriptStore | None = None
_http_client: httpx.AsyncClient | None = None
_active_jobs = 0
_jobs_lock: asyncio.Lock | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a shared httpx client with connection pooling."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _http_client


async def _close_http_client() -> None:
    """Close the shared httpx client (called on server shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def _get_jobs_lock() -> asyncio.Lock:
    """Lazy-init lock for shared job counters."""
    global _jobs_lock
    if _jobs_lock is None:
        _jobs_lock = asyncio.Lock()
    return _jobs_lock


async def _mark_job_started() -> None:
    """Increment active job counter for this process."""
    global _active_jobs
    async with _get_jobs_lock():
        _active_jobs += 1


async def _mark_job_finished() -> None:
    """Decrement active job counter and close shared HTTP client when idle."""
    global _active_jobs
    should_close = False
    async with _get_jobs_lock():
        _active_jobs = max(0, _active_jobs - 1)
        should_close = _active_jobs == 0
    if should_close:
        await _close_http_client()


async def _get_transcript_store() -> TranscriptStore | None:
    """Lazy-init transcript store; disabled when DATABASE_URL is missing."""
    global _transcript_store
    if not DATABASE_URL:
        return None
    if _transcript_store is None:
        _transcript_store = TranscriptStore(database_url=DATABASE_URL)
        await _transcript_store.initialize()
    return _transcript_store


def _setup_langfuse() -> None:
    """Configure Langfuse tracing via OpenTelemetry."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "")

    if not public_key or not secret_key or not host:
        logger.info("Langfuse not configured, skipping OTEL setup")
        return

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
        exporter = OTLPSpanExporter(
            endpoint=f"{host.rstrip('/')}/api/public/otel",
            headers={"Authorization": f"Basic {auth}"},
        )
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))

        # Try livekit's telemetry helper, fall back to global OTEL
        try:
            from livekit.agents.telemetry import set_tracer_provider

            set_tracer_provider(provider)
        except ImportError:
            from opentelemetry import trace

            trace.set_tracer_provider(provider)

        logger.info("Langfuse OTEL tracing configured")
    except Exception:
        logger.exception("Failed to setup Langfuse OTEL")


class VoiceBot(Agent):
    """Voice bot agent for lead validation and RAG Q&A."""

    def __init__(
        self,
        call_id: str = "",
        lead_data: dict | None = None,
        transcript_store: TranscriptStore | None = None,
        langfuse_trace_id: str | None = None,
    ) -> None:
        lead_desc = ""
        if lead_data:
            lead_desc = f"\n\nДанные заявки клиента:\n{json.dumps(lead_data, ensure_ascii=False)}"

        super().__init__(
            instructions=(
                "Ты бот-ассистент компании по недвижимости. "
                "Тебе звонят клиенты, которые оставили заявку. "
                "Твоя задача:\n"
                "1. Поздороваться и представиться\n"
                "2. Подтвердить данные заявки (имя, интересующий объект)\n"
                "3. Ответить на вопросы клиента, используя search_knowledge_base\n"
                "4. Быть вежливым, кратким, говорить по-русски\n"
                "5. Если клиент хочет закончить разговор — попрощаться\n\n"
                "ВАЖНО: отвечай КОРОТКО (1-2 предложения). "
                "Это телефонный разговор, длинные ответы неуместны."
                f"{lead_desc}"
            ),
        )
        self._call_id = call_id
        self._transcript_store = transcript_store
        self._langfuse_trace_id = langfuse_trace_id

    async def _append_transcript(self, role: str, text: str) -> None:
        """Best-effort transcript persistence that never breaks the call flow."""
        if not self._transcript_store or not self._call_id:
            return
        try:
            await self._transcript_store.append_transcript(
                call_id=self._call_id,
                role=role,
                text=text,
                timestamp_ms=int(time.time() * 1000),
            )
        except Exception:
            logger.warning("Failed to append transcript entry (role=%s)", role, exc_info=True)

    @function_tool()
    async def search_knowledge_base(self, context: RunContext, query: str) -> str:
        """Search the property knowledge base for relevant information.

        Args:
            query: The search query about properties, prices, locations, etc.
        """
        await self._append_transcript("user", query)
        try:
            client = _get_http_client()
            payload: dict[str, Any] = {
                "query": query,
                "user_id": 0,
                "session_id": f"voice-{self._call_id}",
                "channel": "voice",
            }
            if self._langfuse_trace_id:
                payload["langfuse_trace_id"] = self._langfuse_trace_id
            resp = await client.post(
                f"{RAG_API_URL}/query",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = str(data.get("response", "Информация не найдена."))
            await self._append_transcript("bot", answer)
            return answer
        except Exception:
            logger.exception("RAG API call failed")
            fallback = "Извините, не могу найти информацию сейчас."
            await self._append_transcript("bot", fallback)
            return fallback


def _prewarm_process(proc: JobProcess) -> None:
    """Pre-load Silero VAD during process init, before the ping timer starts.

    Heavy model loading on first job blocks the event loop and prevents pong
    responses, triggering 'process is unresponsive' kills (#218).
    """
    proc.userdata["vad"] = silero.VAD.load()


server = AgentServer(
    initialize_process_timeout=30.0,  # VAD model cold-load can exceed 10s default
    shutdown_process_timeout=30.0,  # graceful cleanup during network disruptions
    num_idle_processes=2,  # prod default=8 is excessive for single voice bot
    setup_fnc=_prewarm_process,
)


@server.rtc_session(agent_name="voice-bot")
async def entrypoint(ctx: agents.JobContext):
    """Entry point for voice bot agent."""
    await _mark_job_started()
    # Parse call metadata
    metadata: dict = {}
    if ctx.job.metadata:
        with contextlib.suppress(json.JSONDecodeError):
            metadata = json.loads(ctx.job.metadata)

    call_id = metadata.get("call_id", "")
    lead_data = metadata.get("lead_data", {})
    if not isinstance(lead_data, dict):
        lead_data = {}
    phone = str(metadata.get("phone", "")).strip()
    callback_chat_id = metadata.get("callback_chat_id")
    langfuse_trace_id = metadata.get("langfuse_trace_id")

    store = await _get_transcript_store()
    if store is not None and phone:
        try:
            call_id = await store.create_call(
                phone=phone,
                lead_data=lead_data,
                callback_chat_id=callback_chat_id,
                call_id=call_id or None,
            )
            await store.update_status(call_id, CallStatus.ANSWERED)
        except Exception:
            logger.exception("Failed to initialize transcript row for call_id=%s", call_id)

    # Create agent session with ElevenLabs STT/TTS
    session: AgentSession = AgentSession(
        stt=elevenlabs.STT(model_id="scribe_v2_realtime"),
        llm=openai.LLM(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("LLM_BASE_URL", "http://litellm:4000"),
            api_key=os.getenv("LLM_API_KEY", ""),
        ),
        tts=elevenlabs.TTS(
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
            model="eleven_turbo_v2_5",
        ),
        vad=ctx.proc.userdata.get("vad") or silero.VAD.load(),
    )

    call_start = time.monotonic()

    agent = VoiceBot(
        call_id=call_id,
        lead_data=lead_data,
        transcript_store=store,
        langfuse_trace_id=langfuse_trace_id,
    )

    # Register cleanup callback to finalize the call when the session ends
    async def _finalize() -> None:
        try:
            if store and call_id:
                duration_sec = int(time.monotonic() - call_start)
                await store.finalize_call(
                    call_id=call_id,
                    duration_sec=duration_sec,
                    langfuse_trace_id=langfuse_trace_id,
                )
                logger.info("Call %s finalized: duration=%ds", call_id, duration_sec)
        except Exception:
            logger.exception("Failed to finalize call %s", call_id)
        finally:
            await _mark_job_finished()

    ctx.add_shutdown_callback(_finalize)

    await session.start(room=ctx.room, agent=agent)

    # Start conversation with greeting
    await session.generate_reply(
        instructions="Поздоровайся с клиентом и спроси, актуальна ли его заявка."
    )


# Setup Langfuse before starting
_setup_langfuse()

if __name__ == "__main__":
    cli.run_app(server)
