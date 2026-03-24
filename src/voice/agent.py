"""LiveKit Voice Agent — outbound calls with RAG Q&A."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import functools
import json
import logging
import os
import time
from types import SimpleNamespace
from typing import Any, cast

import httpx
from dotenv import load_dotenv

from src.voice.observability import trace_voice_session, update_voice_trace, voice_session_id
from src.voice.rag_api_client import RagApiClient, RagApiClientError, RagQueryRequest
from src.voice.schemas import CallStatus
from src.voice.transcript_store import TranscriptStore


_LIVEKIT_IMPORT_ERROR: Exception | None = None
agents: Any
Agent: Any
AgentServer: Any
AgentSession: Any
JobProcess: Any
RunContext: Any
cli: Any
function_tool: Any
elevenlabs: Any
openai: Any
silero: Any

try:
    from livekit import agents as _livekit_agents
    from livekit.agents import (
        Agent as _LivekitAgent,
    )
    from livekit.agents import (
        AgentServer as _LivekitAgentServer,
    )
    from livekit.agents import (
        AgentSession as _LivekitAgentSession,
    )
    from livekit.agents import (
        JobProcess as _LivekitJobProcess,
    )
    from livekit.agents import (
        RunContext as _LivekitRunContext,
    )
    from livekit.agents import (
        cli as _livekit_cli,
    )
    from livekit.agents import (
        function_tool as _livekit_function_tool,
    )
    from livekit.plugins import (
        elevenlabs as _livekit_elevenlabs,
    )
    from livekit.plugins import (
        openai as _livekit_openai,
    )
    from livekit.plugins import (
        silero as _livekit_silero,
    )
except Exception as exc:  # pragma: no cover - exercised via tests/import fallback
    _LIVEKIT_IMPORT_ERROR = exc

    def _raise_livekit_runtime_unavailable() -> None:
        raise RuntimeError(
            "LiveKit runtime is unavailable in this environment"
        ) from _LIVEKIT_IMPORT_ERROR

    class _AgentStub:
        def __init__(self, *, instructions: str = "") -> None:
            self.instructions = instructions

    class _AgentServerStub:
        def __init__(
            self,
            *,
            initialize_process_timeout: float,
            shutdown_process_timeout: float,
            num_idle_processes: int,
            setup_fnc,
        ) -> None:
            self._initialize_process_timeout = initialize_process_timeout
            self._shutdown_process_timeout = shutdown_process_timeout
            self._num_idle_processes = num_idle_processes
            self.setup_fnc = setup_fnc

        def rtc_session(self, *, agent_name: str):
            def decorator(fn):
                self._agent_name = agent_name
                self._entrypoint = fn
                return fn

            return decorator

    class _AgentSessionStub:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def start(self, *args, **kwargs) -> None:
            _raise_livekit_runtime_unavailable()

        async def generate_reply(self, *args, **kwargs) -> None:
            _raise_livekit_runtime_unavailable()

    class _JobProcessStub:
        def __init__(self) -> None:
            self.userdata: dict = {}

    class _RunContextStub:
        pass

    class _CLI:
        @staticmethod
        def run_app(*_args, **_kwargs) -> None:
            _raise_livekit_runtime_unavailable()

    def function_tool():
        def decorator(fn):
            @functools.wraps(fn)
            async def wrapped(*args, **kwargs):
                return await fn(*args, **kwargs)

            return wrapped

        return decorator

    class _VAD:
        @staticmethod
        def load():
            _raise_livekit_runtime_unavailable()

    class _Factory:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    agents = cast(Any, SimpleNamespace(JobContext=object))
    Agent = cast(Any, _AgentStub)
    AgentServer = cast(Any, _AgentServerStub)
    AgentSession = cast(Any, _AgentSessionStub)
    JobProcess = cast(Any, _JobProcessStub)
    RunContext = cast(Any, _RunContextStub)
    cli = cast(Any, _CLI())
    function_tool = cast(Any, function_tool)
    silero = cast(Any, SimpleNamespace(VAD=_VAD))
    elevenlabs = cast(Any, SimpleNamespace(STT=_Factory, TTS=_Factory))
    openai = cast(Any, SimpleNamespace(LLM=_Factory))
else:
    agents = _livekit_agents
    Agent = _LivekitAgent
    AgentServer = _LivekitAgentServer
    AgentSession = _LivekitAgentSession
    JobProcess = _LivekitJobProcess
    RunContext = _LivekitRunContext
    cli = _livekit_cli
    function_tool = _livekit_function_tool
    elevenlabs = _livekit_elevenlabs
    openai = _livekit_openai
    silero = _livekit_silero


load_dotenv()
logger = logging.getLogger(__name__)

if _LIVEKIT_IMPORT_ERROR is not None:
    logger.warning("LiveKit import failed; voice runtime entrypoint is unavailable", exc_info=True)

RAG_API_URL = os.getenv("RAG_API_URL", "http://rag-api:8080")
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("VOICE_DATABASE_URL", "")
_transcript_store: TranscriptStore | None = None
_rag_api_client: RagApiClient | None = None
_active_jobs = 0
_jobs_lock: asyncio.Lock | None = None


def _get_rag_api_client() -> RagApiClient:
    """Return shared typed RAG API client."""
    global _rag_api_client
    if _rag_api_client is None:
        _rag_api_client = RagApiClient(base_url=RAG_API_URL)
    return _rag_api_client


def _get_http_client() -> httpx.AsyncClient:
    """Compatibility wrapper for tests that assert shared HTTP client behavior."""
    return _get_rag_api_client().client


async def _close_http_client() -> None:
    """Close the shared typed RAG API client (called on server shutdown)."""
    global _rag_api_client
    if _rag_api_client is not None:
        await _rag_api_client.close()
        _rag_api_client = None


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
        self._session_id = voice_session_id(call_id)
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
            request = RagQueryRequest(
                query=query,
                session_id=self._session_id,
                langfuse_trace_id=self._langfuse_trace_id,
            )
            with contextlib.suppress(Exception):
                update_voice_trace(
                    call_id=self._call_id,
                    status="tool_call",
                    session_id=self._session_id,
                    langfuse_trace_id=self._langfuse_trace_id,
                )
            answer = await _get_rag_api_client().search_knowledge_base(request)
            await self._append_transcript("bot", answer)
            return answer
        except RagApiClientError:
            logger.exception("RAG API call failed")
            fallback = "Извините, не могу найти информацию сейчас."
            await self._append_transcript("bot", fallback)
            return fallback
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
    if _LIVEKIT_IMPORT_ERROR is not None:
        raise RuntimeError(
            "LiveKit runtime is unavailable in this environment"
        ) from _LIVEKIT_IMPORT_ERROR
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
    session_id = voice_session_id(call_id)

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
            session_id = voice_session_id(call_id)
        except Exception:
            logger.exception("Failed to initialize transcript row for call_id=%s", call_id)
            await trace_voice_session(
                call_id=call_id,
                status="error",
                session_id=session_id,
                error="transcript_init_failed",
                langfuse_trace_id=langfuse_trace_id,
            )

    await trace_voice_session(
        call_id=call_id,
        status="answered",
        session_id=session_id,
        langfuse_trace_id=langfuse_trace_id,
    )

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
                await trace_voice_session(
                    call_id=call_id,
                    status="finalized",
                    duration_sec=duration_sec,
                    session_id=session_id,
                    langfuse_trace_id=langfuse_trace_id,
                )
                logger.info("Call %s finalized: duration=%ds", call_id, duration_sec)
        except Exception:
            logger.exception("Failed to finalize call %s", call_id)
            await trace_voice_session(
                call_id=call_id,
                status="error",
                session_id=session_id,
                error="finalize_failed",
                langfuse_trace_id=langfuse_trace_id,
            )
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
    if _LIVEKIT_IMPORT_ERROR is not None:
        raise RuntimeError(
            "LiveKit runtime is unavailable in this environment"
        ) from _LIVEKIT_IMPORT_ERROR
    cli.run_app(server)
