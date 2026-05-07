# Docker / Langfuse Health Audit Report

**Date:** 2026-05-07
**Auditor:** W-audit-docker-langfuse-health
**Worktree:** `/home/user/projects/rag-fresh-wt-audit-docker-langfuse-health`
**Branch:** `audit/docker-langfuse-health`
**Stack:** `COMPOSE_FILE=compose.yml:compose.dev.yml` (project `dev`)

---

## Executive Summary

The local `dev` Docker stack is in a critical restart-loop for Langfuse and all Python-based RAG services. The root cause is **not a single runtime failure but a cascade of three independent configuration and image drifts that were exposed when the WSL VM restarted at ~08:13 UTC today** (system uptime 33 min at time of audit). Prior to the restart the stack may have been running from older container state; after the restart the current containers resumed with their latent defects and began crashing immediately.

The three drifts, in order of impact:

1. **Stale custom images (primary Langfuse-adjacent blocker):** `dev_bot`, `dev_mini-app-api`, and `dev_rag-api` images were built on **2026-04-17 with Python 3.14.4** and contain the `langfuse` v4 SDK. Current Dockerfiles were downgraded to **Python 3.13** on 2026-05-05 (commit `546fba07`) specifically because `langfuse` v4 exercises Pydantic v1 code that crashes under Python 3.14 (`pydantic.v1.errors.ConfigError: unable to infer type for attribute "description"`). **The images were never rebuilt after the downgrade.** Every Python service that imports `telegram_bot.observability` (which imports `langfuse`) dies within 1–5 seconds of startup.

2. **Postgres data volume password mismatch (Langfuse web/worker blocker):** The `dev_postgres_data` volume was initialized on **2026-03-05** with a password from an older environment. On 2026-05-05 new containers were created using the current `tests/fixtures/compose.ci.env` password (`test-postgres-password`), but Postgres ignores `POSTGRES_PASSWORD` when data already exists. Langfuse web and worker therefore receive `DATABASE_URL` containing the current env password, which is rejected by the actual database over the Docker network (verified by TCP test from a transient container on `dev_default`). This produces Prisma error `P1000: Authentication failed ... the provided database credentials for postgres are not valid`.

3. **Langfuse v3.172.1 secret validation failure (Langfuse web/worker blocker):** The `ENCRYPTION_KEY`, `SALT`, and `NEXTAUTH_SECRET` values in the running container env are 19, 9, and 20 characters respectively. Langfuse v3.172.1 validates `ENCRYPTION_KEY` at exactly 64 hex characters (256 bits) and fails on startup with a Zod schema error before it even attempts to serve traffic.

These three issues together mean **Langfuse web, Langfuse worker, bot, mini-app-api, and rag-api are all completely non-functional.** The dependency layer (Postgres, ClickHouse, Redis, MinIO, Qdrant, LiteLLM) is healthy, but the application layer cannot start.

---

## Langfuse v3 Architecture: Why Both Web and Worker Exist

Langfuse v3 self-hosted requires **two runtime containers** plus four dependencies:

- **`langfuse` (web):** Serves the UI at `:3000`, handles HTTP API requests, runs Prisma migrations on startup, and writes event batches to S3/MinIO and ClickHouse.
- **`langfuse-worker`:** Processes asynchronous background jobs (e.g., scoring, exports, ingestion pipeline) and reads/writes the same Postgres, ClickHouse, Redis, and MinIO backends.

Both containers are mandatory. The web container cannot process heavy background work at scale without the worker, and the worker cannot serve the UI. In this stack both are present and expected; the problem is that **both fail during initialization** (Prisma migration for web, env validation for worker) and therefore neither role is operational.

---

## Service Status Table

