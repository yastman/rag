---
paths: "src/voice/**,src/api/**"
---

# Voice Bot (LiveKit Agents + SIP)

## Architecture

```
Telegram /call → LiveKit API (dispatch + SIP call)
                     ↓
LiveKit SIP Server → lifecell trunk (csbc.lifecell.ua:5061)
                     ↓
LiveKit Voice Agent (Python):
  - ElevenLabs STT (`scribe_v2_realtime`, ~80ms)
  - LLM via LiteLLM (`LLM_MODEL`, default `gpt-4o-mini`) + Silero VAD
  - @function_tool → RAG API (FastAPI + LangGraph)
  - ElevenLabs TTS (`eleven_turbo_v2_5`, voice_id via `ELEVENLABS_VOICE_ID`)
  - Langfuse via OTEL
                     ↓
PostgreSQL (call transcripts)
```

## Modules

| Module | Purpose |
|--------|---------|
| `src/api/main.py` | FastAPI RAG API — POST /query, GET /health |
| `src/api/schemas.py` | QueryRequest, QueryResponse |
| `src/voice/agent.py` | LiveKit VoiceBot Agent + AgentServer |
| `src/voice/schemas.py` | CallStatus, CallRequest, CallResponse, TranscriptEntry |
| `src/voice/transcript_store.py` | PostgreSQL async store (asyncpg) |
| `src/voice/sip_setup.py` | One-time lifecell SIP trunk provisioning |

## Docker Profile: voice

```bash
docker compose -f docker-compose.dev.yml --profile core --profile voice up -d
```

Services: `rag-api:8080`, `livekit-server:7880`, `livekit-sip:5060/5061`, `voice-agent`

## Key Patterns

- **RAG API** reuses `build_graph()` from `telegram_bot/graph/` with `message=None` (non-streaming)
- **Voice Agent** calls RAG API via `httpx` POST, NOT direct graph import
- **Langfuse**: dual tracing — OTEL from LiveKit Agent + @observe from RAG API
- **Dependencies** in `[project.optional-dependencies.voice]`, not main group
- **SIP trunk** provisioned once via `python -m src.voice.sip_setup`

## Env Vars

```
ELEVENLABS_API_KEY=          # STT + TTS
LIVEKIT_URL=ws://livekit-server:7880
LIVEKIT_API_KEY=devkey       # dev mode
LIVEKIT_API_SECRET=secret    # dev mode
LIFECELL_SIP_USER=           # SIP auth
LIFECELL_SIP_PASS=           # SIP auth
SIP_TRUNK_ID=                # from sip_setup.py output
RAG_API_URL=http://rag-api:8080
```

## Tests

```bash
uv run pytest tests/unit/api/ tests/unit/voice/ tests/unit/test_cmd_call.py -v
uv run pytest tests/integration/test_voice_pipeline.py -v -m integration  # requires Docker voice profile
```

## Design & Plan

- Design: `docs/plans/2026-02-11-voice-bot-design.md`
- Plan: `docs/plans/2026-02-11-voice-bot-plan.md`
- Issue: #153
