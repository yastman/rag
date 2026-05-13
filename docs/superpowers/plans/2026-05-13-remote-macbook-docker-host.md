# Remote MacBook Docker Host Implementation Plan

> **For agentic workers:** execute this plan task by task. Keep edits scoped,
> preserve unrelated worktree changes, and do not print secret values.

**Goal:** Make the MacBook the canonical dev Docker host for `rag-fresh`,
including the Telegram bot container, and verify the workflow from WSL without
using Docker Desktop locally.

**Design input:** [`../specs/2026-05-13-remote-macbook-docker-host-design.md`](../specs/2026-05-13-remote-macbook-docker-host-design.md)

**Architecture:** WSL keeps source editing and fast host-side checks. The
MacBook runs Colima, Docker, Compose, all containers, volumes, images, networks,
the remote repo checkout, and runtime `.env`.

**Remote constants:**

- SSH host: `macbook-docker`
- Remote repo: `/Users/aroslav/Documents/rag-fresh`
- Homebrew path: `/opt/homebrew/bin:/usr/local/bin:$PATH`
- Compose files: `compose.yml:compose.dev.yml`
- Docker host LAN IP: `REDACTED_PRIVATE_IP`
- MacBook BGE-M3 memory default: `BGE_M3_MEMORY_LIMIT=6G`

---

## File Structure

- Modify `Makefile`: remote Docker variables, env sync/check targets, bot
  container targets, active stack target, read-only diagnostics.
- Modify `compose.yml`: keep BGE-M3 memory limit overridable if not already done.
- Modify `docs/runbooks/remote-macbook-docker.md`: final operator workflow.
- Modify `docs/LOCAL-DEVELOPMENT.md`: day-to-day MacBook Docker workflow.
- Modify `DOCKER.md`: only if command/env/profile truth changes.
- Optionally modify `docs/indexes/local-runtime.md` or
  `docs/indexes/runtime-services.md` if lookup paths need the remote runbook.

## Task 1: Normalize Remote Docker Make Variables

**Files:**

- Modify: `Makefile`

- [ ] Set remote variables near existing Compose variables:

```make
REMOTE_DOCKER_HOST ?= macbook-docker
REMOTE_DOCKER_IP ?= REDACTED_PRIVATE_IP
REMOTE_DOCKER_REPO ?= ~/Documents/rag-fresh
REMOTE_DOCKER_PATH ?= /opt/homebrew/bin:/usr/local/bin:$$PATH
REMOTE_COMPOSE_FILE ?= compose.yml:compose.dev.yml
REMOTE_BGE_M3_MEMORY_LIMIT ?= 6G
REMOTE_SSH := ssh $(REMOTE_DOCKER_HOST)
```

- [ ] Define a remote Compose command that:
  - changes into `$(REMOTE_DOCKER_REPO)`;
  - exports Homebrew PATH;
  - enables BuildKit;
  - exports `BGE_M3_MEMORY_LIMIT=$(REMOTE_BGE_M3_MEMORY_LIMIT)`;
  - uses `.env` when present, otherwise `tests/fixtures/compose.ci.env`;
  - always uses `--compatibility`.

- [ ] Keep the remote repo path aligned with
  `/Users/aroslav/Documents/rag-fresh`. Do not reintroduce
  `/Users/aroslav/rag-fresh`.

## Task 2: Add Read-Only Remote Diagnostics

**Files:**

- Modify: `Makefile`

- [ ] Add or verify these targets:

```text
make remote-docker-status
make remote-compose-config
make remote-docker-ps
```

- [ ] `remote-docker-status` should report:
  - remote hostname;
  - git branch and last commit in the remote repo;
  - Colima status;
  - Docker client/server version;
  - Docker buildx version or a clear buildx failure.

- [ ] `remote-compose-config` should render services without printing secrets.

- [ ] `remote-docker-ps` should show Compose container names, status, and ports.

**Verify:**

```bash
make remote-docker-status
make remote-compose-config
```

## Task 3: Add Approved Remote Env Transfer And Validation

**Files:**

- Modify: `Makefile`
- Modify: `docs/runbooks/remote-macbook-docker.md`

- [ ] Add `remote-env-sync`.

Contract:

- copies WSL repo-root `.env` to
  `/Users/aroslav/Documents/rag-fresh/.env`;
- creates no chat/log output containing secret values;
- fails clearly if local `.env` is absent;
- uses SSH/rsync/scp in a simple auditable way.

- [ ] Add `remote-env-check`.

Contract:

- verifies remote `.env` exists;
- reports missing required variable names only;
- covers bot path minimum from `DOCKER.md`:
  `TELEGRAM_BOT_TOKEN`, `LITELLM_MASTER_KEY`, and at least one provider key from
  `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`;
- covers ML profile variables if `remote-active-up` includes Langfuse services:
  `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`;
- never prints values.

**Verify:**

```bash
make remote-env-sync
make remote-env-check
```

## Task 4: Make The Active Remote Stack Include Bot

**Files:**

- Modify: `Makefile`
- Modify: `docs/runbooks/remote-macbook-docker.md`
- Modify: `docs/LOCAL-DEVELOPMENT.md`