| Service / Container | Status | Health | Ports | Critical Log Error | Suspected Root Cause | Fix Recommendation |
|---|---|---|---|---|---|---|
| **dev_langfuse_1** | Restarting (1) | N/A | `127.0.0.1:3001->3000` | `P1000: Authentication failed against database server ... credentials for postgres are not valid` | Postgres data volume has old password; `DATABASE_URL` env does not match actual DB password over TCP | Reset `dev_postgres_data` volume or align `POSTGRES_PASSWORD` with existing DB password; also fix secrets |
| **dev_langfuse-worker_1** | Restarting (1) | N/A | — | `ZodError: ENCRYPTION_KEY must be 256 bits, 64 string characters in hex format` | `ENCRYPTION_KEY` env is 19 chars (needs 64 hex) | Generate `openssl rand -hex 32` and set in `.env` or `compose.ci.env` |
| **dev_bot_1** | Restarting (1) | N/A | — | `pydantic.v1.errors.ConfigError: unable to infer type for attribute "description"` | Stale `dev_bot` image built with Python 3.14; `langfuse` v4 incompatible with Pydantic v1 on 3.14 | Rebuild image (`docker compose build bot`) after Dockerfile downgrade to 3.13 |
| **dev_mini-app-api_1** | Restarting (1) | N/A | `127.0.0.1:8090->8090` | Same pydantic error as bot | Stale `dev_mini-app-api` image (Python 3.14) | Rebuild image (`docker compose build mini-app-api`) |
| **dev_rag-api_1** | Exited (1) 5 days ago | N/A | — | Same pydantic error (from earlier logs) | Stale `dev_rag-api` image (Python 3.14) | Rebuild image; note container is currently stopped, not restarting |
| **dev_postgres_1** | Up 21 min | healthy | `127.0.0.1:5432->5432` | None visible | Data volume password mismatch is latent, not fatal to Postgres itself | Align credentials or reset volume |
| **dev_clickhouse_1** | Up 21 min | healthy | `127.0.0.1:8123->8123`, `9009` | None | — | — |
| **dev_minio_1** | Up 21 min | healthy | `127.0.0.1:9090->9000`, `9091` | None | — | — |
| **dev_redis-langfuse_1** | Up 21 min | healthy | `127.0.0.1:6380->6379` | None | — | — |
| **dev_redis_1** | Up 21 min | healthy | `127.0.0.1:6379->6379` | None | — | — |
| **dev_litellm_1** | Up 21 min | healthy | `127.0.0.1:4000->4000` | None | — | — |
| **dev_qdrant_1** | Up 21 min | healthy | `127.0.0.1:6333-6334` | None | — | — |
| **dev_docling_1** | Up 21 min | healthy | `127.0.0.1:5001->5001` | None | — | — |
| **dev_user-base_1** | Up 21 min | healthy | `127.0.0.1:8003->8000` | None | — | — |
| **dev-bge-m3-1** | Up 21 min | healthy | `127.0.0.1:8000->8000` | None | — | — |
| **dev_mini-app-frontend_1** | Created | N/A | — | Not started | Likely held by failing backend dependency or missing build step | Start after backend is healthy |
| **dev_voice-agent_1** | Created | N/A | — | Not started | Expected: voice/LiveKit is off by default per project policy | No action required |
| **dev_livekit-server_1** | Exited (0) 6 days ago | N/A | — | Not started | Expected: voice/LiveKit is off by default | No action required |
| **dev_livekit-sip_1** | Exited (0) 6 days ago | N/A | — | Not started | Expected: voice/LiveKit is off by default | No action required |
| **dev-loki-1** | Exited (0) 2 weeks ago | N/A | — | Not started | Optional monitoring, not a current blocker | Start if observability is needed |
| **dev-promtail-1** | Exited (0) 2 weeks ago | N/A | — | Not started | Optional monitoring | Start if needed |
| **dev-mlflow-1** | Exited (137) 6 weeks ago | N/A | — | Not started | Optional / removed from stack | No action required |

---

## Evidence and Commands Used

All commands below were read-only; no containers were restarted, removed, or modified during the audit.

### 1. Discovery of missing `.env` and compose parse failure
```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
# Result: error while interpolating services.bot.environment.REDIS_URL: required variable REDIS_PASSWORD is missing a value: REDIS_PASSWORD is required
```
There is **no `.env` file** in the current worktree. The running containers were created from a different worktree (`/home/user/projects/rag-fresh-wt-fix-1380-validate-traces-native/`) using `tests/fixtures/compose.ci.env` as the environment file (confirmed by container labels).

### 2. Container status and restart counts
```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker inspect dev_langfuse_1 --format='Created: {{.Created}}\nStarted: {{.State.StartedAt}}\nRestartCount: {{.RestartCount}}'
docker inspect dev_bot_1 --format='Created: {{.Created}}\nStarted: {{.State.StartedAt}}\nRestartCount: {{.RestartCount}}'
```
- `dev_langfuse_1`: Created 2026-05-05T17:27:11Z, Started 2026-05-07T08:39:53Z, **RestartCount: 33**
- `dev_bot_1`: Created 2026-05-05T17:27:10Z, Started 2026-05-07T08:38:42Z, **RestartCount: 33**
- `dev_postgres_1`: Created 2026-05-05T17:27:10Z, Started 2026-05-07T08:14:13Z, **RestartCount: 0**

