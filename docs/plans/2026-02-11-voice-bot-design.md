# Voice Bot Design — Outbound RAG Calls via LiveKit Agents + lifecell SIP

**Date:** 2026-02-11
**Status:** Draft v2
**Scope:** Исходящие звонки для валидации заявок + RAG Q&A
**Previous:** v1 использовал Asterisk + Pipecat — заменено на LiveKit Agents (native SIP)

## Общая архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│ Telegram Bot (aiogram)                                              │
│  ├─ /call <phone> <заявка> → LiveKit API: dispatch + SIP call       │
│  └─ Обычные текстовые запросы → LangGraph (как сейчас)              │
└────────┬───────────────────────────┬────────────────────────────────┘
         │                           │
    ┌────▼────┐               ┌──────▼────────────────┐
    │ RAG API │◄──────────────│ LiveKit Voice Agent    │
    │(FastAPI)│  @function_   │ (Python, livekit-agents│
    │LangGraph│    tool       │  ElevenLabs STT+TTS)   │
    │Langfuse │               └──────┬────────────────┘
    └────┬────┘                      │
         │                    ┌──────▼──────────────┐
    ┌────▼────────────────┐   │ LiveKit Server       │
    │ Shared Services      │   │ ├─ SIP Server (5060) │
    │ Qdrant, Redis,       │   │ ├─ WebRTC rooms      │
    │ LiteLLM, BGE-M3,     │   │ └─ Redis (state)     │
    │ Langfuse, PostgreSQL  │   │       │               │
    └──────────────────────┘   │  SIP INVITE           │
                               │       ↓               │
                               │  lifecell trunk       │
                               │  csbc.lifecell.ua:5061│
                               └───────────────────────┘
```

## Почему LiveKit Agents (а не Asterisk + Pipecat)

| Критерий | Asterisk + Pipecat (v1) | LiveKit Agents (v2) |
|----------|------------------------|---------------------|
| SIP | Отдельный Asterisk контейнер + ARI конфиг | Native SIP server, trunk через API |
| Audio | Custom RTP handler + G.711↔PCM | Автоматический транскодинг Opus↔G.711 |
| STT/TTS | Custom WebSocket клиенты | Встроенные плагины (1 строка кода) |
| VAD | Ручная настройка | Silero VAD из коробки |
| Инфраструктура | 3 контейнера (Asterisk + voice-service + RAG API) | 2 контейнера (LiveKit + voice-agent) + RAG API |
| Langfuse | Ручная интеграция | OTEL → Langfuse (built-in) |
| Код | ~800 LOC custom (RTP, ARI, WS) | ~200 LOC (Agent + function tools) |
| Production | OpenAI не использует | Powers OpenAI Advanced Voice Mode |

## Стек

| Компонент | Технология | Назначение |
|-----------|-----------|------------|
| SIP trunk | lifecell Украина | TLS:5061 → csbc.lifecell.ua, G.711 alaw |
| Voice server | LiveKit Server (self-hosted) | WebRTC rooms + native SIP server |
| Voice framework | livekit-agents ~1.3 | AgentSession + Agent class |
| STT | ElevenLabs Scribe v2 Realtime | livekit-plugins-elevenlabs, ~80ms |
| TTS | ElevenLabs Flash v2.5 | livekit-plugins-elevenlabs, ~75ms |
| LLM | GPT-4o-mini via LiteLLM | livekit-plugins-openai |
| RAG pipeline | LangGraph (existing) | Exposed via FastAPI, @function_tool |
| VAD | Silero | Встроенный плагин |
| Noise cancellation | Krisp | krisp_enabled=True на SIP participant |
| Observability | Langfuse v3 via OTEL | set_tracer_provider() |
| Transcript DB | PostgreSQL 17 | Полные транскрипты звонков |

## Поток исходящего звонка

```
1. Telegram: /call +380501234567 Заявка на квартиру
   ↓
2. Bot → LiveKit API:
   a) CreateRoom("voice-call-{uuid}")
   b) CreateAgentDispatch(agent_name="voice-bot", room, metadata={phone, lead_data})
   c) CreateSIPParticipant(trunk_id, phone, room, wait_until_answered=True)
   ↓
3. LiveKit SIP Server → SIP INVITE → csbc.lifecell.ua:5061 (TLS, G.711 alaw)
   ↓
4. Абонент поднимает трубку → joins room as SIP participant
   ↓
5. Voice Agent (Python) starts in room:
   ┌──────────────────────────────────────────────────────┐
   │ Silero VAD → ElevenLabs Scribe v2 RT (STT, ~80ms)   │
   │   ↓ текст                                            │
   │ LLM (gpt-4o-mini via LiteLLM):                       │
   │   - Slot-filling (валидация заявки)                   │
   │   - @function_tool → POST rag-api/query (RAG)        │
   │   ↓ текст ответа                                     │
   │ ElevenLabs Flash v2.5 TTS (~75ms TTFT)                │
   │   ↓                                                   │
   │ Opus → LiveKit SIP Server → G.711 alaw → телефон      │
   └──────────────────────────────────────────────────────┘
   ↓
