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

## Worktree Volume Cleanup

`git worktree remove` does **not** tear down Docker Compose stacks created from inside that worktree. Named volumes (HuggingFace caches, Postgres data, Qdrant data, Redis data) survive the worktree deletion and silently consume disk. See [#1546](https://github.com/yastman/rag/issues/1546).

To detect and remove orphan volumes from removed worktrees on this host:

```bash
# Dry-run report (default; prints orphans, makes no changes)
make docker-clean-orphan-worktree-volumes

# Apply: actually delete the orphan volumes
make docker-clean-orphan-worktree-volumes-apply
```

The script enumerates active worktrees via `git worktree list`, infers their Docker Compose project prefixes, and lists `rag-fresh` worktree-like volumes whose prefix does not match any active worktree. Active worktrees, unrelated Compose project prefixes, and the protected prefixes (`dev`, `rag`, `rag-fresh`, `vps`) are always preserved. The default mode is dry-run; deletion requires the `-apply` target. See [`scripts/cleanup_orphaned_worktree_volumes.sh`](scripts/cleanup_orphaned_worktree_volumes.sh) and the operator runbook [`docs/engineering/repo-hygiene-runbook.md`](docs/engineering/repo-hygiene-runbook.md).

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

### VPS default runtime

`compose.yml:compose.vps.yml` starts only the RAG chatbot core by default:
`postgres`, `redis`, `qdrant`, `bge-m3`, `user-base`, `litellm`, and `bot`.

Mini app, Docling, ingestion, and self-hosted Langfuse are optional/profile
runtime on VPS and must not be assumed to be resident services. To run the
optional VPS profile locally, use:

```bash
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --profile vps-noncore up -d
```

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

When `.env` is present, Docker credentials must be set there. `compose.dev.yml`
does not provide built-in password defaults for stateful services; local values
still need to be throwaway/dev-only:

- `BGE_M3_ONNX_MODEL_HOST_DIR` — host path to the ONNX INT8 model artifacts; consumed at Docker build time, not mounted at runtime
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `CLICKHOUSE_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `LANGFUSE_REDIS_PASSWORD`
- `LIVEKIT_API_SECRET` when using the `voice` profile

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
| MinIO API | `http://localhost:${MINIO_API_PORT:-9090}` |
| MinIO Console | `http://localhost:${MINIO_CONSOLE_PORT:-9091}` |
| Loki | `http://localhost:3100` |
| Alertmanager | `http://localhost:9093` |
| RAG API (voice path) | `http://localhost:8080` |
| LiveKit | `ws://localhost:7880` |

## Required Environment Variables

### Core stack (unprofiled services)

- `BGE_M3_ONNX_MODEL_HOST_DIR` — host path to the ONNX INT8 model directory
  containing `model.int8.onnx` and `model.int8.onnx.data`. Used at Docker build
  time via a BuildKit named context; the artifacts are baked into the image and
  do not require a runtime bind mount. Must be an absolute path.
  This is required for all Compose operations that include `bge-m3`.
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`

### Bot path (`make docker-bot-up`)

- `TELEGRAM_BOT_TOKEN`
- `LITELLM_MASTER_KEY`
- At least one provider key for LiteLLM routing:
  - `CEREBRAS_API_KEY` or `GROQ_API_KEY` or `OPENAI_API_KEY`

`telegram_bot/Dockerfile` installs Python dependencies from
`telegram_bot/pyproject.toml` and `telegram_bot/uv.lock`. The root `uv.lock`
does not define the bot image dependency set.

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
| `bge-m3` | `bge-m3` |
| `bot` | `telegram-bot` |
| `user-base` | `user-base` |
| `mini-app-api` | `mini-app-api` |
| `ingestion` | `ingestion` |
| `rag-api` | `rag-api` |
| `voice-agent` | `voice-agent` |

The defaults are set in `compose.yml` and mirrored in `compose.dev.yml` for profile-gated local overrides. `telegram_bot/observability.py` also sets `telegram-bot` at runtime as a safety fallback for non-Docker execution. Kubernetes manifests under `k8s/` additionally hard-code the `telegram-bot` identity.

To override, export `OTEL_SERVICE_NAME` in the shell or set it in `.env` before starting services:

```bash
export OTEL_SERVICE_NAME=custom-bot-name
make docker-bot-up
```

### OpenTelemetry Propagation (`OTEL_PROPAGATORS`)

Each Compose service that initializes the OpenTelemetry SDK declares
`OTEL_PROPAGATORS=${OTEL_PROPAGATORS:-tracecontext,baggage}`. This keeps W3C
TraceContext and Baggage propagation explicit for cross-service trace
continuity; Langfuse user, session, and tag attributes rely on Baggage when
requests cross service boundaries.

Leave the default in place unless a deployment needs an additional propagator,
for example `b3` for Zipkin interoperability:

```bash
export OTEL_PROPAGATORS=tracecontext,baggage,b3
make docker-bot-up
```

### Local Langfuse Headless Initialization

`compose.yml` keeps Langfuse credentials secret-free: it declares traced service
environment variables but does not provide predictable key defaults.

`compose.dev.yml` is the local convenience layer. It provides dev-only
`LANGFUSE_INIT_*` defaults for the `langfuse` service so an empty local
Langfuse database creates a development organization, project, and API key that
match the traced service defaults:

| Variable | Dev default |
| --- | --- |
| `LANGFUSE_INIT_ORG_ID` | `dev-org` |
| `LANGFUSE_INIT_ORG_NAME` | `Local Dev` |
| `LANGFUSE_INIT_PROJECT_ID` | `dev-project` |
| `LANGFUSE_INIT_PROJECT_NAME` | `Local Dev` |
| `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` | `[REDACTED-LANGFUSE-KEY] |
| `LANGFUSE_INIT_PROJECT_SECRET_KEY` | `[REDACTED-LANGFUSE-KEY] |

These non-password defaults are local-only. Override them from `.env` when a dev
stack should use a different local Langfuse project. Production and VPS
environments must provide real Langfuse keys and must not rely on the dev
defaults.

If `bot` logs show OTLP `401` or Langfuse logs show `No key found for public
key`, the local Langfuse database likely lacks the project key currently
injected into traced services. Recreate `langfuse`, `langfuse-worker`, and the
traced service with the same env file so headless initialization and service
credentials line up.

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

### Bot Runtime Environment Preflight

```bash
make preflight-bot
```

This target runs `scripts/probe/check_bot_runtime_env.py` and checks:

* `.env` is present (otherwise the CI fallback `tests/fixtures/compose.ci.env`
  is used — it contains **placeholder** credentials that are **not** valid for
  real bot operation).
* `TELEGRAM_BOT_TOKEN` is not the CI fallback value `123456789:ABC...fghi`.
  Bot startup with this value will crash-loop with `TokenValidationError`.
* LiteLLM port `4000` is published on the Docker host (if Docker is available).
  A missing port binding is most often caused by a **stray third compose file**
  that sets `litellm: {ports: []}`, overriding the `compose.dev.yml` mapping
  of `"127.0.0.1:4000:4000"`.

If issues are found `preflight-bot` exits non-zero, which blocks the
`docker-bot-up` and `bot` targets. To run checks without blocking (e.g. in CI):

```bash
PREFLIGHT_BOT_FLAGS='--no-fail' make preflight-bot
```

The preflight is a **guardrail** — it explains what is wrong and how to fix
it, but it cannot supply real credentials. You must provide a valid
`TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY`, and at least one provider key
in `.env`.

### Common `make bot` and `make docker-bot-up` failures

| Symptom                                         | Likely cause                                    | Fix                                                                              |
|-------------------------------------------------|-------------------------------------------------|----------------------------------------------------------------------------------|
| Bot crash-loop, `TokenValidationError`          | `.env` is missing and CI fallback token is used | `cp .env.example .env` then set `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY`, and a provider key |
| `curl localhost:4000` Connection Refused        | LiteLLM port not published; stray compose file  | Remove any stray compose files (e.g. `/tmp/compose.postgres-root.yml`) that override `litellm` ports, then `make docker-bot-up` |
| Redis auth `WRONGPASS` / `NOAUTH` after `.env` change | `REDIS_PASSWORD` differs between `.env` and running container | `make local-redis-recreate` then `make test-bot-health` |
| `make docker-bot-up` exits before starting      | `preflight-bot` detected issues (see #2123, #2126) | `make preflight-bot` for details, or `PREFLIGHT_BOT_FLAGS='--no-fail' make docker-bot-up` to bypass |
| `make bot` exits before starting                | `preflight-bot` detected issues (see #2123, #2126) | `make preflight-bot` for details, or `PREFLIGHT_BOT_FLAGS='--no-fail' make bot` to bypass |

### LiteLLM port recovery (stray compose file)

A stray Compose file at `/tmp/compose.postgres-root.yml` was observed to clear
`litellm` host ports (`ports: []`), overriding the `compose.dev.yml` mapping.
This blocks LLM-dependent commands (`make bot`, `make test-bot-health`).

Recovery:

```bash
# 1. Remove the stray compose file
rm /tmp/compose.postgres-root.yml

# 2. Restart litellm without the stray file
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility \
  --env-file tests/fixtures/compose.ci.env \
  --profile bot up -d --force-recreate litellm

# 3. Verify the port
curl -fsS http://localhost:4000/health/liveliness
```

## Local Release Gate

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-bot-health
```

## Source Of Truth

- `main` in Git is the official deployment source of truth for VPS snapshots.
- Recommended production flow:
  1. Work on a feature branch.
  2. Open a PR to `dev`.
  3. Stage runtime-sensitive changes on the MacBook Docker host with
     `make remote-core-up`.
  4. Merge `dev` to `main` for deployment snapshots.
- Public GitHub Actions validate static guardrails only; they do not deploy to
  VPS or expose production SSH targets.
- `make deploy-bot` prints the official PR-based deploy flow; it does not push
  directly to `main`.
- Do not treat `/opt/rag-fresh` on the server as an editable working copy; it is a deployment target.

### VPS cleanup

After the minimal runtime change, removed-service data can be cleaned with:

```bash
ssh vps 'cd /opt/rag-fresh && ./scripts/vps_cleanup_removed_services.sh'
ssh vps 'cd /opt/rag-fresh && ./scripts/vps_cleanup_removed_services.sh --apply'
```

Never remove `vps_qdrant_data`, `vps_postgres_data`, `vps_redis_data`, or
`vps_hf_cache` during this cleanup. The cleanup script validates the
`COMPOSE_PROJECT_NAME` and `vps-noncore` profile gating before applying.

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

## Qdrant Storage Management

### Background — issue #1545

The `gdrive_documents_bge` collection grew to 3.1 GB on dev and continued
to expand unbounded in production because Qdrant's default settings keep all
payload data in RAM and write-amplify every ingestion cycle.

### Storage optimisation config (`docker/qdrant/config.yaml`)

`docker/qdrant/config.yaml` is mounted read-only into the Qdrant container as
`/qdrant/config/production.yaml` (Qdrant's well-known override path).  The
file enables two settings based on Qdrant documentation:

| Setting | Value | Effect |
| --- | --- | --- |
| `storage.on_disk_payload` | `true` | Moves payload data that is **not** actively indexed to disk, reducing resident RAM at the cost of a small read-latency increase. Indexed payload fields remain in RAM. |
| `storage.optimizers.indexing_threshold_kb` | `20000` | Triggers HNSW graph construction once an unindexed segment exceeds 20 MB, balancing ingestion speed against timely index availability. |

### Applying the config to an existing collection

The config file controls **defaults for new collections**.  For the existing
`gdrive_documents_bge` collection, patch via the REST API after restarting
Qdrant:

```bash
# Restart Qdrant to pick up the new config file
docker compose restart qdrant

# Patch the existing collection to move payloads to disk
curl -X PATCH http://localhost:6333/collections/gdrive_documents_bge \
     -H 'Content-Type: application/json' \
     -d '{"on_disk_payload": true}'
```

### Manual cleanup / pruning (`make qdrant-cleanup`)

```bash
make qdrant-cleanup
```

This Makefile target:
1. **Snapshot** — POSTs to `/collections/gdrive_documents_bge/snapshots` to
   create a recovery point before any segment merging.
2. **Optimise** — temporarily sets `indexing_threshold` to 0 to force a
   segment merge pass, then restores the value to 20 000 kB.
3. **Checklist** — prints the manual curl command to enable `on_disk_payload`
   on the live collection.

> **TTL strategy note:** Qdrant does not have native per-vector TTL.  The
> recommended approach for this repo is to reindex from source (re-run the
> ingestion pipeline) whenever the collection must be rebuilt, or to delete
> individual points by their document `source_id` payload field when source
> documents are removed from Google Drive.  `make qdrant-cleanup` handles
> storage *compaction*, not logical TTL.

### Volume size monitoring

```bash
# Show Docker volume disk usage
docker system df -v | grep qdrant

# Check collection point count and segment stats
curl -s http://localhost:6333/collections/gdrive_documents_bge | python3 -m json.tool
```

## Notes

- Compose resources are started with `--compatibility` in `Makefile` to apply `deploy.resources.limits` locally.
- `bge-m3` memory is controlled by `BGE_M3_MEMORY_LIMIT` and defaults to 4G in
  local/dev Compose.
- Images are pinned by tag+digest in compose files; update pins explicitly.
- Local and profile workflows use the canonical local compose set: `compose.yml:compose.dev.yml`.
- Docker runtime for images that import `telegram_bot.observability` (and therefore `langfuse`) uses Python 3.13. Local native development may still use the repo's `uv` environment (Python 3.11+).
- The `voice` profile (LiveKit, SIP, voice agent) is intentionally not part of the current local bring-up. Bring it up separately only when explicitly needed.
- `mini-app-frontend` runs nginx as `101:101` with `cap_drop: [ALL]` and `cap_add: [NET_BIND_SERVICE]`; nginx runtime PID/temp paths are kept under `/tmp` to avoid privileged `chown` startup paths.