System uptime was **33 minutes** at audit time, confirming a WSL/VM restart at ~08:13 UTC. After the restart, containers with latent defects resumed and entered their crash loops.

### 3. Langfuse worker env validation failure
```bash
docker logs --tail 120 dev_langfuse-worker_1
```
Repeating error:
```
ZodError: [
  {
    "code": "too_small",
    "minimum": 64,
    "exact": true,
    "path": ["ENCRYPTION_KEY"],
    "message": "ENCRYPTION_KEY must be 256 bits, 64 string characters in hex format, generate via: openssl rand -hex 32"
  }
]
```

### 4. Langfuse web database authentication failure
```bash
docker logs --tail 120 dev_langfuse_1
```
Repeating error:
```
Error: P1000: Authentication failed against database server, the provided database credentials for `postgres` are not valid.
Prisma schema loaded from packages/shared/prisma/schema.prisma
Datasource "db": PostgreSQL database "langfuse", schema "public" at "postgres:5432"
```

### 5. Postgres password mismatch verification
```bash
docker volume inspect dev_postgres_data --format='{{.CreatedAt}}'
# 2026-03-05T14:23:08Z  (two months older than containers)

docker exec -i dev_postgres_1 psql "postgresql://postgres:test-postgres-password@localhost:5432/langfuse" -c "SELECT 1;"
# Succeeds because localhost is trust-authenticated (pg_hba.conf: host all all 127.0.0.1/32 trust)

docker run --rm --network dev_default postgres:17-alpine \
  psql "postgresql://postgres:test-postgres-password@postgres:5432/langfuse" -c "SELECT 1;"
# FAILS: FATAL:  password authentication failed for user "postgres"
```
This proves the env password does **not** match the actual database password over the Docker network.

### 6. Langfuse secret length inspection
```bash
docker inspect dev_langfuse_1 --format='{{range .Config.Env}}{{println .}}{{end}}' | grep -E 'ENCRYPTION_KEY|SALT|NEXTAUTH_SECRET' | awk -F= '{print $1 "=" length($2) " chars"}'
# ENCRYPTION_KEY=19 chars
# SALT=9 chars
# NEXTAUTH_SECRET=20 chars
```

### 7. Python 3.14 / Pydantic v1 incompatibility in custom images
```bash
docker run --rm --entrypoint '' dev_bot python --version
# Python 3.14.4

docker run --rm dev_bot python -c "import langfuse"
# pydantic.v1.errors.ConfigError: unable to infer type for attribute "description"
```
Same crash confirmed for `dev_mini-app-api` and `dev_rag-api`.

### 8. Dockerfile vs image drift (git evidence)
```bash
git log --oneline -5 -- telegram_bot/Dockerfile
# 546fba07 fix(docker): downgrade langfuse-importing runtimes from Python 3.14 to 3.13
# cb3ceda2 fix(docker,python): align Dockerfiles and static analysis with Python 3.14

git show 546fba07 --stat
# Explicitly downgrades builder and runtime images to 3.13 because langfuse SDK v4 crashes under 3.14

docker images dev_bot --format '{{.Repository}} {{.CreatedAt}}'
# dev_bot:latest 2026-04-17 10:51:27 +0000 UTC
```
The Dockerfile was fixed on May 5, but **no rebuild occurred**.

### 9. Dependency upgrade timeline
```bash
git show 1404df3a -- pyproject.toml | grep langfuse
# -    "langfuse>=3.14.0,<4.0",
# +    "langfuse>=4.0.0,<5.0",
```
Commit `1404df3a` (2026-04-17 15:14) upgraded the Python constraint to `langfuse>=4.0.0`. The v4 SDK exercises Pydantic v1 compatibility code that is incompatible with Python 3.14.

### 10. Health probes
```bash
curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:3001/api/public/health
# 000 (unreachable; langfuse is restarting)

curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:8123/ping
# 200 (ClickHouse healthy)
```

