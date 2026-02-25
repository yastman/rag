---
paths: "src/voice/**,src/api/**"
---

# Voice Bot (LiveKit Agents + SIP)

## Architecture

```
Telegram /call → PropertyBot dispatches LiveKit room via API
                     ↓
LiveKit SIP Server → lifecell trunk (csbc.lifecell.ua:5061)
                     ↓
LiveKit Voice Agent (Python SDK):
  - Silero VAD (pre-warmed in _prewarm_process, prevents unresponsive kills)
  - ElevenLabs STT (scribe_v2_realtime, ~80ms)
  - LLM via LiteLLM (LLM_MODEL, default gpt-4o-mini)
  - @function_tool search_knowledge_base → httpx POST → RAG API :8080
  - ElevenLabs TTS (eleven_turbo_v2_5, voice_id via ELEVENLABS_VOICE_ID)
  - Langfuse via OTEL (voice lifecycle tracing)
                     ↓
PostgreSQL (call transcripts: role + text + timestamp_ms)
```

## Modules

| Module | Purpose |
|--------|---------|
| `src/api/main.py` | FastAPI RAG API — POST /query, GET /health |
| `src/api/schemas.py` | QueryRequest, QueryResponse |
| `src/voice/agent.py` | LiveKit VoiceBot Agent + AgentServer |
| `src/voice/schemas.py` | CallStatus, CallRequest, CallResponse, TranscriptEntry |
| `src/voice/transcript_store.py` | PostgreSQL async store (asyncpg) — create_call, append_transcript, finalize_call |
| `src/voice/sip_setup.py` | One-time lifecell SIP trunk provisioning |
| `src/voice/observability.py` | trace_voice_session(), update_voice_trace() — Langfuse OTEL spans |

## Voice Agent Details

**`VoiceBot(Agent)`** in `src/voice/agent.py`:
- `entrypoint()` registered as `@server.rtc_session(agent_name="voice-bot")`
- Parses metadata from `ctx.job.metadata` JSON: call_id, lead_data, phone, callback_chat_id, langfuse_trace_id
- Pre-warms Silero VAD in `_prewarm_process()` (prevents unresponsive process kills)
- `AgentServer` settings: `num_idle_processes=2`, `initialize_process_timeout=30s`

**`@function_tool search_knowledge_base`** — calls RAG API via httpx POST (NOT direct graph import).

## RAG API

**`src/api/main.py`** — FastAPI (port 8080):
- `POST /query` → `build_graph().ainvoke()` with `message=None` (non-streaming)
- Returns: response text, query_type, cache_hit, documents_count, rerank_applied, latency_ms, context
- Langfuse: `@observe(name="rag-api-query")` + `propagate_attributes()` + `write_langfuse_scores()`
- Reuses full LangGraph pipeline from `telegram_bot/graph/`

## Voice Lifecycle Tracing (#614)

Trace family: `voice-session` with metadata states:
- `answered` — call connected
- `tool_call` — RAG API invoked
- `finalized` — call ended normally (duration_sec, langfuse_trace_id)
- `error` — call failed

Dual tracing: OTEL from LiveKit Agent + `@observe` from RAG API. Trace ID propagated via call metadata.

## Transcript Store

PostgreSQL table from `docker/postgres/init/04-voice-schema.sql`:
- `create_call(call_id, phone, lead_data)` → new record
- `append_transcript(call_id, role, text, timestamp_ms)` → JSONB array append
- `update_status(call_id, status)` → CallStatus enum
- `finalize_call(call_id, duration_sec, langfuse_trace_id)` → close record

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
ELEVENLABS_VOICE_ID=         # TTS voice
LIVEKIT_URL=ws://livekit-server:7880
LIVEKIT_API_KEY=devkey       # dev mode
LIVEKIT_API_SECRET=secret    # dev mode
LIFECELL_SIP_USER=           # SIP auth
LIFECELL_SIP_PASS=           # SIP auth
LIFECELL_SIP_NUMBER=         # SIP phone number
SIP_TRUNK_ID=                # from sip_setup.py output
RAG_API_URL=http://rag-api:8080
DATABASE_URL=                # PostgreSQL for transcripts
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
