# Telegram Bot Runtime Logs Audit — 2026-05-07

**Scope:** Local `dev` Compose stack (`compose.yml:compose.dev.yml`)
**Containers inspected:** `dev_bot_1`, `dev_mini-app-api_1`, `dev_langfuse_1`, `dev_langfuse-worker_1`, `dev_litellm_1`, `dev_postgres_1`, `dev_user-base_1`
**Method:** Read-only `docker logs --tail`, `docker inspect`, `docker ps`, `rg`, bounded source reads.
**Redaction:** Tokens, API keys, chat IDs, and personal data are redacted.

---

## Executive Summary

The Telegram bot and the related mini-app API are both in a **crash-loop** (≈27–28 restarts each). The RAG chatbot stack is **non-functional** because the bot container cannot start. There are three distinct root causes, all fixable without code changes (Docker image rebuild + environment alignment).

| # | Root Cause | Affected Services | Fix Category |
|---|------------|-------------------|--------------|
| 1 | **Stale Docker image with Python 3.14** — langfuse SDK v4 → pydantic v1 incompatibility | `bot`, `mini-app-api` | Docker rebuild |
| 2 | **Postgres password mismatch** (persistent volume initialized with a different password than current env) | `langfuse` | Env / volume reset |
| 3 | **`ENCRYPTION_KEY` too short** for Langfuse 3.172.1 (needs 64 hex chars) | `langfuse-worker` | Env fix |

---

## 1. Bot & Mini-App-API: Python 3.14 × Pydantic V1 Crash on Startup

### Evidence

`dev_bot_1` logs (every start, identical stack trace):

```
UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.
pydantic.v1.errors.ConfigError: unable to infer type for attribute "description"
```

Stack trace points through:
- `telegram_bot/main.py:22` → `telegram_bot/bot.py:41` → `telegram_bot/integrations/cache.py:32` → `telegram_bot/observability.py:18` → `langfuse` import

`dev_mini-app-api_1` shows the **identical** crash.

### Root-Cause Analysis

1. **Running image is stale.** The `dev_bot` image was built on **2026-04-17** (`docker inspect` → `2026-04-17T10:51:27Z`).
2. The current `telegram_bot/Dockerfile` (commit `546fba07`, 2026-05-05) pins the runtime to `python:3.13-slim-bookworm`, but the **running container reports `PYTHON_VERSION=3.14.4`**.
3. The code inside the container is also older than the current branch: the container’s `observability.py` has the unguarded `from langfuse import Langfuse` at line 18, whereas the current source (commit `1f71f78c`, 2026-05-01) wraps that import in `try/except` with no-op fallbacks.
4. Langfuse SDK v4 (installed in the image) internally uses `pydantic.v1`, which is **known to fail under Python 3.14**.

### Frequency
- **100 % of starts** — bot has restarted **27 times** since container creation (`docker inspect dev_bot_1` → `RestartCount: 27`, last started 2026-05-07T08:33:18Z).
- Mini-app-api has restarted **28 times**.

### Category
**Docker dependency / image staleness issue** — not a live bot-code bug. The code fixes (import guard + Dockerfile downgrade) already exist in `dev`; they were simply never rebuilt locally.

### Recommended Fix
1. `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose build bot mini-app-api`
2. `docker compose up -d --force-recreate bot mini-app-api`

---

## 2. Langfuse Web: Database Authentication Failure (P1000)

### Evidence

`dev_langfuse_1` logs repeat:

```
Error: P1000: Authentication failed against database server,
the provided database credentials for `postgres` are not valid.
```

Prisma tries to connect to `postgresql://postgres:<password>@postgres:5432/langfuse`.

The `langfuse` database **does exist** and is reachable from the postgres container itself (`SELECT 1` succeeds), but Prisma inside the Langfuse container rejects the credentials over TCP.

### Root-Cause Analysis

- Postgres container env: `POSTGRES_PASSWORD=<redacted>` (short placeholder).
- Langfuse `DATABASE_URL` contains the same placeholder password.
- Postgres is using `scram-sha-256` for host connections (`pg_hba.conf`).
- The postgres data is stored in a **named volume** (`dev_postgres_data`). If the volume was first initialized with a different password (e.g., an older default from `compose.dev.yml`), changing the env var later does **not** update the already-hashed password in the volume.
- This explains why local `trust` connections work but password-over-TCP connections fail.

