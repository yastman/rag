# Langfuse Real-Env OTEL Fix — 2026-05-07

## Problem

Real `make bot` startup reached polling, but Langfuse OTEL export to `http://localhost:3001/api/public/otel/v1/traces` returned HTTP 401 with an underlying Prisma database-authentication error (`Authentication failed against database server`).

## Root Cause

Langfuse `web` and `worker` containers were running with a stale `DATABASE_URL` that contained a fixture/test Postgres password (`<redacted>`). The running Postgres container was initialized with a different password (`<redacted>`), so Prisma connections from Langfuse failed with P1000 auth errors. Because Langfuse could not reach its own database, the OTEL ingestion endpoint returned 401.

## Fix Applied

1. **Created a local `.env` symlink** (untracked) pointing to the real environment file:
   ```bash
   ln -s /home/user/projects/rag-fresh/.env .env
   ```

2. **Aligned Postgres password non-destructively** via `ALTER USER` so the running Postgres container accepted the real password. The password value was not written to the report.

3. **Recreated Langfuse web and worker containers** using the real env file:
   ```bash
   docker compose --env-file /home/user/projects/rag-fresh/.env -f compose.yml -f compose.dev.yml up -d --force-recreate langfuse langfuse-worker
   ```
   This caused Docker Compose to pick up the correct `POSTGRES_PASSWORD` and interpolate `DATABASE_URL` consistently across Postgres, Langfuse web, and Langfuse worker.

## Verification

| Check | Result |
|-------|--------|
| Langfuse health (`http://127.0.0.1:3001/api/public/health`) | `200 OK` |
| Langfuse web logs — no Prisma P1000 / auth failures | Pass |
| Langfuse worker logs — no Prisma P1000 / auth failures | Pass |
| `timeout 120 make bot` reaches `Startup verdict: OK` and `Start polling` | Pass |
| `logs/bot-run.log` — no `Failed to export span batch code: 401` | Pass |
| `logs/bot-run.log` — no `Prisma` / `Authentication failed` after fix | Pass |

Bot output excerpt:
```
2026-05-07 09:58:18,431 - telegram_bot.preflight - INFO - Preflight OK: langfuse [OPTIONAL]
2026-05-07 09:58:19,636 - telegram_bot.bot - INFO - Startup verdict: OK
2026-05-07 09:58:19,638 - aiogram.dispatcher - INFO - Start polling
2026-05-07 09:58:19,978 - urllib3.connectionpool - DEBUG - http://localhost:3001 "POST /api/public/otel/v1/traces HTTP/1.1" 200 None
```

OTEL trace batch export now returns HTTP 200.

## Files Changed

- `docs/audits/2026-05-07-langfuse-real-env-otel-fix.md` (this report)

No application code or committed configuration was modified.
