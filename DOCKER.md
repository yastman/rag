# Docker Services

This document is the source of truth for containerized local/dev/VPS runtime in this repository.

## Compose Files

| File | Scope | Typical use |
| --- | --- | --- |
| `compose.yml` | Secure baseline for all services | Shared base for local and VPS |
| `compose.dev.yml` | Development overrides (ports, profile gating, local defaults) | Local development and integration testing |
| `compose.vps.yml` | VPS production-like overrides | Server deployment and operations |

## Compose Project Name

The canonical local Compose project name is `dev`. `COMPOSE_PROJECT_NAME=dev` is set in `tests/fixtures/compose.ci.env`, which is the fallback env file used by local `make` targets when `.env` is absent. There is only one local stack; do not create worktree-named Docker projects.

## Compose Profiles (`compose.yml` + `compose.dev.yml`)

Default `up` (no profile) starts unprofiled services:
- `postgres`, `redis`, `qdrant`, `bge-m3`, `user-base`, `docling`
- `mini-app-api`
- `mini-app-frontend`

Optional profiles add scoped services:

| Profile | Services |
| --- | --- |
| `bot` | `litellm`, `bot` |
| `ingest` | `ingestion` |
| `voice` | `rag-api`, `livekit-server`, `livekit-sip`, `voice-agent`, `litellm` — **intentionally separate/off for now** |
| `ml` | `clickhouse`, `minio`, `redis-langfuse`, `langfuse-worker`, `langfuse` |
| `obs` | `loki`, `promtail`, `alertmanager` |
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

For local development, the canonical local env file is `.env` in the repo root. `.env.local` is not auto-loaded by the documented `make` and `uv run` workflows.

Local `make` targets that use `$(LOCAL_COMPOSE_CMD)` automatically fall back to `tests/fixtures/compose.ci.env` when `.env` is absent. This lets commands like `make docker-ps` and profile-gated `up` targets render Compose config without real secrets.

The MacBook remote Docker workflow is intentionally narrower than the full
profile stack. On an 8GB MacBook, keep the default remote runtime to the
bot/core path and start `ml`, `obs`, `voice`, or `full` only for focused checks.
See [`docs/runbooks/remote-macbook-docker.md`](docs/runbooks/remote-macbook-docker.md).

## Service Endpoints (Host)

| Service | URL/Port |
| --- | --- |
| PostgreSQL | `localhost:5432` |
| Qdrant | `http://localhost:6333` (`6334` gRPC) |
| Redis | `localhost:6379` |
| BGE-M3 API | `http://localhost:8000` |
| User Base | `http://localhost:8003` |
| Docling | `http://localhost:5001` |
| Mini App API | `http://localhost:8090` |
| Mini App Frontend | `http://localhost:8091` |
| LiteLLM | `http://localhost:4000` |
| Langfuse | `http://localhost:3001` |
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

### OpenTelemetry Service Identity (`OTEL_SERVICE_NAME`)

Each Langfuse-instrumented service sets a stable `OTEL_SERVICE_NAME` default in Compose so traces and observations are consistently attributed. The variable is optional — every service falls back to its default when `OTEL_SERVICE_NAME` is unset.

| Service | Default `OTEL_SERVICE_NAME` |
| --- | --- |
| `bot` | `telegram-bot` |
| `mini-app-api` | `mini-app-api` |
| `ingestion` | `ingestion` |
| `rag-api` | `rag-api` |

The defaults are set in `compose.yml` and mirrored in `compose.dev.yml` for profile-gated local overrides. `telegram_bot/observability.py` also sets `telegram-bot` at runtime as a safety fallback for non-Docker execution. Kubernetes manifests under `k8s/` additionally hard-code the `telegram-bot` identity.

To override, export `OTEL_SERVICE_NAME` in the shell or set it in `.env` before starting services:

```bash
export OTEL_SERVICE_NAME=custom-bot-name
make docker-bot-up
```

## Health Checks

```bash
make docker-ps

curl -fsS http://localhost:6333/readyz
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:5001/health
curl -fsS http://localhost:4000/health/liveliness
curl -fsS http://localhost:3100/ready
curl -fsS http://localhost:9093/-/healthy

# Preflight gate for Redis auth + retrieval + LLM connectivity
make test-bot-health
```

`make test-bot-health` resolves `QDRANT_COLLECTION` in the same order as local Docker runtime intent:
1. exported shell env (`QDRANT_COLLECTION`)
2. `.env` value (`QDRANT_COLLECTION=...`)
3. compose default from `compose.yml` (currently `gdrive_documents_bge`)

For native bot startup it also resolves Redis in this order:
1. exported shell env (`REDIS_URL`)
2. `.env` value (`REDIS_URL=...`)
3. derived local default from `REDIS_PASSWORD` as `redis://:REDIS_PASSWORD@localhost:6379`

## Local Release Gate

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-bot-health
```

## Source Of Truth

- `main` in Git is the official deployment source of truth for VPS.
- Standard flow: work locally, push to `dev` or a feature branch, open a PR to `main`, and merge the PR.
- Only merges to `main` should trigger VPS auto-deploy through GitHub Actions.
- `make deploy-bot` prints the official PR-based deploy flow; it does not push directly to `main`.
- Use `make deploy-vps-local` or `./scripts/deploy-vps.sh` only as fallback/manual recovery when GitHub-driven deploy is unavailable.
- Do not treat `/opt/rag-fresh` on the server as an editable working copy; it is a deployment target.

## Internal K3s Images

- Kubernetes manifests under `k8s/` use versioned GitHub Container Registry images instead of local `rag/*:latest` tags.
- Canonical image names:
  - `ghcr.io/yastman/rag-bot`
  - `ghcr.io/yastman/rag-ingestion`
  - `ghcr.io/yastman/rag-docling`
  - `ghcr.io/yastman/rag-user-base`
  - `ghcr.io/yastman/rag-bge-m3`
- Publish workflow: `.github/workflows/publish-internal-images.yml`
- Manual publish helper: `make k3s-push-<service> K3S_IMAGE_TAG=v<version>`
- Use explicit version tags for k3s manifests and let Renovate manage future updates.

## Common Operations

```bash
# Logs
make monitoring-logs
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility logs -f bot litellm qdrant

# Rebuild selected services
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility build bot litellm bge-m3
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --force-recreate bot litellm bge-m3

# Image drift check against compose-pinned images (uses compose.yml + compose.dev.yml + tests/fixtures/compose.ci.env)
make verify-compose-images

# Validate required Langfuse trace families (fast, no rebuild)
make validate-traces-fast
```

## Notes

- Compose resources are started with `--compatibility` in `Makefile` to apply `deploy.resources.limits` locally.
- `bge-m3` memory is controlled by `BGE_M3_MEMORY_LIMIT` and defaults to 4G in
  local/dev Compose, including the MacBook remote helpers.
- Images are pinned by tag+digest in compose files; update pins explicitly.
- Local and profile workflows use the canonical local compose set: `compose.yml:compose.dev.yml`.
- Docker runtime for images that import `telegram_bot.observability` (and therefore `langfuse`) uses Python 3.13. Local native development may still use the repo's `uv` environment (Python 3.11+).
- The `voice` profile (LiveKit, SIP, voice agent) is intentionally not part of the current local bring-up. Bring it up separately only when explicitly needed.
- `mini-app-frontend` runs nginx as `101:101` with `cap_drop: [ALL]` and `cap_add: [NET_BIND_SERVICE]`; nginx runtime PID/temp paths are kept under `/tmp` to avoid privileged `chown` startup paths.
