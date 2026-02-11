# Voice Bot Implementation Plan (LiveKit Agents)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add outbound voice calling to the RAG chatbot via LiveKit Agents + lifecell SIP trunk, enabling Telegram-triggered calls that validate leads and answer questions using the existing RAG pipeline.

**Architecture:** LiveKit Server with native SIP handles telephony. A Python LiveKit Agent uses ElevenLabs STT/TTS plugins and calls the RAG API via @function_tool. A new FastAPI RAG API exposes the existing LangGraph pipeline as HTTP endpoint. Call transcripts stored in PostgreSQL. Langfuse tracing via OpenTelemetry.

**Tech Stack:** LiveKit Server + SIP, livekit-agents ~1.3, ElevenLabs (Scribe v2 RT + Flash v2.5), FastAPI, asyncpg, LangGraph, Langfuse v3 via OTEL

**Design doc:** `docs/plans/2026-02-11-voice-bot-design.md`

---

## Task 1: Dependencies and environment setup

Устанавливаем все новые зависимости и обновляем .env.example.

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

**Step 1: Add dependencies**

```bash
# RAG API deps
uv add fastapi uvicorn asyncpg

# LiveKit Agent deps (отдельная группа, не в основной bot)
uv add "livekit-agents[silero,turn-detector]~=1.3" \
       "livekit-plugins-elevenlabs~=1.0" \
       "livekit-plugins-openai~=1.0" \
       "livekit~=0.20" \
       "opentelemetry-sdk" \
       "opentelemetry-exporter-otlp-proto-http"
```

Run: `uv sync`
Expected: Lock file updated, no errors

**Step 2: Update .env.example**

Добавить в конец файла `.env.example`:
```bash
# === Voice Bot (LiveKit Agents) ===
# ElevenLabs (STT + TTS)
ELEVENLABS_API_KEY=

# LiveKit Server
LIVEKIT_URL=ws://livekit-server:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

# lifecell SIP trunk
LIFECELL_SIP_USER=
LIFECELL_SIP_PASS=

# RAG API
RAG_API_URL=http://rag-api:8080

# PostgreSQL for voice transcripts
VOICE_DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
```

**Step 3: Commit**

```bash
git add pyproject.toml uv.lock .env.example
git commit -m "chore: add LiveKit Agents and RAG API dependencies"
```

---

## Task 2: RAG API — FastAPI wrapper around LangGraph

Выносим LangGraph pipeline в отдельный HTTP API. Voice agent и (в будущем) Telegram бот вызывают его.

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/main.py`
- Create: `src/api/schemas.py`
- Create: `src/api/Dockerfile`
- Create: `tests/unit/api/__init__.py`
- Create: `tests/unit/api/test_rag_api.py`

**Step 1: Write schemas**

```python
# src/api/schemas.py
from pydantic import BaseModel


class QueryRequest(BaseModel):
    query: str
    user_id: int = 0
    session_id: str = ""
    channel: str = "api"  # "telegram" | "voice" | "api"


class QueryResponse(BaseModel):
    response: str
    query_type: str
    cache_hit: bool
    search_results_count: int
    latency_ms: float
    langfuse_trace_id: str | None = None
```

**Step 2: Write failing test**

```python
# tests/unit/api/__init__.py
# (empty)

# tests/unit/api/test_rag_api.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_graph_result():
    return {
        "response": "Test answer",
        "query_type": "GENERAL",
        "cache_hit": False,
        "search_results_count": 3,
    }


@pytest.mark.asyncio
async def test_query_request_schema():
    from src.api.schemas import QueryRequest

    req = QueryRequest(query="тест", user_id=123, channel="voice")
    assert req.query == "тест"
    assert req.channel == "voice"


@pytest.mark.asyncio
async def test_query_response_schema():
    from src.api.schemas import QueryResponse

    resp = QueryResponse(
        response="answer",
        query_type="GENERAL",
        cache_hit=False,
        search_results_count=3,
        latency_ms=100.0,
    )
    assert resp.response == "answer"
```

Run: `uv run pytest tests/unit/api/test_rag_api.py -v`
Expected: PASS (schema tests)

**Step 3: Implement RAG API**

```python
# src/api/__init__.py
# (empty)

# src/api/main.py
"""RAG API — FastAPI wrapper around LangGraph pipeline."""
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from src.api.schemas import QueryRequest, QueryResponse
from telegram_bot.graph.config import GraphConfig
from telegram_bot.graph.graph import build_graph
from telegram_bot.graph.state import make_initial_state
from telegram_bot.observability import get_client, observe, propagate_attributes

