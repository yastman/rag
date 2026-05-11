# src/voice/

LiveKit Voice Agent — outbound calls with RAG Q&A.

> **Status: Deferred / off by default.**
>
> LiveKit services (`livekit-server`, `livekit-sip`, `voice-agent`) are gated behind Docker Compose profiles (`voice`, `full`). They are **not started** in the default `docker compose up` bring-up. To enable voice, explicitly activate the profile: `docker compose --profile voice up`.

## Purpose

Provides a voice interface to the RAG system using LiveKit Agents. The agent handles SIP calls, transcribes speech, queries the RAG API, and synthesizes responses.

## Ownership

- Owns the LiveKit voice agent transport path, SIP helpers, RAG API client, schemas, and transcript storage.
- Maintains voice-specific observability wrappers while reusing shared tracing infrastructure.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`agent.py`](./agent.py) | LiveKit agent implementation with graceful import fallback |
| [`rag_api_client.py`](./rag_api_client.py) | HTTP client to the RAG API (`src/api/`) |
| [`sip_setup.py`](./sip_setup.py) | SIP trunk configuration helpers |
| [`transcript_store.py`](./transcript_store.py) | Call transcript persistence |

## Boundaries

- The voice agent is a **separate transport surface**. It calls the RAG API (`src/api/`) rather than embedding retrieval logic directly.
- If LiveKit SDK is unavailable, imports degrade gracefully with stub classes.
- Voice reuses `telegram_bot.observability` for Langfuse tracing but calls the RAG API (`src/api/`) for all retrieval and generation logic.

## Related Runtime Services

- **LiveKit Server** — WebRTC/media routing (`livekit-server`)
- **LiveKit SIP** — SIP trunk bridge (`livekit-sip`)
- **RAG API** — `src/api/main.py` (voice agent queries this)
- **Langfuse** — voice session tracing (optional)

## Focused checks

```bash
uv run pytest tests/unit/voice/ -q
uv run python -c "from src.voice.agent import VoiceBot; print('ok')"
```

## See Also

- [`../api/`](../api/) — RAG API that the voice agent consumes
- [`../../DOCKER.md`](../../DOCKER.md) — Docker profiles and service orchestration
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../../docs/runbooks/README.md`](../../docs/runbooks/README.md) — Operational troubleshooting
