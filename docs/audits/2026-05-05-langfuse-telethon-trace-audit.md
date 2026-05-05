# Local Langfuse + Telegram/Telethon Bot Trace Coverage Audit

**Date:** 2026-05-05
**Branch:** `audit/1307-langfuse-telethon`
**Worker:** `W-audit-1307-langfuse-telethon`
**Scope:** Local-only verification of Langfuse stack health, bot trace path, and Telethon E2E readiness.

---

## 1. Runbook

### Local commands used
| Command | Purpose |
|---------|---------|
| `make docker-ps` | Verify local Docker service status |
| `make test-bot-health` | Preflight: Redis, Postgres, Qdrant, LiteLLM |
| `curl -fsS http://localhost:3001/api/public/health` | Langfuse UI/API health probe |
| `curl -fsS http://localhost:4000/health/readiness` | LiteLLM proxy health probe |
| `curl -fsS http://localhost:6333/collections` | Qdrant collection list |
| `curl -fsS http://localhost:8000/health` | BGE-M3 embedding service health |
| `make validate-traces-fast` | Trace validation via LangGraph pipeline (skipped — see §5) |
| `make e2e-telegram-test` | Telegram userbot E2E runner (skipped — see §4) |
| `make check` | Lint + type-check gate |

### Environment keys required (names only)
- **Langfuse:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- **Redis:** `REDIS_PASSWORD` (required because local Redis uses `--requirepass`)
- **Qdrant / BGE-M3 / LiteLLM:** Defaults work when services are up; overrides needed for native execution outside Docker network
- **Telegram E2E:** `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, plus an `e2e_tester.session` file
- **Bot runtime:** `TELEGRAM_BOT_TOKEN`, `LLM_API_KEY`
- **Trace validation:** Same as above plus `QDRANT_URL`, `BGE_M3_URL`, `REDIS_URL`, `LLM_BASE_URL` when run natively

### Expected services
All services are running under Docker Compose project `dev` (from `compose.yml:compose.dev.yml`):
- `dev_langfuse_1` (UI/API on `:3001`)
- `dev_langfuse-worker_1`
- `dev_clickhouse_1`
- `dev_minio_1`
- `dev_litellm_1` (proxy on `:4000`)
- `dev_qdrant_1` (REST on `:6333`)
- `dev_bge-m3-1` (REST on `:8000`)
- `dev_redis_1` (password-protected on `:6379`)
- `dev_redis-langfuse_1`
- `dev_postgres_1`
- `dev_docling_1`
- `dev_user-base_1`

### Rollback / stop policy
- **Do not** stop or delete Docker services or volumes.
- No production env, credentials, or sessions were read or committed.
- If a command fails, record the blocker and move on; do not loop.

---

## 2. Health Checks

### `make docker-ps`
**Status:** PASSED
All 12 relevant containers are `Up` and `healthy`.

### `make test-bot-health`
**Status:** PASSED (with `REDIS_PASSWORD` supplied)
- Redis auth: OK
- Postgres: skipped (DSN points to `postgres:5432` — expected for native runs)
- Qdrant collection `gdrive_documents_bge`: exists
- LiteLLM readiness: OK (`http://localhost:4000/health/readiness`)

**Note:** Without `REDIS_PASSWORD`, the script fails with `redis.exceptions.AuthenticationError` because local Redis is started with `--requirepass`. The root `.env` file is absent, so `BotConfig` falls back to `redis://localhost:6379` with no password.

### Direct HTTP probes
| Endpoint | Result |
|----------|--------|
| `http://localhost:3001/api/public/health` | `{"status":"OK","version":"3.172.1"}` |
| `http://localhost:4000/health/readiness` | `{"status":"healthy", ...}` |
| `http://localhost:6333/collections` | `gdrive_documents_bge`, `apartments`, `conversation_history` |
| `http://localhost:8000/health` | `{"status":"ok","model_loaded":true,"warmed_up":true}` |

---

## 3. Langfuse API / Readability