logger = logging.getLogger(__name__)

_graph_config: GraphConfig | None = None
_cache: Any = None
_embeddings: Any = None
_sparse: Any = None
_qdrant: Any = None
_reranker: Any = None
_llm: Any = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph_config, _cache, _embeddings, _sparse, _qdrant, _reranker, _llm

    _graph_config = GraphConfig.from_env()

    from telegram_bot.integrations.cache import CacheLayerManager
    from telegram_bot.integrations.embeddings import (
        BGEM3HybridEmbeddings,
        BGEM3SparseEmbeddings,
    )
    from telegram_bot.services.qdrant import QdrantService

    _cache = CacheLayerManager(redis_url=_graph_config.redis_url)
    await _cache.initialize()
    _embeddings = BGEM3HybridEmbeddings(base_url=_graph_config.bge_m3_url)
    _sparse = BGEM3SparseEmbeddings(base_url=_graph_config.bge_m3_url)
    _qdrant = QdrantService(
        url=_graph_config.qdrant_url,
        collection_name=_graph_config.qdrant_collection,
    )
    _llm = _graph_config.create_llm()

    if os.getenv("RERANK_PROVIDER") == "colbert":
        from telegram_bot.services.colbert_reranker import ColbertRerankerService

        _reranker = ColbertRerankerService(base_url=_graph_config.bge_m3_url)

    logger.info("RAG API services initialized")
    yield

    await _cache.close()
    await _qdrant.close()
    if hasattr(_embeddings, "aclose"):
        await _embeddings.aclose()
    if hasattr(_sparse, "aclose"):
        await _sparse.aclose()
    logger.info("RAG API services cleaned up")


app = FastAPI(title="RAG API", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
@observe(name="rag-api-query")
async def query(req: QueryRequest) -> QueryResponse:
    start = time.perf_counter()

    state = make_initial_state(
        user_id=req.user_id,
        session_id=req.session_id or f"{req.channel}-{req.user_id}",
        query=req.query,
    )

    with propagate_attributes(
        session_id=state["session_id"],
        user_id=str(req.user_id),
        tags=[req.channel, "rag"],
    ):
        graph = build_graph(
            cache=_cache,
            embeddings=_embeddings,
            sparse_embeddings=_sparse,
            qdrant=_qdrant,
            reranker=_reranker,
            llm=_llm,
            message=None,  # Non-streaming
        )
        result = await graph.ainvoke(state)
        elapsed_ms = (time.perf_counter() - start) * 1000

        lf = get_client()
        lf.update_current_trace(
            input={"query": req.query, "channel": req.channel},
            output={"response": result.get("response", "")},
        )

        return QueryResponse(
            response=result.get("response", ""),
            query_type=result.get("query_type", ""),
            cache_hit=result.get("cache_hit", False),
            search_results_count=result.get("search_results_count", 0),
            latency_ms=elapsed_ms,
        )
```

**Step 4: Write Dockerfile**

```dockerfile
# src/api/Dockerfile
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY telegram_bot/ telegram_bot/
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/telegram_bot /app/telegram_bot
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/api/test_rag_api.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/api/ tests/unit/api/
git commit -m "feat(api): add FastAPI RAG API endpoint for multi-channel access"
```

---

## Task 3: LiveKit Server + SIP trunk Docker setup

Docker Compose для LiveKit Server, SIP server и конфигурация lifecell trunk.

**Files:**
- Create: `docker/livekit/livekit.yaml`
- Create: `src/voice/__init__.py`
- Create: `src/voice/sip_setup.py`
- Modify: `docker-compose.dev.yml` (add livekit-server, livekit-sip, rag-api, voice-agent services)

**Step 1: Write LiveKit config**

```yaml
# docker/livekit/livekit.yaml
port: 7880
log_level: info
rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 50100
  use_external_ip: true
keys:
  devkey: secret
```

**Step 2: Write SIP trunk setup script**

```python
# src/voice/__init__.py
# (empty)

# src/voice/sip_setup.py
"""One-time SIP trunk provisioning for lifecell Ukraine."""
import asyncio
import os

from livekit import api
from livekit.protocol.sip import CreateSIPOutboundTrunkRequest, SIPOutboundTrunkInfo


async def setup_lifecell_trunk() -> str:
    """Create lifecell outbound SIP trunk. Returns trunk ID."""
    lk = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL", "http://localhost:7880"),
        api_key=os.getenv("LIVEKIT_API_KEY", "devkey"),
        api_secret=os.getenv("LIVEKIT_API_SECRET", "secret"),
    )

    sip_user = os.getenv("LIFECELL_SIP_USER", "")
    sip_pass = os.getenv("LIFECELL_SIP_PASS", "")
    sip_number = os.getenv("LIFECELL_SIP_NUMBER", "")

    if not sip_user or not sip_pass:
        raise ValueError("LIFECELL_SIP_USER and LIFECELL_SIP_PASS required")

    trunk = SIPOutboundTrunkInfo(
        name="lifecell-ukraine-outbound",
        address="csbc.lifecell.ua:5061",
        numbers=[sip_number] if sip_number else [],
        auth_username=sip_user,
        auth_password=sip_pass,
    )

    result = await lk.sip.create_sip_outbound_trunk(
        CreateSIPOutboundTrunkRequest(trunk=trunk)
    )
    trunk_id = result.sip_trunk_id
    print(f"Created lifecell trunk: {trunk_id}")

    await lk.aclose()
    return trunk_id


