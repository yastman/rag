# Telethon-Langfuse Runtime Loop Audit

**Date:** 2026-05-08
**Branch:** `runtime/1307-telethon-langfuse-loop-20260508`
**Worker:** `W-1307-telethon-langfuse-loop-20260508`
**Scope:** Execute the Telethon-driven validation loop as far as local credentials/resources allow.

---

## 1. Static Readiness

### Git status
- Branch: `runtime/1307-telethon-langfuse-loop-20260508` tracking `origin/dev`
- Worktree clean

### Environment presence (names only)
No `.env` file exists in the repo root. The shell environment does not contain:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`
- `TELEGRAM_BOT_TOKEN`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

`.env.example` contains placeholder values for `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.

### Session files
No `e2e_tester.session` or other Telethon session files found in the worktree.

---

## 2. Existing Harness Checks

### Unit tests
| Test | Result |
|------|--------|
| `tests/unit/e2e/test_langfuse_trace_validator.py` | **PASSED** (1 passed) |
| `tests/unit/e2e/test_corpus_e2e_config.py` | **PASSED** (2 passed) |

Both tests pass with warnings (Langfuse SDK 4.3.1 Pydantic V1 deprecation on Python 3.14), consistent with prior audit.

---

## 3. Local Services

### Docker service status
Core services are running under project `dev`:

| Service | Status | Notes |
|---------|--------|-------|
| `dev_bot_1` | Up (healthy) | Crashes on start due to invalid token (see §5) |
| `dev_litellm_1` | Up (healthy) | Proxy on `:4000` |
| `dev_qdrant_1` | Up (healthy) | REST on `:6333` |
| `dev_bge-m3-1` | Up (healthy) | REST on `:8000` |
| `dev_redis_1` | Up (healthy) | Password-protected on `:6379` |
| `dev_postgres_1` | Up (healthy) | `:5432` |
| `dev_langfuse-worker_1` | Up (healthy) | |
| `dev_langfuse_1` | **Up (unhealthy)** | Database auth failure (see §5) |
| `dev_mini-app-frontend_1` | **Restarting** | nginx permission error (see §5) |

### Health probes
- `curl http://localhost:4000/health/readiness` → LiteLLM healthy
- `curl http://localhost:6333/readyz` → Qdrant healthy
- `curl http://localhost:8000/health` → BGE-M3 healthy
- `curl http://localhost:3001/api/public/health` → **Connection reset** (Langfuse unhealthy)

---

## 4. Bot

### Container state
The bot container reports `healthy` in Docker but its logs show a crash loop:
- `TokenValidationError: Token is invalid!`
- Cause: `TELEGRAM_BOT_TOKEN` is set to the test placeholder `test-telegram-bot-token` from `tests/fixtures/compose.ci.env`

### Langfuse in bot
Bot logs also report:
- `Langfuse endpoint unreachable (http://langfuse:3000) — tracing disabled`
- `Langfuse disabled (missing LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)`

This is because `tests/fixtures/compose.ci.env` does not set Langfuse keys, and `compose.yml` defaults them to empty strings.

---

## 5. Telethon Loop

### Required credentials
Per `scripts/e2e/config.py`:
- `TELEGRAM_API_ID` (int)
- `TELEGRAM_API_HASH` (str)
- `E2E_BOT_USERNAME` (defaults to `@test_nika_homes_bot`)
- Telethon session file (`e2e_tester.session`)

### Blocker
**The Telethon loop cannot run.**
- `TELEGRAM_API_ID` is not set in the shell environment.
- `TELEGRAM_API_HASH` is not set.
- No `.env` file exists.
- No `e2e_tester.session` file exists.

Running `make e2e-telegram-test` or `scripts/e2e/runner.py` would exit with:
```
Configuration errors:
  - TELEGRAM_API_ID not set
  - TELEGRAM_API_HASH not set
```

---

## 6. Trace Audit

### Langfuse accessibility
Langfuse UI/API is **not accessible** because the `dev_langfuse_1` container is unhealthy.

### Root cause: Postgres auth mismatch
Langfuse logs show:
```
Authentication failed against database server, the provided database credentials for `postgres` are not valid.
Error: P1000: Authentication failed against database server
```

This occurred because `make validate-traces-fast` (run without a `.env` file) used `tests/fixtures/compose.ci.env`, which sets `POSTGRES_PASSWORD=test-postgres-password`. The existing Postgres data volume was previously initialized with the default password `postgres` (from `compose.dev.yml`). Recreating the Postgres container with a different password causes an auth mismatch.

### `make validate-traces-fast`
**Status:** FAILED
- Exited with code 2 due to `dev_mini-app-frontend_1` being unhealthy
- The mini-app-frontend restart loop is caused by an nginx `chown` permission error inside the container

---

## 7. Findings

### New bugs

| Title | Evidence | Suspected Files | Disposition |
|-------|----------|-----------------|-------------|
| Postgres auth mismatch when `.env` is missing and `make validate-traces-fast` uses `compose.ci.env` | Langfuse fails with P1000 after `make validate-traces-fast` recreates Postgres with `test-postgres-password` against old data volume | `Makefile`, `tests/fixtures/compose.ci.env`, `compose.dev.yml` | `new_or_existing_issue` |
| mini-app-frontend container restart loop | nginx `[emerg] chown("/var/cache/nginx/client_temp", 101) failed (1: Operation not permitted)` | `compose.dev.yml` (mini-app-frontend service) | `new_or_existing_issue` |
| `compose.ci.env` missing Langfuse keys causes bot to disable tracing | Bot logs: `Langfuse disabled (missing LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)` | `tests/fixtures/compose.ci.env` | `new_or_existing_issue` |

### Pre-existing / already tracked
- `litellm-acompletion` orphan traces (see #1362)
- `FakeMessage.chat` streaming issue (see #1379)
- Pydantic V1 warning on Python 3.14 (see #1381)

### Environment blockers
| Blocker | Missing Variables |
|---------|-------------------|
| Telegram E2E cannot run | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `e2e_tester.session` |
| Bot cannot start | `TELEGRAM_BOT_TOKEN` (real token) |
| Langfuse tracing disabled in bot | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` in `compose.ci.env` |

---

## 8. Recommendations

1. **Provide real Telegram credentials** (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH` from my.telegram.org) and create an `e2e_tester.session` file to unblock the Telethon loop.
2. **Fix Postgres password consistency** when `make validate-traces-fast` falls back to `compose.ci.env` — either document the need to run with a consistent `.env`, or ensure `compose.ci.env` matches the default dev password.
3. **Fix mini-app-frontend** nginx permission issue (likely needs `user root;` in nginx config or adjusted container permissions).
4. **Add `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`** to `tests/fixtures/compose.ci.env` so that local bot containers do not silently disable tracing when the fallback env file is used.
5. **Update `docs/LOCAL-DEVELOPMENT.md`** to explicitly list `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` as requirements for the Telegram E2E path (see §9).

---

## 9. Docs Impact

`docs/LOCAL-DEVELOPMENT.md` was updated to include the Telegram E2E credential requirements in the local development prerequisites section.

---

*Report generated by `W-1307-telethon-langfuse-loop-20260508` on 2026-05-08.*
