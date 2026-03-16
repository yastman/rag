# Docker Services

This document is the source of truth for containerized local/dev/VPS runtime in this repository.

## Compose Files

| File | Scope | Typical use |
| --- | --- | --- |
| `compose.dev.yml` | Full development stack with profiles | Local development and integration testing |
| `compose.vps.yml` | VPS production-like stack | Server deployment and operations |

## Compose Profiles (`compose.dev.yml`)

Default `up` (no profile) starts unprofiled services:
- `postgres`, `redis`, `qdrant`, `bge-m3`, `user-base`, `docling`

Optional profiles add scoped services:

| Profile | Services |
| --- | --- |
| `bot` | `litellm`, `bot` |
| `ingest` | `ingestion` |
| `voice` | `rag-api`, `livekit-server`, `livekit-sip`, `voice-agent`, `litellm` |
| `ml` | `clickhouse`, `minio`, `redis-langfuse`, `langfuse-worker`, `langfuse`, `mlflow` |
| `obs` | `loki`, `promtail`, `alertmanager` |
| `security` | `llm-guard` |
| `full` | all profile-gated services |

## Makefile Shortcuts

```bash
# Core stack (default/unprofiled services)
make docker-up

# Profile stacks
make docker-bot-up
make docker-ingest-up
make docker-voice-up
make docker-ml-up
make docker-obs-up
make docker-full-up

# Lifecycle
make docker-ps
make docker-down

# Minimal local subset (same compose file)
make local-up
make local-ps
make local-down
```

## Service Endpoints (Host)

| Service | URL/Port |
| --- | --- |
| Qdrant | `http://localhost:6333` (`6334` gRPC) |
| Redis | `localhost:6379` |
| BGE-M3 API | `http://localhost:8000` |
| Docling | `http://localhost:5001` |
| LiteLLM | `http://localhost:4000` |
| Langfuse | `http://localhost:3001` |
| MLflow | `http://localhost:5000` |
| Loki | `http://localhost:3100` |
| Alertmanager | `http://localhost:9093` |
| RAG API (voice path) | `http://localhost:8080` |
| LiveKit | `ws://localhost:7880` |

## Required Environment Variables

### Bot path (`make docker-bot-up`)

- `TELEGRAM_BOT_TOKEN`
- `LITELLM_MASTER_KEY`
- At least one provider key for LiteLLM routing:
  - `CEREBRAS_API_KEY` or `GROQ_API_KEY` or `OPENAI_API_KEY`

### ML profile (`make docker-ml-up`)

- `NEXTAUTH_SECRET`
- `SALT`
- `ENCRYPTION_KEY`

### Alert delivery (optional, for Telegram alerts)

- `TELEGRAM_ALERTING_BOT_TOKEN`
- `TELEGRAM_ALERTING_CHAT_ID`

### Voice path

- `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` (dev defaults exist)
- `ELEVENLABS_API_KEY` (if ElevenLabs is used)

## Health Checks

```bash
make docker-ps

curl -fsS http://localhost:6333/readyz
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:5001/health
curl -fsS http://localhost:4000/health/liveliness
curl -fsS http://localhost:3100/ready
curl -fsS http://localhost:9093/-/healthy
```

## Common Operations

```bash
# Logs
make monitoring-logs
docker compose --compatibility -f compose.dev.yml logs -f bot litellm qdrant

# Rebuild selected services
docker compose --compatibility -f compose.dev.yml build bot litellm bge-m3
docker compose --compatibility -f compose.dev.yml up -d --force-recreate bot litellm bge-m3

# Image drift check against compose-pinned images
make verify-compose-images
```

## Notes

- Compose resources are started with `--compatibility` in `Makefile` to apply `deploy.resources.limits` locally.
- Images are pinned by tag+digest in compose files; update pins explicitly.
- Local and profile workflows use the same canonical file: `compose.dev.yml`.
- VPS rehearsal/cutover flow is documented in `docs/runbooks/vps-rag-ready.md`.