if __name__ == "__main__":
    asyncio.run(setup_lifecell_trunk())
```

**Step 3: Add services to docker-compose.dev.yml**

Добавить в `docker-compose.dev.yml` четыре новых сервиса (профиль `voice`):

```yaml
  # --- Voice profile ---
  rag-api:
    build:
      context: .
      dockerfile: src/api/Dockerfile
    container_name: dev-rag-api
    profiles: ["voice", "full"]
    restart: unless-stopped
    logging: *default-logging
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      REDIS_URL: redis://redis:6379
      QDRANT_URL: http://qdrant:6333
      QDRANT_COLLECTION: ${QDRANT_COLLECTION:-gdrive_documents_bge}
      BGE_M3_URL: http://bge-m3:8000
      LLM_API_KEY: ${LITELLM_MASTER_KEY:?LITELLM_MASTER_KEY is required}
      LLM_BASE_URL: http://litellm:4000
      LLM_MODEL: gpt-4o-mini
      RERANK_PROVIDER: colbert
      LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-}
      LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-}
      LANGFUSE_HOST: http://langfuse:3000
    depends_on:
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      bge-m3:
        condition: service_healthy
      litellm:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=5)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 512M

  livekit-server:
    image: livekit/livekit-server:v1.8
    container_name: dev-livekit
    profiles: ["voice", "full"]
    restart: unless-stopped
    ports:
      - "7880:7880"
      - "7881:7881"
      - "50000-50100:50000-50100/udp"
    volumes:
      - ./docker/livekit/livekit.yaml:/etc/livekit.yaml:ro
    command: --config /etc/livekit.yaml --dev
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:7880 || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 256M

  livekit-sip:
    image: livekit/sip:latest
    container_name: dev-livekit-sip
    profiles: ["voice", "full"]
    restart: unless-stopped
    ports:
      - "5060:5060/udp"
      - "5061:5061/tcp"
      - "10000-10100:10000-10100/udp"
    environment:
      LIVEKIT_API_KEY: devkey
      LIVEKIT_API_SECRET: secret
      LIVEKIT_WS_URL: ws://livekit-server:7880
      SIP_PORT: "5060"
      RTP_PORT_LOW: "10000"
      RTP_PORT_HIGH: "10100"
    depends_on:
      livekit-server:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 256M

  voice-agent:
    build:
      context: .
      dockerfile: src/voice/Dockerfile
    container_name: dev-voice-agent
    profiles: ["voice", "full"]
    restart: unless-stopped
    logging: *default-logging
    environment:
      LIVEKIT_URL: ws://livekit-server:7880
      LIVEKIT_API_KEY: devkey
      LIVEKIT_API_SECRET: secret
      ELEVEN_API_KEY: ${ELEVENLABS_API_KEY:-}
      RAG_API_URL: http://rag-api:8080
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/postgres
      LANGFUSE_PUBLIC_KEY: ${LANGFUSE_PUBLIC_KEY:-}
      LANGFUSE_SECRET_KEY: ${LANGFUSE_SECRET_KEY:-}
      LANGFUSE_HOST: http://langfuse:3000
    depends_on:
      livekit-server:
        condition: service_healthy
      rag-api:
        condition: service_healthy
      postgres:
        condition: service_healthy
    deploy:
      resources:
        limits:
          memory: 1G
