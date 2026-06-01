# Local Development

Canonical local setup and verification flow.

## Prerequisites

- Python `3.12` recommended (`>=3.11` supported)
- `uv`
- Docker + Docker Compose v2

## 1. Bootstrap Workspace

```bash
uv sync
cp .env.example .env
```

For local development, the canonical environment file is `.env` in the repo root. `.env.local` is legacy/manual-only and is not auto-loaded by local commands.

Minimum env for bot profile:
- `TELEGRAM_BOT_TOKEN`
- `LITELLM_MASTER_KEY`
- at least one provider key: `CEREBRAS_API_KEY` or `GROQ_API_KEY` or `OPENAI_API_KEY`
- optional `QDRANT_COLLECTION` (defaults to `gdrive_documents_bge` from `compose.yml` if unset)

Minimum env for Telegram E2E (Telethon userbot):
- `TELEGRAM_API_ID` (from [my.telegram.org](https://my.telegram.org))
- `TELEGRAM_API_HASH` (from [my.telegram.org](https://my.telegram.org))
- `E2E_BOT_USERNAME` (defaults to `@test_nika_homes_bot`)
- an authorized Telethon session file (e.g., `e2e_tester.session`)
- if the session is present but unauthorized, refresh it with `uv run python scripts/e2e/auth.py --phone <PHONE>`

E2E judge routing defaults:
- `E2E_JUDGE_PROVIDER=litellm` (default)
- `E2E_JUDGE_BASE_URL=http://localhost:4000/v1` (default)
- `E2E_JUDGE_MODEL=gpt-4o-mini` (default)
- `E2E_JUDGE_API_KEY` (or `LLM_API_KEY` / `OPENAI_API_KEY` / `LITELLM_MASTER_KEY`)
- direct Anthropic judge is opt-in only: `E2E_JUDGE_PROVIDER=anthropic-direct` + `ANTHROPIC_API_KEY`
- for transport-only Telethon checks without LLM judge: run `uv run python scripts/e2e/runner.py --no-judge`

Voice-note fixture for E2E:
- `E2E_VOICE_NOTE_PATH` — path to a local `.ogg` or `.oga` voice-note fixture
- keep a short, non-sensitive query recording in an ignored local path such as `tmp/e2e/` (e.g., *"найди квартиру у моря до 120 тысяч"*)
- do not commit personal voice recordings to the repo

The canonical local Compose project name is `dev`. `COMPOSE_PROJECT_NAME=dev` is set in `tests/fixtures/compose.ci.env`, which `make` targets use as a fallback when `.env` is absent. Do not create worktree-named Docker projects.

Secret model by compose file:
- `compose.yml` is the secure baseline: no predictable built-in secret defaults.
  Stateful passwords use `${VAR:?VAR is required}` — they must come from `.env`
  or an explicit `--env-file`.
- `compose.dev.yml` overrides stateful password variables with the same required
  pattern and provides local-only non-password defaults for Langfuse headless
  init (`LANGFUSE_INIT_*`) and traced-service keys (`LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY`). `LIVEKIT_API_KEY` defaults to `devkey` as a documented
  dev identifier.
- Production/VPS stacks must set real secret values via environment management or file-backed secret patterns (`*_FILE` / `secrets:`) when available.

Langfuse local development:
- `compose.dev.yml` uses Langfuse headless initialization defaults to create a local dev organization/project/API key (`[REDACTED-LANGFUSE-KEY] / `[REDACTED-LANGFUSE-KEY] when the Langfuse database is empty.
- Traced dev services use the same local keys, so a fresh local Langfuse database should accept OTLP ingestion after `langfuse` is recreated.
- If `bot` logs show OTLP `401` / `No key found for public key`, recreate `langfuse`, `langfuse-worker`, and the traced service with the same env file, then confirm the local Langfuse DB has an organization, project, and API key before debugging application tracing.

## 2. Start Services

```bash
# Core services (default compose set)
make docker-up

# Bot runtime
make docker-bot-up

# Optional profiles
make docker-ml-up
make docker-ingest-up
make monitoring-up

# Voice is intentionally off by default; start separately when needed:
# make docker-voice-up
```

## 3. Validate Runtime

```bash
make docker-ps
curl -fsS http://localhost:6333/readyz
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:5001/health
```

Bot environment preflight (checks .env, token validity, port binding):

```bash
make preflight-bot
```

Bot preflight:

```bash
make test-bot-health
```

End-to-end smoke (proves `make bot` actually answers a Telegram message,
issue #2192):

```bash
make bot-response-smoke
```

The target runs five preflight stages — env vars, Telethon session file,
`getMe` username match, `getWebhookInfo` empty, and the Redis polling lock
state — before delegating to `scripts.e2e.quick_test` for a single safe
query. It never deletes the polling lock and never re-authorizes the
userbot; missing session redirects to `scripts.e2e.auth`.

Bot-local LangChain/LangGraph dependency smoke:

```bash
uv --directory telegram_bot run --frozen python -c 'from langchain.agents import create_agent'
PYTHONPATH="$PWD" uv --directory telegram_bot run --frozen python -c 'from telegram_bot.agents.agent import create_bot_agent'
```

Run this after changes to `telegram_bot/pyproject.toml`,
`telegram_bot/uv.lock`, or LangChain/LangGraph agent code. The Docker bot image
builds from the bot-local lock, so root `uv.lock` passing is not enough for bot
runtime compatibility.

If `make test-bot-health` reports Redis auth failure after editing `.env`:

```bash
make local-redis-recreate
make test-bot-health
```

`make test-bot-health` is a local helper for the published native bot prerequisites:
- Redis via the same `BotConfig` + `redis.from_url(...)` path used by native startup
- Qdrant via `BotConfig.get_collection_name()` + `qdrant-client`
- LiteLLM via proxy readiness (`/health/readiness`)
- optional localhost Postgres note without turning DB reachability into a hard failure

The authoritative startup preflight still lives in [`telegram_bot/preflight.py`](../telegram_bot/preflight.py) and runs when you start the bot. That runtime preflight also keeps the repo-local BGE-M3 health and warmup contract, because BGE-M3 is not a generic upstream SDK probe in this repo.

## 4. Development Gates

Git hooks and push gates are static guardrails only: lint, formatting, type
checks, and repository policy checks. They should not run pytest suites. Run
tests explicitly as local validation on the development machine.

### Pre-push gate

The `make pre-push` target is the recommended gate before pushing:

```bash
make pre-push          # lint + format-check
```

This runs expanded lint (covering `src/` and `telegram_bot/` to match CI),
and format verification. Run `make check` when you also need the current
lint + MyPy gate; it may surface known baseline type drift until that is fixed.

For candidate or review validation where the project `.venv` must not be
changed implicitly, use:

```bash
make candidate-check
```

This is a read-only frozen check that runs `uv sync --frozen --check` first to
detect whether `.venv` matches the lockfile, then runs Ruff lint and MyPy with
`uv run --no-sync` to prevent implicit environment updates. It does NOT create
or modify `.venv`. If the environment is absent or stale, it fails with
guidance instead of uninstalling or installing packages. Keep ordinary
developer loops on `make check` when auto-sync is acceptable.

Stale `.venv` remediation:
- If `.venv` exists but is stale (lockfile changed): `uv sync --frozen`
- If `.venv` is absent or was polluted by another worktree: recreate with
  `uv sync --frozen` (or `uv sync` for full dev install)
- When switching between worktrees that share a lockfile, run
  `make candidate-check` in each before committing changes

### Hooks and uv environments

Pre-commit hooks use their own isolated virtualenvs managed by the pre-commit
framework. They do NOT use the project `.venv` created by `uv sync`. This means
hooks can run even if your project venv is in an inconsistent state.

### Hooks in OpenCode worker worktrees

Each worktree needs its own hook installation. After creating a new worktree,
run:

```bash
make setup-hooks
```

This installs both pre-commit and pre-push hooks for that worktree.

### fail_fast behavior

The hook configuration sets `fail_fast: true`. This ensures hooks stop on the
first failure and do not mutate unrelated files in a dirty checkout.

### Local release gate

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-bot-health
```

PR-ready local gate:

```bash
make local-pr-ready
```

Optional broader gates:

```bash
make test
make test-full
```

### CI vs Local Test Gates

GitHub CI runs repository hygiene gates such as secret scanning, Semgrep project
guardrails, Ruff lint, Ruff format, and CodeQL. Python test gates are
local/manual so failures can be debugged against the developer environment that
owns the runtime state.

| Local Command | What It Covers |
|---|---|
| `make test` | unit + critical graph paths; no contract, no coverage |
| `make test-contract` | contract trace tests only (static, no Docker) |
| `make test` + `make test-contract` | local test-surface match for unit + contract + graph-path checks |
| `make local-pr-ready` | `make check` (lint + types) then `make test-unit`; skips contract and graph-path integration tests |
| `make check` + `make test` + `make test-contract` | recommended merge-readiness ladder on a powerful local machine |

Run the same generic code-pattern guardrails as the `Semgrep` CI job:

```bash
uvx --from semgrep==1.163.0 semgrep scan \
  --config .semgrep/project-guardrails.yml \
  --error \
  --metrics=off \
  src telegram_bot scripts .github/workflows compose.yml compose.dev.yml
```

`make local-pr-ready` is a quick local gate that catches most regressions early
but is narrower than the full local merge-readiness ladder. Before merging a
test-sensitive change on a powerful local machine, use:

```bash
make check
make test
make test-contract
```

### Heavy test gate (`make test-full`)

`make test-full` runs the entire test suite (all tiers) and is intended as a
**manual** pre-merge validation step, not a routine development loop command.

It defaults to bounded parallelism (`-n 2 --dist=worksteal`) via
`PYTEST_FULL_PARALLEL_ARGS` to prevent memory saturation on WSL/Docker
environments where RAM is limited (8-10 GiB typical).

Fast gates (`make test`, `make test-unit`) keep `-n auto` via
`PYTEST_PARALLEL_ARGS` for quick local feedback since they exercise a smaller
test surface that fits comfortably in memory.

To override parallelism for a specific run:

```bash
PYTEST_FULL_PARALLEL_ARGS='-n 4 --dist=worksteal' make test-full
```

**WSL considerations:** On WSL with constrained memory, unbounded `-n auto`
during heavy test runs can exhaust RAM + swap, cause unkillable `D`-state
processes, and destabilize Docker Desktop integration. Keep parallelism low
(`-n 2` or `-n 4` max) and ensure no stale pytest-xdist workers are running
before starting a heavy session:

```bash
pgrep -af 'pytest|docker compose'
```

Trace coverage gate:

```bash
make validate-traces-fast
```

This target runs natively on the host and automatically points to local Docker service endpoints (`localhost:6333`, `localhost:8000`, `localhost:4000`, etc.). You can override individual endpoints if needed: `make validate-traces-fast QDRANT_URL=http://custom:6333`.

When `.env` is absent, `validate-traces-fast` runs a preflight guard before `docker compose up`. If fallback uses `tests/fixtures/compose.ci.env` with the local default `POSTGRES_PASSWORD=postgres`, reusing `dev_postgres_data` is allowed. The guard fails fast only when fallback password and existing volume credentials can mismatch, preventing an unhealthy Langfuse/Postgres auth loop.

If Langfuse CLI returns `401` or points to wrong host, run with explicit host:

```bash
lf --host "$LANGFUSE_HOST" traces list --name rag-api-query --limit 1
```

## 5. Production Deployment (VPS)

The recommended production flow is:

1. Work on a feature branch.
2. Push the branch.
3. Stage on the MacBook Docker host with `make remote-core-up`.
4. Open/merge PR to `main`.
5. GitHub Actions deploys `main` to VPS.

The VPS default runtime (`compose.yml:compose.vps.yml`) starts only the RAG
chatbot core: `postgres`, `redis`, `qdrant`, `bge-m3`, `user-base`, `litellm`,
and `bot`. Mini app, Docling, ingestion, and self-hosted Langfuse are
optional/profile-gated. See [`../DOCKER.md`](../DOCKER.md) for details and
[cleanup commands](../DOCKER.md#vps-cleanup).

## 6. Python Runtime Note

Docker images that import `telegram_bot.observability` (and therefore `langfuse`) run on Python 3.13. Local native development via `uv` may use a different Python version (3.11+ supported, 3.12 recommended).

## 7. Running Components Without Docker Wrapper

`make bot`, `make run-bot`, and `make preflight-bot` now use
`uv run --no-sync` to prevent implicit venv updates during runtime loops.
This keeps the runtime environment stable and avoids lockfile drift when
the development venv is already in sync.

```bash
# Telegram bot (no-sync)
make bot                 # tee output to logs/bot-run.log

# Telegram bot without tee
make run-bot

# Unified ingestion
uv run python -m src.ingestion.unified.cli

# RAG API
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8080
```

If your venv is stale and the bot startup fails with a missing import,
run `uv sync --frozen` before restarting.

## 8. Minimal Stack (Fast Iteration)

Use the `local-*` shortcuts (they now run a minimal subset from `compose.yml:compose.dev.yml`) when full dev stack is unnecessary:

```bash
make local-up
make test-bot-health
make bot
make local-ps
make local-down
```

`make local-up` starts the native bot dependencies needed for the local loop:
Postgres, Redis, Qdrant, BGE-M3, and LiteLLM. Postgres is included so
favorites backed by `realestate.public.user_favorites` are available during
native bot runs.

If you changed `.env` `REDIS_PASSWORD`, recreate local Redis before retrying bot health:

```bash
make local-redis-recreate
make test-bot-health
```

`make bot` is the operator-facing command for this local loop; `make run-bot` remains the lower-level/native target.

For ingestion workflows that require docling:

```bash
make local-up-ingest
make local-ps
make local-down
```

## 9. E2E Core Trace Gate (#1307)

Required core Telethon trace scenarios with Langfuse validation:

```bash
make local-up
make docker-ml-up
make bot
make e2e-test-traces-core
```

Keep `make bot` running in another terminal while the E2E command executes. Use `make run-bot` only when you do not need the tee'd `logs/bot-run.log` evidence.

## 10. Runtime env in worktrees

Swarm worktrees start from a fresh `origin/dev` checkout and do not contain the main checkout's `.env` or Telegram session files. To keep E2E trace gates reproducible without copying secrets into every worktree:

- Compose commands must use `$(LOCAL_COMPOSE_CMD)` (or explicitly `docker compose --env-file tests/fixtures/compose.ci.env ...`) so services start with safe fallback values when `.env` is absent.
- Telethon/E2E commands must use `uv run --env-file "$RAG_RUNTIME_ENV_FILE" ...` so runner credentials are loaded explicitly.
- For swarm worktrees, set `RAG_RUNTIME_ENV_FILE=/repo/.env` when local Telegram credentials live only in the main checkout.
- Do not copy `.env`, Telegram sessions, or provider keys into worker worktrees.

## 11. Common Issues

- `docker-bot-up` fails immediately: missing required env variables in `.env`. Run `make preflight-bot` for a diagnostic report.
- Bot crash-loops with `TokenValidationError`: `.env` is missing and the CI fallback `TELEGRAM_BOT_TOKEN=123456789:ABC...fghi` is not a valid Telegram token. `cp .env.example .env` then set real `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY`, and a provider key.
- `curl localhost:4000` Connection Refused: LiteLLM port not published on host. See [`../DOCKER.md`](../DOCKER.md) "LiteLLM port recovery" — most often caused by a stray compose file at `/tmp/compose.postgres-root.yml` overriding the dev port mapping.
- Slow first startup: BGE-M3 and Docling warm up and cache models.
- Ingestion status empty: verify `GDRIVE_SYNC_DIR` and collection bootstrap.
- Redis auth error (`WRONGPASS` / `NOAUTH`) after changing `.env` `REDIS_PASSWORD`: run `make local-redis-recreate`, then `make test-bot-health`.
- `make docker-bot-up` or `make bot` exits before starting with no clear error: run `make preflight-bot` to see exactly what is missing. Use `PREFLIGHT_BOT_FLAGS='--no-fail'` to bypass the guardrail if you only need to start infrastructure.
- `make candidate-check` fails with "Environment is stale": run `uv sync --frozen` to align `.venv` with the current lockfile, then retry. If `.venv` was polluted by another worktree sharing the same lockfile, delete `.venv` and recreate with `uv sync --frozen`.
- `make bot` fails with a missing import at startup: the venv is stale. Run `uv sync --frozen` before restarting the bot.