### Auth probe
**Status:** PASSED
Local Langfuse accepts the dev credentials documented in `.env.example` (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`).

### Create → flush → read-back test
**Status:** PASSED
A test trace was created via the Python SDK (`langfuse==4.3.1`) with:
- Unique trace ID generated via `uuid.uuid4()`
- Observation name `audit-1307-test-trace`
- Custom input/output metadata

The trace was flushed and successfully read back via `lf.api.trace.get(trace_id)` within 1 second.

### Existing traces in Langfuse
The local instance already contains traces from previous activity:
- `litellm-acompletion` traces (orphaned — see #1362)
- `validation-query` traces from the `scripts/validate_traces.py` run (see §5)

---

## 4. Telethon / Bot E2E

### Required env inspection
`scripts/e2e/config.py` requires:
- `TELEGRAM_API_ID` (int)
- `TELEGRAM_API_HASH` (str)
- `ANTHROPIC_API_KEY` (str, unless `--no-judge`)
- `E2E_BOT_USERNAME` (defaults to `@test_nika_homes_bot`)

### Session inspection
`scripts/e2e/telegram_client.py` uses `TelegramClient("e2e_tester", ...)` which expects an on-disk session file `e2e_tester.session` (or a `StringSession` if configured).

### Blocker
**`make e2e-telegram-test` was SKIPPED.**
- `TELEGRAM_API_ID` is not set in the shell environment.
- `TELEGRAM_API_HASH` is not set.
- No `e2e_tester.session` file exists in the worktree.
- Per the task constraints, we do **not** force-create an interactive Telegram session.

---

## 5. Trace Validation

### `make validate-traces-fast`
**Status:** PARTIAL / BLOCKED by hostname mismatch
Running the Makefile target natively fails at Qdrant collection discovery because `GraphConfig.from_env()` defaults to Docker-internal hostnames (`http://qdrant:6333`).

After overriding the following env vars for native execution, the script proceeds:
- `QDRANT_URL=http://localhost:6333`
- `BGE_M3_URL=http://localhost:8000`
- `REDIS_URL=redis://:dev_redis_pass@localhost:6379`
- `LLM_BASE_URL=http://localhost:4000`
- `LLM_API_KEY=no-key` (LiteLLM proxy accepts this locally)
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

**Observed behavior:**
- The LangGraph pipeline executes real RAG queries.
- Traces are written to Langfuse (confirmed: `validation-query` traces visible in API).
- Streaming phase encounters `AttributeError: 'FakeMessage' object has no attribute 'chat'` and falls back to non-streaming (see #1379).
- The full run takes **> 3 minutes** (killed by `timeout 180` before report generation).

**Verdict:** The trace-write path is functional end-to-end, but the `make validate-traces-fast` target is not actually "fast" and is not runnable out-of-the-box without native URL overrides.

### `make e2e-test-traces`
**Status:** SKIPPED
Depends on `make e2e-telegram-test`, which is blocked by missing Telegram credentials.

---

## 6. Findings

### Confirmed bugs / gaps (new issues created)

| # | Issue | Title | Blocks #1307? |
|---|-------|-------|---------------|
| 1379 | [yastman/rag#1379](https://github.com/yastman/rag/issues/1379) | `FakeMessage` lacks `chat` attribute breaking streaming TTFT validation | Partially — skews TTFT metrics |
| 1380 | [yastman/rag#1380](https://github.com/yastman/rag/issues/1380) | `make validate-traces-fast` fails natively because `GraphConfig` defaults to Docker hostnames | Yes — breaks local validation workflow |
| 1381 | [yastman/rag#1381](https://github.com/yastman/rag/issues/1381) | Langfuse SDK 4.3.1 emits Pydantic V1 warning on Python 3.14 | No — noise only |

### Confirmed bugs / gaps (already tracked)

| # | Issue | Observation |
|---|-------|-------------|
| 1362 | [yastman/rag#1362](https://github.com/yastman/rag/issues/1362) | Orphaned `litellm-acompletion` traces visible in local Langfuse API — confirmed present. |
| 1367 | [yastman/rag#1367](https://github.com/yastman/rag/issues/1367) | Audit scope focused on bot core path; ingestion/retrieval blind spots were not exercised but remain valid. |
| 1369 | [yastman/rag#1369](https://github.com/yastman/rag/issues/1369) | Duplicate `detect-agent-intent` and WARNING-level spans were not directly triggered in this session. |

### Environment blockers (not product bugs)

| Blocker | Reason | Variable(s) |
|---------|--------|-------------|
| Telegram E2E cannot run | Missing local credentials and session file | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `e2e_tester.session` |
| No root `.env` file | Local dev setup incomplete; `make test-bot-health` fails on Redis auth without manual override | `REDIS_PASSWORD` |
| `LLM_API_KEY` not set | LiteLLM proxy accepts `no-key` locally, so not a hard blocker for validation | `LLM_API_KEY` |

### What works
1. Langfuse UI/API is healthy on `http://localhost:3001`.
2. Langfuse dev keys authenticate and allow create/read trace operations.
3. The LangGraph RAG pipeline creates readable traces in Langfuse when executed.
4. All core Docker services (Qdrant, Redis, BGE-M3, LiteLLM, Postgres) are healthy.
5. Bot health preflight passes when Redis password is supplied.

### What is blocked or degraded
1. **Telegram E2E path:** Missing API ID/hash + session file.
2. **Native trace validation:** Hostname defaults assume Docker network; requires 4+ env overrides.
3. **Streaming TTFT validation:** `FakeMessage.chat` missing causes fallback to non-streaming.
4. **Validation runtime:** Full `validate_traces.py` run exceeds 3 minutes, making the "fast" target a misnomer.

---

## 7. Recommendations

1. **Fix #1380** so `make validate-traces-fast` works natively without manual hostname overrides (e.g., run inside the bot container or detect native mode).
2. **Fix #1379** so streaming TTFT is actually measured during validation.
3. **Document** the exact minimal `.env` needed for local bot health checks (at minimum `REDIS_PASSWORD=dev_redis_pass`).
4. **Update** `docs/LOCAL-DEVELOPMENT.md` to clarify that Telegram E2E requires `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and a pre-created Telethon session.
5. **Monitor** Langfuse SDK releases for Python 3.14 Pydantic V2 compatibility (#1381).

---

*Report generated by `W-audit-1307-langfuse-telethon` on 2026-05-05.*