6. Завершение: транскрипт → PostgreSQL, trace → Langfuse
              результат → callback в Telegram чат
```

## Латенси бюджет

| Этап | Время |
|------|-------|
| VAD + STT (Scribe v2 RT) | ~80ms |
| LLM (slot-filling, без RAG) | ~300-500ms |
| LLM + RAG API call | ~2-4s |
| TTS TTFT (Flash v2.5) | ~75ms |
| Opus ↔ G.711 transcoding | ~5ms (автоматически) |
| **Итого slot-filling** | **~500-700ms** |
| **Итого с RAG** | **~2.5-4.5s** |

## Компоненты

### RAG API (новый сервис)

```python
# src/api/main.py — FastAPI wrapper вокруг LangGraph
POST /query        → {query, user_id, session_id, channel: "voice"|"telegram"} → RAG ответ
GET  /health       → healthcheck (Qdrant, Redis, LiteLLM)
```

- Импортирует `build_graph()`, `GraphConfig`, `make_initial_state()` из `telegram_bot/graph/`
- Инициализирует сервисы один раз при старте (Qdrant, Redis, BGE-M3, LLM)
- Langfuse trace автоматически — тот же `@observe()` декоратор
- `message=None` → non-streaming mode

### Voice Agent (новый сервис)

```python
# src/voice/agent.py — LiveKit Agent с RAG function tool

class VoiceBot(Agent):
    instructions = "Ты бот-ассистент для валидации заявок..."

    @function_tool()
    async def search_knowledge_base(self, ctx, query: str) -> str:
        """Ищет в базе знаний."""
        resp = await httpx.post(RAG_API_URL + "/query", json={...})
        return resp.json()["response"]

server = AgentServer()

@server.rtc_session(agent_name="voice-bot")
async def entrypoint(ctx: JobContext):
    session = AgentSession(
        stt=elevenlabs.STT(model="scribe_v2_realtime"),
        llm=openai.LLM.with_cerebras(model="..."),  # или через LiteLLM
        tts=elevenlabs.TTS(voice_id="...", model="eleven_turbo_v2_5"),
        vad=silero.VAD.load(),
    )
    await session.start(room=ctx.room, agent=VoiceBot())
```

### LiveKit Server (Docker)

```yaml
livekit-server:
  image: livekit/livekit-server:latest
  ports: [7880, 7881, 50000-60000/udp]

livekit-sip:
  image: livekit/sip:latest
  ports: [5060/udp, 5061/tcp, 10000-20000/udp]
```

Никакой настройки Asterisk, pjsip.conf, extensions.conf — всё через API.

### SIP Trunk (конфигурация через API)

```python
# Одноразовая настройка trunk
trunk = SIPOutboundTrunkInfo(
    name="lifecell-ukraine",
    address="csbc.lifecell.ua:5061",
    numbers=["+380XXXXXXXXX"],
    auth_username=LIFECELL_SIP_USER,
    auth_password=LIFECELL_SIP_PASS,
)
await lk_api.sip.create_sip_outbound_trunk(trunk)
```

### Database

```sql
CREATE TABLE call_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    lead_data JSONB DEFAULT '{}',
    transcript JSONB DEFAULT '[]',    -- [{role, text, timestamp_ms}]
    langfuse_trace_id VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'initiated',
    duration_sec INTEGER DEFAULT 0,
    validation_result JSONB,
    callback_chat_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Telegram /call command

```python
# В telegram_bot/bot.py
async def cmd_call(self, message: Message):
    # 1. Валидация (admin-only, phone format)
    # 2. LiveKit API: dispatch agent + SIP call
    # 3. Ответ: "Звонок инициирован, ID: ..."
    # 4. Background: ждать callback с результатом
```

## Langfuse Tracing

### Двойная трассировка

**LiveKit Agent OTEL spans** (автоматические):
- Session start/stop
- STT processing
- LLM calls
- TTS processing
- Function tool calls (RAG)

**RAG API Langfuse spans** (через @observe):
- Полный LangGraph trace (classify → retrieve → generate)
- 14+ existing scores

### Voice Call Trace Structure

```
TRACE: voice_call_{call_id} (via OTEL → Langfuse)
├── SPAN: agent_session
│   ├── SPAN: stt (ElevenLabs Scribe — auto from plugin)
│   ├── SPAN: llm_call (auto from plugin)
│   │   └── SPAN: function_tool:search_knowledge_base
│   │       └── → HTTP call → RAG API → отдельный Langfuse trace
│   └── SPAN: tts (ElevenLabs — auto from plugin)
│
├── SCORE: call_duration_sec (manual)
├── SCORE: turns_count (manual)
├── SCORE: validation_success (manual)
└── metadata: {phone, lead_data, channel: "voice"}
```

### Setup