```

**Step 4: Verify LiveKit starts**

Run: `docker compose -f docker-compose.dev.yml --profile core --profile voice up -d livekit-server`
Run: `docker logs dev-livekit --tail 10`
Expected: `LiveKit server started`

**Step 5: Commit**

```bash
git add docker/livekit/ src/voice/__init__.py src/voice/sip_setup.py docker-compose.dev.yml
git commit -m "feat(voice): add LiveKit Server + SIP Docker setup and trunk provisioning"
```

---

## Task 4: PostgreSQL schema for call transcripts

**Files:**
- Create: `docker/postgres/init/02-voice-schema.sql`
- Create: `src/voice/schemas.py`
- Create: `src/voice/transcript_store.py`
- Create: `tests/unit/voice/__init__.py`
- Create: `tests/unit/voice/test_transcript_store.py`

**Step 1: Write SQL migration**

```sql
-- docker/postgres/init/02-voice-schema.sql
CREATE TABLE IF NOT EXISTS call_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    lead_data JSONB DEFAULT '{}',
    transcript JSONB DEFAULT '[]',
    langfuse_trace_id VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'initiated',
    duration_sec INTEGER DEFAULT 0,
    validation_result JSONB,
    callback_chat_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_call_transcripts_phone ON call_transcripts(phone);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_status ON call_transcripts(status);
