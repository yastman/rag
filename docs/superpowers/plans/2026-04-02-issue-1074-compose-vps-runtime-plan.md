# Issue #1074 Compose VPS Runtime Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the current runtime-contract gaps behind `#1074` by correcting the base compose/env configuration that VPS and local runtime both rely on, while avoiding stale fixes for issue points that are no longer true.

**Architecture:** First codify the actual current contract in tests: `.env.example` must document required runtime vars, and base `compose.yml` must provide the MinIO console address plus environment-driven LiveKit URLs instead of hardcoded values. Then apply the minimal config edits and verify the merged VPS compose still resolves cleanly with dummy required env values.

**Tech Stack:** Docker Compose, YAML, `.env.example`, `pytest`, `uv`

---

### Task 1: Lock the missing env/example contract

**Files:**
- Modify: `tests/unit/test_env_example.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing env-example assertions**

Add assertions that `.env.example` contains:
- `BOT_USERNAME`
- `INGESTION_DATABASE_URL`

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/unit/test_env_example.py -q`

Expected: fail because those variables are not currently documented in `.env.example`.

- [ ] **Step 3: Add the missing env variables**

Document both variables in `.env.example` in the relevant sections without inventing unrelated new required secrets.

- [ ] **Step 4: Run GREEN**

Run: `uv run pytest tests/unit/test_env_example.py -q`

Expected: pass.

### Task 2: Lock the compose runtime contract

**Files:**
- Create: `tests/unit/test_compose_runtime_contract.py`
- Modify: `compose.yml`

- [ ] **Step 1: Write failing compose-contract tests**

Add focused tests asserting:
- base `compose.yml` MinIO command includes `--console-address ":9001"`
- `voice-agent` uses `${LIVEKIT_URL:-ws://livekit-server:7880}`
- `livekit-sip` uses `${LIVEKIT_URL:-ws://livekit-server:7880}` for both `LIVEKIT_WS_URL` and `SIP_CONFIG_BODY`

- [ ] **Step 2: Run RED**

Run: `uv run pytest tests/unit/test_compose_runtime_contract.py -q`

Expected: fail on the current hardcoded/higher-drift config.

- [ ] **Step 3: Apply the minimal compose fix**

Update `compose.yml` only:
- add MinIO console address to the base command
- replace hardcoded LiveKit websocket URLs with `${LIVEKIT_URL:-ws://livekit-server:7880}`

- [ ] **Step 4: Run GREEN**

Run: `uv run pytest tests/unit/test_compose_runtime_contract.py -q`

Expected: pass.

### Task 3: Verify VPS runtime shape and finish tracking

**Files:**
- Modify: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`

- [ ] **Step 1: Run targeted runtime verification**

Run:
- `export POSTGRES_PASSWORD=x REDIS_PASSWORD=x TELEGRAM_BOT_TOKEN=x LITELLM_MASTER_KEY=x OPENAI_API_KEY=x NEXTAUTH_SECRET=x SALT=x ENCRYPTION_KEY=x LIVEKIT_API_KEY=x LIVEKIT_API_SECRET=x GDRIVE_SYNC_DIR=/tmp; COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services`
- `make verify-compose-images` (only if it does not require live running services; otherwise skip and state why)
- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

Expected: compose resolves, checks pass, and no new runtime regressions appear.

- [ ] **Step 2: Mark the shared triage snapshot**

If the implementation is complete and verified, update `docs/plans/2026-04-01-open-issues-triage-snapshot.md`:
- move `#1074` out of `Plan needed`
- add an execution update entry with concrete completion details
- switch `Next recommended task` to the next open issue in order
