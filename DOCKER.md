# DOCKER.md — Compose Runtime Reference

Docker Compose is the primary runtime for all sidecar services. The Python
application runs as a native process (or as the `bot` Compose service for
production-like deploys).

## Compose Files

| File | Purpose |
|---|---|
| `compose.yml` | Base configuration — all services, no ports exposed |
| `compose.dev.yml` | Dev overrides — ports, relaxed caps, dev tuning |
| `compose.core.yml` | Minimal core (Qdrant + Redis only, no auth) |

Use explicit files; do not set `COMPOSE_FILE`:

```bash
docker compose -f compose.yml -f compose.dev.yml up -d
```

`make` targets use this pair on Linux/POSIX.

> **Docker Desktop (Windows):** Use the Linux engine (WSL2 backend). Explicit
> `-f` flags work unchanged; use Windows absolute paths (e.g., `C:\path\to\dir`)
> for host bind mounts and build contexts in `.env`.

## Profiles

Services are gated by profiles. Run only what you need. PostgreSQL is an
opt-in service (#3241): the core demo topology starts without it, and the bot
degrades gracefully (bookmarks capability disabled) when it is absent.

| Profile | Services included |
|---|---|
| *(no profile)* | `redis`, `qdrant`, `bge-m3` |
| `postgres` | above + `postgres` (opt-in domain DB) |
| `bot` | above + `bot` (combine with `postgres` when the bot needs favorites) |
| `ingest` | above + `ingestion` |
| `full` | all services, including `postgres` |

## Services

| Service | Image | Profile | Purpose |
|---|---|---|---|
| `postgres` | `postgres:17` | `postgres`, `full` | Bot domain DB (users/leads/funnel/favorites) — opt-in |
| `redis` | `redis:8.10.1` | default | Five caches: semantic answer, embedding, search, rerank, extraction |
| `qdrant` | `qdrant/qdrant:v1.19.0` | default | Vector store — dense, sparse, ColBERT retrieval; storage config (`on_disk_payload`, `indexing_threshold_kb`) caps growth |
| `bge-m3` | built locally | default | Self-hosted BGE-M3 ONNX embedding API |
| `bot` | built locally | `bot` | Telegram bot process |
| `ingestion` | built locally | `ingest` | Unified ingestion pipeline (Markdown-only, stdlib parsing) |

## Ports (dev only — `compose.dev.yml`)

Base `compose.yml` exposes **no ports**. All ports are loopback-bound in dev.

| Service | Port | Protocol |
|---|---|---|
| `qdrant` | `127.0.0.1:6333` | HTTP REST |
| `qdrant` | `127.0.0.1:6334` | gRPC |
| `redis` | `127.0.0.1:6379` | Redis |
| `postgres` | `127.0.0.1:5432` | PostgreSQL |
| `bge-m3` | `127.0.0.1:8000` | HTTP |

## Common Commands

```bash
# Minimal core (Qdrant + Redis, no auth — fastest start for native dev)
make core-min-up

# Default core (redis, qdrant, bge-m3 — no PostgreSQL)
make docker-core-up

# Core + PostgreSQL (opt-in domain DB for bookmarks/user features)
docker compose -f compose.yml -f compose.dev.yml --profile postgres up -d

# Core + bot (Compose-managed bot)
make docker-bot-up

# Core + ingestion (lean Markdown-only ingestion pipeline)
make local-up-ingest

# Full stack (all profiles). `make docker-full-up` returns success only after
# all six services are healthy; on failure it exits nonzero and prints the
# failing containers' names/statuses (bounded wait: FULL_UP_WAIT_TIMEOUT=600s).
make docker-full-up

# Status (local service set)
make local-ps

# Stop the local service set
make local-down

# Prune Docker build cache / stopped containers directly (no Make wrapper):
docker builder prune -f --filter "until=720h"
docker container prune -f
```

Windows PowerShell equivalents:

```powershell
docker compose -f compose.core.yml up -d
docker compose -f compose.yml -f compose.dev.yml up -d
docker compose -f compose.yml -f compose.dev.yml down
```

### Qdrant upgrade / snapshot rollback

Before upgrading a **populated** Qdrant volume, take a snapshot so the data can
be restored into the previous server version (snapshots are the supported
rollback path; a data directory written by a newer server is not readable by an
older one):

```bash
# 1. Snapshot the collection (run while the old version is still up)
curl -X POST "http://127.0.0.1:6333/collections/{collection}/snapshots"

# 2. Copy the snapshot off the volume (host-side snapshot store: /qdrant/snapshots)
docker compose cp qdrant:/qdrant/snapshots/{collection} ./qdrant-snapshots

# 3. Upgrade the image tag, then recreate only qdrant on the same volume
docker compose -f compose.yml -f compose.dev.yml up -d qdrant

# Rollback: pin the previous image tag, start with a FRESH volume, copy the
# snapshot back and recover it into the previous server version
docker compose cp ./qdrant-snapshots/{snapshot}.snapshot qdrant:/qdrant/snapshots/
curl -X PUT "http://127.0.0.1:6333/collections/{collection}/snapshots/recover?priority=snapshot" \
  -H 'Content-Type: application/json' \
  -d '{"location": "file:///qdrant/snapshots/{snapshot}.snapshot"}'
```

Native bot run (bot as host process, sidecars in Compose):

```bash
make docker-core-up  # start sidecars
make run-bot         # run bot natively
```

## Operator Env Gate (#3367)

Real build/up commands (`make docker-full-up`, `docker-core-up`,
`docker-bot-up`, `local-up`,
`local-up-ingest`, `local-build`) require an **explicit operator env file**
(`.env` by default, override with `OPERATOR_ENV=/path/to/env`). When it is
missing the command exits nonzero with an actionable message — it never falls
back to the CI Compose fixture (dummy credentials and an intentionally invalid
BGE context live there; it is reserved for named CI/static-validation targets
such as the hosted `compose-config` job).

Before Compose runs, every build/up target executes the gate:

```bash
make operator-env-check                 # validate .env (the OPERATOR_ENV default)
make operator-env-check OPERATOR_ENV=/path/to/env
```

The gate validates, before any image build:

- **File existence** — missing `.env` is a hard, nonzero failure.
- **Required secret presence/shape** — `TELEGRAM_BOT_TOKEN`,
  `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `ENCRYPTION_KEY` (64-hex), `SALT`,
  `NEXTAUTH_SECRET`, `BGE_M3_ONNX_MODEL_HOST_DIR`, and at least one of
  `CEREBRAS_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` / `LLM_API_KEY`.
  CI dummy values and `<change-me>` placeholders are rejected.
- **Native host path semantics** — WSL paths (`/mnt/c/...`) and other
  POSIX-absolute paths fail on native Windows; Windows drive-letter paths
  fail on POSIX hosts; every configured host path must exist.
- **BGE-M3 artifact pin** — the artifact directory is hash-verified against
  `services/bge-m3-api/artifact_manifest.json` (#3366), so an invalid or
  substituted model fails before `docker compose build` can consume it.

Failure behavior: each problem is reported as `- KEY: reason` on stderr and
the process exits nonzero. Secret values are never printed — only variable
names, path locations, and remediation hints.

`GDRIVE_SYNC_DIR` is optional (Compose falls back to an empty repo-relative
directory) but is validated the same way when it is set.

## Required Environment Variables

Copy `.env.example` to `.env` and fill in at minimum:

| Variable | Required for | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | compose rendering (postgres is an opt-in profile, #3241) | Any non-empty string for local dev |
| `REDIS_PASSWORD` | all profiles | Any non-empty string for local dev |
| `TELEGRAM_BOT_TOKEN` | `bot` profile | From @BotFather |
| `BGE_M3_ONNX_MODEL_HOST_DIR` | `bge-m3` build | Path to ONNX INT8 model dir; baked into image at build time |
| `GDRIVE_SYNC_DIR` | `ingest` profile | Shared host directory containing exported Drive files |
| `CEREBRAS_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | LLM calls | At least one required |

Native path examples (the operator gate rejects non-native forms):

| Variable | Linux / macOS | Windows Docker Desktop |
|---|---|---|
| `BGE_M3_ONNX_MODEL_HOST_DIR` | `/srv/rag-fresh/models/bge_m3_onnx_int8` | `C:/models/bge_m3_onnx_int8` |
| `GDRIVE_SYNC_DIR` | `/srv/rag-fresh/drive-sync` | `C:/Users/you/Documents/drive-sync` |

## BGE-M3 Build Requirement

`bge-m3` is a locally-built image. The ONNX model directory is baked into the
image at build time via a BuildKit named context — it is **not** bind-mounted
at runtime.

```bash
BGE_M3_ONNX_MODEL_HOST_DIR=./path/to/bge_m3_onnx_int8
```

The directory must contain `model.int8.onnx` (and its `.data` sidecar) before
running `docker compose build bge-m3`.

Windows example (Docker Desktop Linux engine):
```powershell
$env:BGE_M3_ONNX_MODEL_HOST_DIR = "C:/data/models/bge_m3_onnx_int8"
```

## Ingestion Bind Source

`GDRIVE_SYNC_DIR` is mounted read-only by the `ingest` profile. Set it to the
directory containing the exported Drive files before running `make local-up-ingest`.
On Windows Docker Desktop, use a drive shared with Docker and forward slashes:

```powershell
$env:GDRIVE_SYNC_DIR = "C:/Users/you/Documents/drive-sync"
```

When it is unset, Compose creates `./data/drive-sync-empty` in the repository
and ingests no documents. This makes config rendering portable; it is not a
source of documents.

## Redis TTL Policy (volatile-lfu safety audit)

Redis runs with `--maxmemory-policy volatile-lfu` (`compose.yml:65`): only keys
**with a TTL** are eligible for eviction under memory pressure. Keys without a TTL
are never evicted.

Audit result — all Redis key-writing code categorised by TTL presence:

| Key pattern | Module | TTL | Category | Safe? |
|---|---|---|---|---|
| `topics:{user_id}:{expert_id}` | `TopicService` | none | state | ✅ never evicted |
| `topics:{user_id}:thread:{tid}` | `TopicService` | none | state | ✅ never evicted |
| `topic:{chat_id}:{expert_id}` | `TopicManager` | 30 d | state/cache | ⚠️ see note |
| `topic_rev:{chat_id}:{tid}` | `TopicManager` | 30 d | state/cache | ⚠️ see note |
| `implicit_retry:{uid}` | `_bot_query_pipeline` | 60 s | short-lived cache | ✅ intentional |
| `extraction:v1:{hash}` | `ApartmentExtractionPipeline` | 24 h | cache | ✅ intentional |
| `sem:v8:…` (semantic answer cache) | `CacheManager` / RedisVL | per query-type | cache | ✅ intentional |
| `embeddings:v5:…` | `CacheManager` / RedisVL | configured TTL | cache | ✅ intentional |
| `search:v5:…`, `rerank:v5:…`, etc. | `CacheManager.store_exact` | `DEFAULT_TTLS` | cache | ✅ intentional |
| `conversation:{user_id}` | write path removed in #157 | — | n/a | ✅ no writes |

**⚠️ `TopicManager` note:** `topic:` / `topic_rev:` keys carry a 30-day TTL,
making them eviction candidates under memory pressure. These store Telegram forum
topic IDs (created via the Telegram API). Expiry causes a new forum topic to be
created on next access — acceptable degradation, not data loss. If zero-eviction
guarantees are needed, remove the TTL or use `TopicService` (no-TTL variant)
instead.

**Rule:** cache keys must have a TTL; durable state keys must have no TTL (or use
a separate Redis DB). Any future key added to Redis must follow this policy.

## Memory Limits

| Service | Default limit |
|---|---|
| `postgres` | 512 MB |
| `redis` | 300 MB (256 MB on VPS) |
| `qdrant` | 1 GB |
| `bge-m3` | 4 GB (override: `BGE_M3_MEMORY_LIMIT`) |
| `bot` | 512 MB |
| `ingestion` | 1 GB |

## Health Checks

All services declare health checks. Dependent services use `condition:
service_healthy`. On first start, `bge-m3` has a 420 s start period (cold
model load).

Full-profile startup is ordered, waited, and failure-honest (#3361):

- **Ordered** — the `bot` declares `postgres` with
  `condition: service_healthy, required: false`: inside the `postgres`/`full`
  profiles it waits for a healthy database (bookmarks capability setup never
  races a cold PostgreSQL); without those profiles the dependency is skipped
  and PostgreSQL stays optional (#3241). `ingestion` starts only after
  Qdrant and BGE-M3 are healthy.
- **Waited** — `make docker-full-up` runs `docker compose up -d --wait
  --wait-timeout 600` (override: `FULL_UP_WAIT_TIMEOUT`), so success means
  every one of the six services reports healthy — process presence alone is
  never sufficient.
- **Failure-honest** — a failed wait exits nonzero and prints the project's
  container names/statuses (`compose ps -a`), naming the service that broke
  the start. Secret values are never printed.
- **Capability-honest probes** — the `bot` healthcheck verifies its CRITICAL
  dependencies (Redis, Qdrant, BGE-M3) still serve from inside the bot's
  network namespace (PostgreSQL is deliberately not probed — optional
  capability); the `ingestion` healthcheck verifies Qdrant readiness and that
  the BGE-M3 model is actually loaded (`model_loaded`), cold-start-safe on a
  fresh volume where the collection does not exist yet.

Recovery recomputes capability state: whenever the bot (re)starts — including
`docker compose restart bot` after bringing PostgreSQL up late —
`setup_postgres` re-runs and re-enables the bookmarks capability after a
validated connection.

## Volumes

| Volume | Service |
|---|---|
| `postgres_data` | `postgres` |
| `redis_data` | `redis` |
| `qdrant_data` | `qdrant` |
| `hf_cache` | `bge-m3` |
| `ingestion-manifest` | `ingestion` |


## Worktree Cleanup

Orphaned Docker volumes from removed git worktrees can be cleaned up safely:

```bash
# Dry-run — list orphaned volumes
make docker-clean-orphan-worktree-volumes

# Apply — delete orphaned volumes (destructive)
bash scripts/cleanup_orphaned_worktree_volumes.sh --apply
```

The underlying script (`scripts/cleanup_orphaned_worktree_volumes.sh`) defaults to
dry-run mode and protects active worktrees and long-lived project volumes.

## Security Defaults

`compose.yml` applies hardened defaults to all services:
`no-new-privileges`, `cap_drop: ALL`, `read_only: true`. The dev override
(`compose.dev.yml`) relaxes caps on `postgres` as needed for local startup.

## Related Docs

| Document | Use it for |
|---|---|
| [`README.md`](README.md) | Full local setup and validation ladder |
| [`src/ingestion/README.md`](src/ingestion/README.md) | Ingestion operations |