CREATE INDEX IF NOT EXISTS idx_call_transcripts_created ON call_transcripts(created_at DESC);
```

**Step 2: Write Pydantic schemas**

```python
# src/voice/schemas.py
"""Voice service schemas."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CallStatus(str, Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"


class CallRequest(BaseModel):
    phone: str
    lead_data: dict = Field(default_factory=dict)
    callback_chat_id: int | None = None


class CallResponse(BaseModel):
    call_id: str
    status: CallStatus


class TranscriptEntry(BaseModel):
    role: str  # "user" | "bot"
    text: str
    timestamp_ms: int
```

**Step 3: Write transcript store**

```python
# src/voice/transcript_store.py
"""PostgreSQL transcript storage for voice calls."""
from __future__ import annotations

import json
import logging
import uuid

import asyncpg

from src.voice.schemas import CallStatus

logger = logging.getLogger(__name__)


class TranscriptStore:
    """Stores call transcripts in PostgreSQL."""

    def __init__(self, database_url: str):
        self._database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def initialize(self) -> None:
        self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def create_call(
        self,
        phone: str,
        lead_data: dict | None = None,
        callback_chat_id: int | None = None,
    ) -> str:
        call_id = str(uuid.uuid4())
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO call_transcripts (id, phone, lead_data, callback_chat_id)
                   VALUES ($1, $2, $3, $4)""",
                uuid.UUID(call_id),
                phone,
                json.dumps(lead_data or {}),
                callback_chat_id,
            )
        return call_id

    async def update_status(self, call_id: str, status: CallStatus) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE call_transcripts SET status = $1, updated_at = NOW()
                   WHERE id = $2""",
                status.value,
                uuid.UUID(call_id),
            )

    async def append_transcript(
        self, call_id: str, role: str, text: str, timestamp_ms: int
    ) -> None:
        entry = {"role": role, "text": text, "timestamp_ms": timestamp_ms}
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE call_transcripts
                   SET transcript = transcript || $1::jsonb, updated_at = NOW()
                   WHERE id = $2""",
                json.dumps([entry]),
                uuid.UUID(call_id),
            )

    async def finalize_call(
        self,
        call_id: str,
        duration_sec: int,
        validation_result: dict | None = None,
        langfuse_trace_id: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE call_transcripts
                   SET status = $1, duration_sec = $2,
                       validation_result = $3, langfuse_trace_id = $4,
                       updated_at = NOW()
                   WHERE id = $5""",
                CallStatus.COMPLETED.value,
                duration_sec,
                json.dumps(validation_result) if validation_result else None,
                langfuse_trace_id,
                uuid.UUID(call_id),
            )

    async def get_call(self, call_id: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM call_transcripts WHERE id = $1",
                uuid.UUID(call_id),
            )
            return dict(row) if row else None
```

**Step 4: Write tests**

```python
# tests/unit/voice/__init__.py
# (empty)

# tests/unit/voice/test_transcript_store.py
from src.voice.schemas import CallRequest, CallResponse, CallStatus, TranscriptEntry


def test_call_request_schema():
    req = CallRequest(phone="+380501234567", lead_data={"name": "Test"}, callback_chat_id=123)
    assert req.phone == "+380501234567"
    assert req.lead_data == {"name": "Test"}


def test_call_status_enum():
    assert CallStatus.INITIATED.value == "initiated"
    assert CallStatus.COMPLETED.value == "completed"
    assert CallStatus.NO_ANSWER.value == "no_answer"


def test_transcript_entry():
    entry = TranscriptEntry(role="user", text="Привет", timestamp_ms=1000)
    assert entry.role == "user"
    assert entry.text == "Привет"


def test_call_response():
    resp = CallResponse(call_id="abc-123", status=CallStatus.INITIATED)
    assert resp.status == CallStatus.INITIATED


def test_transcript_store_init():
    from src.voice.transcript_store import TranscriptStore

    store = TranscriptStore(database_url="postgresql://test:test@localhost/test")
    assert store._database_url == "postgresql://test:test@localhost/test"
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/voice/test_transcript_store.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add docker/postgres/init/02-voice-schema.sql src/voice/schemas.py src/voice/transcript_store.py tests/unit/voice/
git commit -m "feat(voice): add call transcript PostgreSQL schema and store"
```

---

## Task 5: Voice Agent — LiveKit Agent with ElevenLabs STT/TTS

Основной voice agent: LiveKit Agent class с ElevenLabs STT/TTS и RAG @function_tool.

**Files:**
- Create: `src/voice/agent.py`
- Create: `src/voice/Dockerfile`
- Create: `tests/unit/voice/test_voice_agent.py`

**Step 1: Write voice agent**

```python
# src/voice/agent.py
"""LiveKit Voice Agent — outbound calls with RAG Q&A."""
from __future__ import annotations

import base64
import json
import logging
import os
import time

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, function_tool
from livekit.plugins import elevenlabs, openai, silero

from src.voice.schemas import CallStatus
from src.voice.transcript_store import TranscriptStore

load_dotenv()
logger = logging.getLogger(__name__)

RAG_API_URL = os.getenv("RAG_API_URL", "http://rag-api:8080")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Global transcript store
_transcript_store: TranscriptStore | None = None


def _setup_langfuse() -> None:
    """Configure Langfuse tracing via OpenTelemetry."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "")

    if not public_key or not secret_key or not host:
        logger.info("Langfuse not configured, skipping OTEL setup")
        return

    try:
        from livekit.agents.telemetry import set_tracer_provider
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
        set_tracer_provider(provider)
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
        self._turn_count = 0
        self._call_start = time.perf_counter()

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
                return data.get("response", "Информация не найдена.")
        except Exception:
            logger.exception("RAG API call failed")
            return "Извините, не могу найти информацию сейчас."


server = AgentServer()


@server.rtc_session(agent_name="voice-bot")
async def entrypoint(ctx: agents.JobContext):
    """Entry point for voice bot agent."""
    global _transcript_store

    # Initialize transcript store once
    if _transcript_store is None and DATABASE_URL:
        _transcript_store = TranscriptStore(database_url=DATABASE_URL)
        await _transcript_store.initialize()

    # Parse call metadata
    metadata = {}
    if ctx.job.metadata:
        try:
            metadata = json.loads(ctx.job.metadata)
        except json.JSONDecodeError:
            pass

    call_id = metadata.get("call_id", "")
    lead_data = metadata.get("lead_data", {})

    # Create agent session with ElevenLabs STT/TTS
    session = AgentSession(
        stt=elevenlabs.STT(model="scribe_v2_realtime"),
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
    agents.cli.run_app(server)
```

**Step 2: Write Dockerfile**

```dockerfile
# src/voice/Dockerfile
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY telegram_bot/ telegram_bot/
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/telegram_bot /app/telegram_bot
ENV PATH="/app/.venv/bin:$PATH"

# Download VAD/turn-detector models
RUN python -c "from livekit.plugins.silero import VAD; VAD.load()" 2>/dev/null || true

CMD ["python", "-m", "src.voice.agent", "start"]
```

**Step 3: Write tests**

```python
# tests/unit/voice/test_voice_agent.py
"""Unit tests for voice agent."""
import json
import pytest


def test_voice_bot_init():
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="test-123", lead_data={"name": "Test"})
    assert agent._call_id == "test-123"
    assert "Test" in agent.instructions


def test_voice_bot_instructions_without_lead_data():
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="test-456")
    assert "бот-ассистент" in agent.instructions
    assert "заявка" not in agent.instructions.split("Данные заявки")[-1] if "Данные заявки" in agent.instructions else True