```python
# src/voice/agent.py
from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def setup_langfuse():
    auth = base64.b64encode(f"{PUBLIC_KEY}:{SECRET_KEY}".encode()).decode()
    exporter = OTLPSpanExporter(
        endpoint=f"{LANGFUSE_HOST}/api/public/otel",
        headers={"Authorization": f"Basic {auth}"},
    )
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    set_tracer_provider(provider)  # LiveKit-specific!
```

### Метрики

| Метрика | Источник | Цель |
|---------|----------|------|
| Call success rate | SIP answer status | >80% |
| Avg call duration | agent session time | 30-120s |
| STT latency | OTEL span | <150ms |
| TTS TTFT | OTEL span | <100ms |
| RAG latency in call | function_tool span | <3s |
| E2E voice latency | STT end → TTS first byte | <3s |

## Файловая структура (новые файлы)

```
src/
├── api/                        # RAG API (FastAPI)
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, POST /query
│   ├── schemas.py              # Pydantic models
│   └── Dockerfile
├── voice/                      # Voice Agent (LiveKit)
│   ├── __init__.py
│   ├── agent.py                # LiveKit Agent + AgentServer
│   ├── schemas.py              # Pydantic models (CallRequest, CallStatus)
│   ├── transcript_store.py     # PostgreSQL transcript storage
│   ├── sip_setup.py            # One-time SIP trunk provisioning script
│   └── Dockerfile
docker/
├── livekit/
│   └── livekit.yaml            # LiveKit server config
├── postgres/
│   └── init/
│       └── 02-voice-schema.sql # Call transcripts table
```

## Docker Compose (дополнение к docker-compose.dev.yml)

```yaml
services:
  rag-api:
    build:
      context: .
      dockerfile: src/api/Dockerfile
    container_name: dev-rag-api
    profiles: ["voice", "full"]
    ports: ["127.0.0.1:8080:8080"]
    depends_on: [qdrant, redis, litellm, bge-m3]

  livekit-server:
    image: livekit/livekit-server:v1.8
    container_name: dev-livekit
    profiles: ["voice", "full"]
    ports:
      - "7880:7880"       # API + WebSocket
      - "7881:7881"       # ICE/TCP
      - "50000-50100:50000-50100/udp"  # WebRTC media
    volumes:
      - ./docker/livekit/livekit.yaml:/etc/livekit.yaml
    command: --config /etc/livekit.yaml --dev

  livekit-sip:
    image: livekit/sip:latest
    container_name: dev-livekit-sip
    profiles: ["voice", "full"]
    ports:
      - "5060:5060/udp"
      - "5061:5061/tcp"
      - "10000-10100:10000-10100/udp"
    environment:
      LIVEKIT_API_KEY: devkey
      LIVEKIT_API_SECRET: secret
      LIVEKIT_WS_URL: ws://livekit-server:7880
      SIP_PORT: 5060
      RTP_PORT_LOW: 10000
      RTP_PORT_HIGH: 10100
    depends_on: [livekit-server]

  voice-agent:
    build:
      context: .
      dockerfile: src/voice/Dockerfile
    container_name: dev-voice-agent
    profiles: ["voice", "full"]
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
    depends_on: [livekit-server, rag-api, postgres]
```

## MVP этапы

| Этап | Что делаем | Результат |
|------|-----------|-----------|
| **1** | RAG API — вынести LangGraph в FastAPI | `POST /query` работает |
| **2** | LiveKit Server + SIP — Docker setup | LiveKit + SIP server запущены, trunk зарегистрирован |
| **3** | Voice Agent — базовый echo agent | Agent отвечает голосом (без RAG) |
| **4** | Voice Agent — RAG @function_tool | Полный цикл: STT → LLM + RAG → TTS |
| **5** | PostgreSQL + транскрипты | Хранение полных транскриптов |
| **6** | Telegram /call + callback | `/call +380...` → звонок, результат в чат |
| **7** | Langfuse OTEL tracing | Полная трассировка voice calls |

## Зависимости (новые)

```
livekit-agents[silero,turn-detector]~=1.3
livekit-plugins-elevenlabs~=1.0
livekit-plugins-openai~=1.0
livekit-plugins-noise-cancellation~=0.2
livekit~=0.20                     # LiveKit Python SDK (API client)
asyncpg                           # PostgreSQL async driver
fastapi                           # RAG API
uvicorn                           # ASGI server
opentelemetry-sdk                 # OTEL for Langfuse
opentelemetry-exporter-otlp-proto-http
```

## Env vars (новые)

```bash
# ElevenLabs
ELEVENLABS_API_KEY=...            # STT + TTS

# LiveKit
LIVEKIT_URL=ws://livekit-server:7880
LIVEKIT_API_KEY=devkey            # dev mode
LIVEKIT_API_SECRET=secret         # dev mode

# lifecell SIP
LIFECELL_SIP_USER=...
LIFECELL_SIP_PASS=...

# RAG API
RAG_API_URL=http://rag-api:8080

# PostgreSQL (reuse existing or new)
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres

# Voice in Telegram bot
VOICE_SERVICE_URL=                # Not needed — bot calls LiveKit API directly
```