### 11. Disk usage
```bash
docker system df
# Images: 67 total, 76.15GB (53.11GB reclaimable)
# Containers: 26 total, 44.57MB
# Local Volumes: 23 total, 18.56GB (6.17GB reclaimable)
```
Disk is not critically full; space is not the blocker.

### 12. Git diff check
```bash
git diff --check
# No whitespace errors in current worktree.
```

---

## Fix Plan

### Immediate (blocks any local development)
1. **Rebuild Python images**
   ```bash
   docker compose -f compose.yml -f compose.dev.yml build bot mini-app-api rag-api
   ```
   The Dockerfiles already specify Python 3.13; the images just need to be rebuilt.

2. **Fix Langfuse secrets**
   Generate proper values and place them in `.env` (or `tests/fixtures/compose.ci.env` if that fixture is used for local dev):
   ```bash
   openssl rand -base64 32   # NEXTAUTH_SECRET
   openssl rand -base64 32   # SALT
   openssl rand -hex 32      # ENCRYPTION_KEY (64 hex chars)
   ```
   Note: `ENCRYPTION_KEY`, `SALT`, and `NEXTAUTH_SECRET` are required variables per `compose.yml`.

3. **Fix Postgres password mismatch**
   Two options:
   - **Option A (destructive, fast):** Remove the stale volume and let Postgres re-initialize with the current password:
     ```bash
     docker compose -f compose.yml -f compose.dev.yml stop postgres
     docker volume rm dev_postgres_data
     docker compose -f compose.yml -f compose.dev.yml up -d postgres
     ```
     *Warning: this deletes all local Postgres data (including the `langfuse` DB, Qdrant metadata, LiteLLM config, etc. if shared).*
   - **Option B (preservative):** Connect to Postgres and `ALTER USER postgres WITH PASSWORD 'test-postgres-password';` to align the DB with the current env, then restart Langfuse.

4. **Create `.env` file**
   Copy `.env.example` to `.env` and fill in all required variables (at minimum: `REDIS_PASSWORD`, `CLICKHOUSE_PASSWORD`, `MINIO_ROOT_PASSWORD`, `POSTGRES_PASSWORD`, `ENCRYPTION_KEY`, `SALT`, `NEXTAUTH_SECRET`, `LITELLM_MASTER_KEY`, `TELEGRAM_BOT_TOKEN`, `GDRIVE_SYNC_DIR`).

### Follow-up
5. **Add image-staleness guard to local workflow**
   The commit `546fba07` already added a static test preventing Python 3.14 reintroduction, but there is no automated check that warns when a local image is older than its Dockerfile. Consider adding a `make local-up` pre-flight step that compares image build timestamps to Dockerfile mtime or runs `docker compose build --pull` when the image is stale.

6. **Document worktree isolation for Docker**
   Because all worktrees use `COMPOSE_PROJECT_NAME=dev` (added in commit `59a2acff`), containers created from one worktree can shadow or conflict with another. The current containers were created from `rag-fresh-wt-fix-1380-validate-traces-native`, not the current audit worktree. Developers should be aware that `docker compose` commands from different worktrees target the same container set.

---

## Commands Skipped

- `docker compose up/down/restart/rm/volume rm/system prune` — skipped per read-only audit contract.
- `make check` — skipped per prompt instruction (audit-only, no code checks).
- LiveKit/voice health probes — skipped per prompt (expected off).

---

## Variable Names Affected (Secret Values Redacted)

The following environment variables are required by `compose.yml` but are either missing from the current shell environment or have invalid placeholder values:

- `REDIS_PASSWORD`
- `CLICKHOUSE_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `POSTGRES_PASSWORD`
- `ENCRYPTION_KEY`
- `SALT`
- `NEXTAUTH_SECRET`
- `LITELLM_MASTER_KEY`
- `TELEGRAM_BOT_TOKEN`
- `GDRIVE_SYNC_DIR`

Langfuse-specific additional variables:
- `DATABASE_URL` (derived from `POSTGRES_PASSWORD`)
- `LANGFUSE_REDIS_PASSWORD`
- `REDIS_AUTH`

---

## Conclusion

The `dev` stack is non-functional because of **stale images + stale volume password + invalid secrets**, all exposed by a WSL restart. The dependency layer is healthy, so fixing the three drifts above should restore the full stack. The most important single action is **rebuilding the Python images** (to resolve the Python 3.14/langfuse v4 crash) and **aligning the Postgres credentials** (to allow Langfuse web/worker to start).
