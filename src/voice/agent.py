"""LiveKit Voice Agent — outbound calls with RAG Q&A."""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, cli, function_tool
from livekit.plugins import elevenlabs, openai, silero


load_dotenv()
logger = logging.getLogger(__name__)

RAG_API_URL = os.getenv("RAG_API_URL", "http://rag-api:8080")


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

    def __init__(self, call_id: str = "", lead_data: dict | None = None) -> None:
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

    @function_tool()
    async def search_knowledge_base(self, context: RunContext, query: str) -> str:
        """Search the property knowledge base for relevant information.

        Args:
            query: The search query about properties, prices, locations, etc.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{RAG_API_URL}/query",
                    json={
                        "query": query,
                        "user_id": 0,
                        "session_id": f"voice-{self._call_id}",
                        "channel": "voice",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return str(data.get("response", "Информация не найдена."))
        except Exception:
            logger.exception("RAG API call failed")
            return "Извините, не могу найти информацию сейчас."


server = AgentServer()


@server.rtc_session(agent_name="voice-bot")
async def entrypoint(ctx: agents.JobContext):
    """Entry point for voice bot agent."""
    # Parse call metadata
    metadata: dict = {}
    if ctx.job.metadata:
        with contextlib.suppress(json.JSONDecodeError):
            metadata = json.loads(ctx.job.metadata)

    call_id = metadata.get("call_id", "")
    lead_data = metadata.get("lead_data", {})

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
        vad=silero.VAD.load(),
    )

    agent = VoiceBot(call_id=call_id, lead_data=lead_data)
    await session.start(room=ctx.room, agent=agent)

    # Start conversation with greeting
    await session.generate_reply(
        instructions="Поздоровайся с клиентом и спроси, актуальна ли его заявка."
    )


# Setup Langfuse before starting
_setup_langfuse()

if __name__ == "__main__":
    cli.run_app(server)
