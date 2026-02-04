# Plan: Fast Docker Startup via Core/Bot/Full Profiles

**Date:** 2026-02-03
**Status:** Draft
**Owner:** Orchestrator

## Goal

Make Docker startup fast for day-to-day ingestion work, without losing the ability to run a full “prod-like” stack.

Target outcomes:
- **Default startup (core)**: ready in **≤ 60–90s** on warm images
- **Bot + core**: ready in **≤ 2–3 min** on warm images
- **Full stack**: unchanged capability, allowed to be slower

## Non-Goals

- Re-architecting the application runtime or RAG pipeline logic
- Replacing services (Langfuse/MLflow/etc.) with alternatives
- Performance tuning inside Qdrant/docling/bge-m3 beyond startup readiness

## Current Findings (Why it’s slow today)

1) **Too many services in the default path** (`docker-compose.dev.yml` starts everything).
2) **Heavy dependency chain**: `bot` depends on `litellm`, which depends on `langfuse`, which depends on `clickhouse/minio/redis-langfuse` → bot startup waits for the whole ML platform.
3) **Model warm-up services** (`bge-m3`, `docling`) have large `start_period` and real warmup time.
4) `Makefile:docker-up` uses `docker compose up -d` without `-f docker-compose.dev.yml`, which can create confusion about which stack is actually running.

## Proposed Strategy

Use **Docker Compose profiles** (preferred) to split the stack into 3 modes:

### Mode 1: `core` (default)
Services required for ingestion correctness:
- `postgres` (for ingestion state/DLQ)
- `qdrant`
- `docling`
- `bm42` (BM42 as HTTP service)
- `ingestion`

Optional (only if required by current ingestion implementation):
- `redis`

**Rule:** core services should be **unprofiled** so `docker compose -f docker-compose.dev.yml up -d` starts core only.

### Mode 2: `bot` (core + bot runtime)
Adds:
- `redis` (if bot cache needs it)
- `bot`

Optional:
- `litellm` (only if bot requires it)

**Rule:** bot should not require `langfuse/clickhouse/minio` to start.

### Mode 3: `full` (prod-like)
Adds:
- Observability: `loki`, `promtail`, `alertmanager`
- ML platform: `clickhouse`, `minio`, `redis-langfuse`, `langfuse-worker`, `langfuse`, `mlflow`
- Optional research/extra: `lightrag`, `bge-m3`, `user-base`, etc.

## Work Items (TЗ)

### P0 — Make core the default
1) **Assign profiles** in `docker-compose.dev.yml`:
   - Keep core services unprofiled
   - Mark heavy/non-essential services as `profiles: ["full"]`
   - Mark observability as `profiles: ["full", "obs"]` (optional split)
   - Mark bot as `profiles: ["bot"]` (if not default)

2) **Remove hard dependency chains**:
   - Ensure `bot` can start without `langfuse` and without `clickhouse/minio`.
   - If Langfuse tracing is needed, gate it behind env flags and/or enable only in `full`.

3) **BM42 single source of truth**:
   - In ingestion, use BM42 via HTTP: `BM42_URL=http://bm42:8000`.
   - Avoid local `fastembed` inside ingestion container if possible (smaller image, faster build).

**Acceptance criteria (P0):**
- `docker compose -f docker-compose.dev.yml up -d` brings `postgres/qdrant/docling/bm42/ingestion` to healthy within target time on warm images.
- Ingestion can process a local test file end-to-end (docling → dense → bm42 HTTP → qdrant upsert).

### P1 — Improve developer ergonomics (commands + docs)
4) Update Makefile targets (no implementation here, just spec):
   - `make docker-core-up`: `docker compose -f docker-compose.dev.yml up -d`
   - `make docker-bot-up`: `docker compose -f docker-compose.dev.yml --profile bot up -d`
   - `make docker-full-up`: `docker compose -f docker-compose.dev.yml --profile full up -d`
   - matching `down/logs/ps` targets for each mode

5) Update docs:
   - `DOCKER.md`: document the three modes and exact commands.

**Acceptance criteria (P1):**
- A new developer can start core/bot/full with a single Make command and understand what is included.

### P2 — Build-time improvements (optional, if rebuild is frequent)
6) Pin moving tags:
   - avoid `:latest` for build-critical tool layers (e.g., uv image) to stabilize cache.

7) Use build cache:
   - enable BuildKit caching for dependency installs (uv/pip caches) to reduce rebuild time.

**Acceptance criteria (P2):**
- Rebuilding ingestion after a code-only change does not reinstall all dependencies.

## Rollout Plan

1) Implement profiles + depends cleanup (P0).
2) Verify ingestion core: bring up core mode and run a small ingestion smoke test.
3) Add Make targets + docs (P1).
4) Optional build caching work (P2) if rebuild time is still a major blocker.

## Risks / Notes

- Some services may implicitly rely on others (e.g., bot → litellm). If so, keep them together in the same profile, but do not force `langfuse` into `bot` mode.
- Compose `deploy:` resource limits do not reliably apply outside Swarm. If memory pressure causes slow startups, enforce limits via Docker Desktop/WSL settings or explicit runtime flags.
