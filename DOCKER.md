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
make core-up

# Core + PostgreSQL (opt-in domain DB for bookmarks/user features)
docker compose -f compose.yml -f compose.dev.yml --profile postgres up -d

# Core + bot (Compose-managed bot)
make docker-bot-up

# Core + ingestion (lean Markdown-only ingestion pipeline)
make docker-ingest-up

# Full stack (all profiles)
make docker-full-up

# Status
make docker-ps

# Stop everything
make docker-down

# Prune build cache and stopped containers (safe)
make docker-clean
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
make core-up      # start sidecars
make run-bot      # run bot natively
```

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
directory containing the exported Drive files before running `make docker-ingest-up`.
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

# Apply — delete orphaned volumes
make docker-clean-orphan-worktree-volumes-apply
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