def test_voice_bot_has_function_tool():
    from src.voice.agent import VoiceBot

    agent = VoiceBot()
    # Check that search_knowledge_base is a method
    assert hasattr(agent, "search_knowledge_base")
    assert callable(agent.search_knowledge_base)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/voice/test_voice_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/voice/agent.py src/voice/Dockerfile tests/unit/voice/test_voice_agent.py
git commit -m "feat(voice): add LiveKit voice agent with ElevenLabs STT/TTS and RAG function tool"
```

---

## Task 6: Telegram bot — /call command

Добавляем команду `/call` в Telegram бот. Бот вызывает LiveKit API напрямую для создания комнаты, диспатча агента и SIP звонка.

**Files:**
- Modify: `telegram_bot/bot.py` (add cmd_call, import livekit api)
- Modify: `telegram_bot/config.py` (add livekit_url, livekit_api_key, livekit_api_secret, sip_trunk_id)
- Create: `tests/unit/test_cmd_call.py`

**Step 1: Add config fields**

В `telegram_bot/config.py` добавить в `BotConfig`:
```python
# LiveKit (voice calls)
livekit_url: str = Field(default="", validation_alias=AliasChoices("LIVEKIT_URL", "livekit_url"))
livekit_api_key: str = Field(default="", validation_alias=AliasChoices("LIVEKIT_API_KEY", "livekit_api_key"))
livekit_api_secret: str = Field(default="", validation_alias=AliasChoices("LIVEKIT_API_SECRET", "livekit_api_secret"))
sip_trunk_id: str = Field(default="", validation_alias=AliasChoices("SIP_TRUNK_ID", "sip_trunk_id"))
```

**Step 2: Add /call handler to bot.py**

В `_register_handlers()` добавить:
```python
self.dp.message(Command("call"))(self.cmd_call)
```

Новый метод:
```python
async def cmd_call(self, message: Message):
    """Handle /call command — trigger outbound voice call.

    Usage: /call +380501234567 [lead description]
    Admin-only command.
    """
    assert message.from_user is not None
    if not self._is_admin(message.from_user.id):
        await message.answer("Только администраторы могут инициировать звонки.")
        return

    if not self.config.livekit_url or not self.config.sip_trunk_id:
        await message.answer("Voice service не настроен (LIVEKIT_URL, SIP_TRUNK_ID).")
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=2)  # /call +380... description
    if len(parts) < 2:
        await message.answer("Использование: /call +380501234567 [описание заявки]")
        return

    phone = parts[1]
    lead_desc = parts[2] if len(parts) > 2 else ""

    try:
        import uuid
        from livekit import api

        lk = api.LiveKitAPI(
            url=self.config.livekit_url,
            api_key=self.config.livekit_api_key,
            api_secret=self.config.livekit_api_secret,
        )

        room_name = f"voice-call-{uuid.uuid4().hex[:8]}"
        call_id = str(uuid.uuid4())

        # 1. Dispatch voice agent to room
        await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="voice-bot",
                room=room_name,
                metadata=json.dumps({
                    "call_id": call_id,
                    "phone": phone,
                    "lead_data": {
                        "description": lead_desc,
                        "triggered_by": message.from_user.id,
                    },
                    "callback_chat_id": message.chat.id,
                }),
            )
        )

        # 2. Create SIP participant (dials the phone)
        await lk.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=self.config.sip_trunk_id,
                sip_call_to=phone,
                participant_identity=f"phone-{phone}",
                participant_name="Phone User",
                krisp_enabled=True,
                wait_until_answered=True,
            )
        )

        await lk.aclose()
        await message.answer(
            f"Звонок инициирован!\n"
            f"ID: `{call_id}`\n"
            f"Телефон: {phone}\n"
            f"Room: {room_name}",
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.exception("Failed to initiate call")
        await message.answer(f"Ошибка инициации звонка: {e}")
```

Добавить `import json` в начало `bot.py` (если ещё нет).

**Step 3: Write test**

```python
# tests/unit/test_cmd_call.py
"""Tests for /call command."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def bot_config():
    """Create test config."""
    from telegram_bot.config import BotConfig

    return BotConfig(
        telegram_token="test:token",
        admin_ids=[111],
        livekit_url="ws://localhost:7880",
        livekit_api_key="devkey",
        livekit_api_secret="secret",
        sip_trunk_id="ST_test123",
    )


@pytest.fixture
def message():
    msg = MagicMock()
    msg.from_user = MagicMock()
    msg.from_user.id = 111  # admin
    msg.chat = MagicMock()
    msg.chat.id = 999
    msg.answer = AsyncMock()
    return msg


def test_call_requires_admin(bot_config, message):
    """Non-admin users should be rejected."""
    from telegram_bot.bot import PropertyBot

    with patch.object(PropertyBot, "__init__", lambda self, config: None):
        bot = PropertyBot.__new__(PropertyBot)
        bot.config = bot_config
        bot.config.admin_ids = [111]

    message.from_user.id = 999  # not admin
    import asyncio
    asyncio.run(bot.cmd_call(message))
    message.answer.assert_called_once()
    assert "администратор" in message.answer.call_args[0][0].lower()


def test_call_requires_phone(bot_config, message):
    """Command without phone should show usage."""
    from telegram_bot.bot import PropertyBot

    with patch.object(PropertyBot, "__init__", lambda self, config: None):
        bot = PropertyBot.__new__(PropertyBot)
        bot.config = bot_config
        bot.config.admin_ids = [111]

    message.text = "/call"
    import asyncio
    asyncio.run(bot.cmd_call(message))
    message.answer.assert_called_once()
    assert "380" in message.answer.call_args[0][0]
```

**Step 4: Run test**

Run: `uv run pytest tests/unit/test_cmd_call.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/bot.py telegram_bot/config.py tests/unit/test_cmd_call.py
git commit -m "feat(bot): add /call command to trigger outbound voice calls via LiveKit"
```

---

## Task 7: Integration test — full voice pipeline

**Files:**
- Create: `tests/integration/test_voice_pipeline.py`

**Step 1: Write integration test**

```python
# tests/integration/test_voice_pipeline.py
"""Integration tests for voice pipeline (requires Docker voice profile)."""
import pytest
import httpx

RAG_URL = "http://localhost:8080"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_api_health():
    """RAG API should return healthy status."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{RAG_URL}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_api_query():
    """RAG API should return a response for a query."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{RAG_URL}/query",
            json={"query": "тестовый запрос", "channel": "api"},
            timeout=30.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "query_type" in data
        assert "latency_ms" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_livekit_server_health():
    """LiveKit server should be running."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("http://localhost:7880", timeout=5.0)
            # LiveKit returns 200 on root
            assert resp.status_code in (200, 404)
        except httpx.ConnectError:
            pytest.skip("LiveKit server not running")
```

**Step 2: Run tests**

Run: `docker compose -f docker-compose.dev.yml --profile voice up -d`
Run: `uv run pytest tests/integration/test_voice_pipeline.py -v -m integration`

**Step 3: Commit**

```bash
git add tests/integration/test_voice_pipeline.py
git commit -m "test(voice): add integration tests for RAG API and LiveKit"
```

---

## Порядок выполнения

```
Task 1 (deps)          ← Первый — зависимости для всех остальных
  ↓
Task 2 (RAG API)       ← Основа, от которой зависит voice agent
Task 3 (LiveKit Docker) ← Параллельно с Task 2
Task 4 (PostgreSQL)     ← Параллельно с Task 2 и 3
  ↓
Task 5 (Voice Agent)    ← Зависит от 2 (RAG API) и 4 (transcript store)
  ↓
Task 6 (Telegram /call) ← Зависит от 5
  ↓
Task 7 (Integration)    ← Финальная проверка
```

**Параллельные группы:**
- Tasks 2, 3, 4 — можно делать параллельно (после Task 1)
- Task 5 требует Task 2 + Task 4

**Сравнение с v1 (Asterisk + Pipecat):**

| | v1 (old) | v2 (LiveKit) |
|---|---------|-------------|
| Tasks | 11 | 7 |
| Новых файлов | ~15 | ~10 |
| Custom code | ~800 LOC | ~200 LOC |
| Контейнеров | 3 (Asterisk + voice + RAG API) | 4 (LiveKit + SIP + agent + RAG API) |
| Конфигов | pjsip.conf, extensions.conf, ari.conf, http.conf, rtp.conf, modules.conf | livekit.yaml (6 строк) |