- [ ] Define `REMOTE_ACTIVE_SERVICES` as the current development Docker service
  set plus the `bot` container.

Baseline active set:

```text
mini-app-frontend mini-app-api bge-m3 litellm redis langfuse langfuse-worker postgres redis-langfuse qdrant rag-api minio clickhouse user-base bot
```

- [ ] Ensure `remote-active-up` enables the profiles required by that set:
  `bot`, `ml`, and `voice` if `rag-api` remains in the active set.

- [ ] Keep `remote-full-up` as an explicit full-profile command, not the default
  daily command.

**Verify:**

```bash
make remote-active-up
make remote-docker-ps
```

Expected: services build/start on the MacBook. The bot container is present.

## Task 5: Add Bot Container Operator Targets

**Files:**

- Modify: `Makefile`
- Modify: `docs/runbooks/remote-macbook-docker.md`

- [ ] Add or verify:

```text
make remote-bot-up
make remote-bot-restart
make remote-bot-logs
```

Contracts:

- `remote-bot-up` starts the Compose bot container and required profile.
- `remote-bot-restart` recreates the bot container after code/config changes.
- `remote-bot-logs` shows recent bot logs without secret values.

- [ ] Do not redefine WSL `make bot` in this task. Document that `make bot` is
  the native WSL helper, while MacBook Docker bot runs through `remote-*`.

**Verify:**

```bash
make remote-bot-up
make remote-bot-logs
```

Expected: bot preflight reaches running dependencies or reports missing runtime
requirements by name.

## Task 6: Verify Remote Service Health

**Files:**

- Modify: `Makefile`
- Modify: `docs/runbooks/remote-macbook-docker.md`

- [ ] Update `remote-service-health` to check endpoints over SSH on the MacBook
  with `127.0.0.1`, because WSL `localhost` is not the Docker host.

Minimum checks:

```text
Qdrant readyz
BGE-M3 health
LiteLLM readiness
Docling health if started
Langfuse web or API health if started
bot container status/restart count
```

- [ ] Optional services may be soft failures only when they are not part of the
  selected stack. Required active-stack services should be hard failures.

**Verify:**

```bash
make remote-service-health
```

Expected: Compose status and endpoint checks agree before the stack is called
healthy.

## Task 7: Update Project Documentation

**Files:**

- Modify: `docs/runbooks/remote-macbook-docker.md`
- Modify: `docs/LOCAL-DEVELOPMENT.md`
- Modify: `DOCKER.md` only if canonical command/env/profile truth changed.
- Optionally modify: `docs/indexes/local-runtime.md`,
  `docs/indexes/runtime-services.md`, `docs/runbooks/README.md`.

- [ ] In the runbook, document:
  - MacBook owns Docker runtime, including bot container;
  - `make remote-env-sync` and `make remote-env-check`;
  - read-only diagnostics;
  - `make remote-active-up`;
  - `make remote-bot-up`, `make remote-bot-restart`,
    `make remote-bot-logs`;
  - `localhost` vs `REDACTED_PRIVATE_IP`;
  - which tests stay on WSL and which run over SSH on MacBook;
  - troubleshooting for SSH, Colima, buildx, stale repo, `.env`, bot restart
    loops, and health mismatch.

- [ ] In local development docs, make the MacBook Docker path the recommended
  Docker path for this machine and keep native `make bot` described as separate
  from Docker bot.

- [ ] Avoid duplicating the full service table from `DOCKER.md`.

**Verify:**

```bash
git diff --check -- Makefile compose.yml DOCKER.md docs/LOCAL-DEVELOPMENT.md docs/runbooks/remote-macbook-docker.md docs/indexes/local-runtime.md docs/indexes/runtime-services.md docs/runbooks/README.md
```

## Task 8: End-To-End Runtime Verification

**Files:**

- No planned edits unless verification exposes bugs.

- [ ] Check remote status:

```bash
make remote-docker-status
```

- [ ] Sync and validate env:

```bash
make remote-env-sync
make remote-env-check
```

- [ ] Render Compose:

```bash
make remote-compose-config
```

- [ ] Start active stack including bot:

```bash
make remote-active-up
```

- [ ] Inspect containers:

```bash
make remote-docker-ps
make remote-bot-logs
```

- [ ] Check service health:

```bash
make remote-service-health
```

- [ ] Run WSL checks against MacBook endpoints only where appropriate:

```bash
QDRANT_URL=http://REDACTED_PRIVATE_IP:6333 \
LITELLM_BASE_URL=http://REDACTED_PRIVATE_IP:4000 \
make test-bot-health
```

- [ ] Run Docker-local checks over SSH when they depend on Compose networks,
  Docker exec, volumes, or bind mounts:

```bash
ssh macbook-docker 'cd ~/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-smoke'
```

## Task 9: Report Final State

- [ ] Report exact commands run and their outcomes.
- [ ] Report any services still unhealthy by name.
- [ ] Report tests skipped and why.
- [ ] Report whether `.env` was synced, without printing values.
- [ ] Confirm whether Docker Desktop on WSL/Windows was avoided.
