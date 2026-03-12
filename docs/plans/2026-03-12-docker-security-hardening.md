# Docker Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 Docker security issues (#849, #850, #851, #852) in a single PR.

**Architecture:** Replace hardcoded passwords with env var refs, create per-service postgres users with least-privilege, harden mlflow container, add network isolation between service groups.

**Tech Stack:** Docker Compose, PostgreSQL init scripts, Dockerfile

---

### Task 1: #849 — Replace hardcoded default passwords

**Files:**
- Modify: `compose.yml` (clickhouse, minio, redis-langfuse services + langfuse-env anchor)
- Modify: `compose.dev.yml` (add dev defaults for new required vars)
- Modify: `.env.example` (document new required vars)

**Step 1: compose.yml — clickhouse password**
Replace `${CLICKHOUSE_PASSWORD:-clickhouse}` with `${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD is required}` in all occurrences (clickhouse service env + langfuse-env anchor).

**Step 2: compose.yml — minio password**
Replace `${MINIO_ROOT_PASSWORD:-miniosecret}` with `${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}` in all occurrences (minio service + langfuse-env S3 keys).

**Step 3: compose.yml — redis-langfuse password**
Replace `${LANGFUSE_REDIS_PASSWORD:-langfuseredis}` with `${LANGFUSE_REDIS_PASSWORD:?LANGFUSE_REDIS_PASSWORD is required}` in all occurrences.

**Step 4: compose.dev.yml — add dev defaults**
Add environment overrides for clickhouse, minio, redis-langfuse with safe dev defaults so `make docker-ml-up` still works without setting these vars.

**Step 5: .env.example — document vars**
Uncomment/update the 3 vars in DEV INFRASTRUCTURE section to show they're required for production.

---

### Task 2: #850 — Per-service PostgreSQL users

**Files:**
- Modify: `docker/postgres/init/00-init-databases.sql` (create per-service users + grant)
- Modify: `compose.yml` (DATABASE_URL strings for langfuse, mlflow, ingestion, bot, voice-agent)
- Modify: `compose.dev.yml` (add password env vars with dev defaults)
- Modify: `.env.example` (document new vars)

**Step 1: Rewrite 00-init-databases.sql**
Create per-service users with passwords from env vars (using `:'var'` psql syntax won't work in init scripts — use shell wrapper). Actually, postgres init scripts run as SQL, so we need a shell script approach.

Replace `00-init-databases.sql` with `00-init-databases.sh` that:
- Creates databases: langfuse, mlflow, litellm, realestate, cocoindex (move cocoindex DB creation here)
- Creates users: `langfuse_user`, `litellm_user`, `mlflow_user`, `cocoindex_user`, `realestate_user`, `voice_user`
- Each user gets CONNECT + full privileges only on their database
- Passwords come from env vars with fallback to POSTGRES_PASSWORD

**Step 2: Update compose.yml — pass per-service password env vars to postgres**
Add env vars to postgres service for per-service passwords.

**Step 3: Update compose.yml — update DATABASE_URL strings**
- langfuse-env anchor: `postgresql://langfuse_user:${LANGFUSE_DB_PASSWORD:-...}@postgres:5432/langfuse`
- mlflow: `postgresql://mlflow_user:${MLFLOW_DB_PASSWORD:-...}@postgres:5432/mlflow`
- ingestion: `postgresql://cocoindex_user:${COCOINDEX_DB_PASSWORD:-...}@postgres:5432/cocoindex`
- bot REALESTATE_DATABASE_URL: `postgresql://realestate_user:${REALESTATE_DB_PASSWORD:-...}@postgres:5432/realestate`
- voice-agent DATABASE_URL: `postgresql://voice_user:${VOICE_DB_PASSWORD:-...}@postgres:5432/postgres`

**Step 4: compose.dev.yml — dev defaults for DB passwords**
Add env overrides with dev defaults so local dev works without extra config.

---

### Task 3: #851 — MLflow hardening

**Files:**
- Modify: `docker/mlflow/Dockerfile` (non-root user, remove root pip cache mount)
- Modify: `compose.yml` (mlflow: resource limits, logging, security)

**Step 1: Dockerfile — non-root user**
Add `RUN useradd -r -s /bin/false mlflow` and `USER mlflow`. Fix pip cache mount to user dir.

**Step 2: compose.yml — resource limits + logging**
Add `deploy.resources.limits.memory: 512M`, `logging: *default-logging`, and security defaults to mlflow service.

---

### Task 4: #852 — Network isolation

**Files:**
- Modify: `compose.yml` (define networks, attach per-service)

**Network design:**
- `backend` — core services: postgres, redis, qdrant, bge-m3, user-base, docling, litellm, bot, mini-app-api, mini-app-frontend, ingestion, rag-api
- `langfuse` — langfuse stack: postgres, clickhouse, minio, redis-langfuse, langfuse, langfuse-worker (+ litellm for OTEL)
- `monitoring` — loki, promtail, alertmanager
- `voice` — livekit-server, livekit-sip, voice-agent, rag-api, redis (livekit-sip needs redis)

Services on multiple networks: postgres (backend + langfuse), litellm (backend + langfuse), redis (backend + voice), rag-api (backend + voice).

---

### Task 5: Validation

**Step 1:** `docker compose -f compose.yml config --quiet` — base validates
**Step 2:** `docker compose -f compose.yml -f compose.dev.yml config --quiet` — dev validates
**Step 3:** `docker compose -f compose.yml -f compose.vps.yml config --quiet` — vps validates