### Category
**External access / environment configuration issue** (persistent volume drift).

### Recommended Fix
1. Verify the actual postgres password from inside the container over TCP, **or**
2. Reset the postgres volume (destructive to local dev data):
   ```bash
   docker compose down
   docker volume rm dev_postgres_data
   docker compose up -d postgres
   ```
3. Then recreate Langfuse so migrations run with the fresh password.

---

## 3. Langfuse Worker: Invalid ENCRYPTION_KEY Length

### Evidence

`dev_langfuse-worker_1` logs:

```
ZodError: [
  {
    "path": [ "ENCRYPTION_KEY" ],
    "message": "ENCRYPTION_KEY must be 256 bits, 64 string characters in hex format,
                generate via: openssl rand -hex 32"
  }
]
```

Current env value: `ENCRYPTION_KEY=<redacted>` (non-64-hex placeholder, 20 characters).

### Root-Cause Analysis

Langfuse `3.172.1` enforces a strict 64-character hex `ENCRYPTION_KEY`. The test fixture (`tests/fixtures/compose.ci.env`) sets `ENCRYPTION_KEY=<redacted>` (non-64-hex placeholder), which satisfies the `?required` interpolation but fails Langfuse’s runtime validation.

### Category
**External access / secrets configuration issue**.

### Recommended Fix
1. Generate a compliant key: `openssl rand -hex 32`
2. Update `.env` / `compose.ci.env` / local env export with the 64-char hex value.
3. Recreate `langfuse` and `langfuse-worker`.

---

## 4. Langfuse Worker: Will Also Hit DB Auth Issue

Once the `ENCRYPTION_KEY` is fixed, the worker will encounter the **same P1000 database authentication failure** as the web container because both share the same `DATABASE_URL` and postgres password mismatch.

---

## Recommended Fix Order

1. **Regenerate `ENCRYPTION_KEY`** and update local env / `.env`.
2. **Align postgres password** with the actual password in `dev_postgres_data`, or reset the volume.
3. **Rebuild bot & mini-app-api images** so they pick up the `python:3.13` runtime and the latest `observability.py` import guard.
4. **Recreate all affected containers** (`bot`, `mini-app-api`, `langfuse`, `langfuse-worker`).
5. **Verify stack health**:
   ```bash
   COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps
   docker logs --tail 20 dev_bot_1
   ```

---

## Issue Disposition

| Issue | Disposition | Reason |
|-------|-------------|--------|
| Python 3.14 stale image (bot, mini-app-api) | `autofix_current_task` | Local dev environment fix; Dockerfile and guard already committed |
| Postgres password drift | `autofix_current_task` | Local env/volume reset; no code change needed |
| ENCRYPTION_KEY too short | `autofix_current_task` | Local env update; fixture may need update for CI parity |

No new product bugs were found in the current branch code. The failures are **runtime-environment issues** (stale images + env drift) rather than logic defects in the bot or RAG pipeline.

---

## Appendix: Command Evidence

- `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility ps` — revealed `dev_bot_1`, `dev_mini-app-api_1`, `dev_langfuse_1`, `dev_langfuse-worker_1` all in `Restarting` state.
- `docker logs --tail 300 dev_bot_1` — showed identical pydantic crash on every restart.
- `docker inspect dev_bot --format '{{.Created}}'` — image created `2026-04-17`.
- `docker run --rm dev_bot python --version` — `Python 3.14.4` despite `Dockerfile` pinning `3.13`.
- `docker inspect dev_langfuse_1 --format '{{range .Config.Env}}{{.}}{{"\n"}}{{end}}'` — `ENCRYPTION_KEY=<redacted>`.
- `docker logs --tail 50 dev_langfuse_1` — repeated Prisma `P1000` auth failure.
- `docker exec dev_postgres_1 psql -U postgres -d langfuse -c "SELECT 1"` — DB exists and local trust connections work.
- `docker inspect dev_postgres_1` — mounts persistent volume `dev_postgres_data`.
