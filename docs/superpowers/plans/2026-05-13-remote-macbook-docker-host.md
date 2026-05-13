# Remote MacBook Docker Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use tmux-swarm-orchestration to
> execute this plan with isolated OpenCode workers, a PR branch, runtime
> verification, read-only PR review, and review-fix waves. Steps use checkbox
> (`- [ ]`) syntax for tracking. Keep edits scoped, preserve unrelated worktree
> changes, and do not print secret values.

**Goal:** Make the MacBook the canonical dev Docker host for `rag-fresh`,
including the Telegram bot container, and verify the workflow from WSL without
using Docker Desktop locally.

**Design input:** [`../specs/2026-05-13-remote-macbook-docker-host-design.md`](../specs/2026-05-13-remote-macbook-docker-host-design.md)

**Architecture:** WSL keeps source editing and fast host-side checks. The
MacBook runs Colima, Docker, Compose, all containers, volumes, images, networks,
the remote repo checkout, and runtime `.env`.

**Tech Stack:** GNU Make, SSH, rsync/scp, Docker Compose v2, Colima on macOS,
existing `compose.yml`/`compose.dev.yml`, `tests/fixtures/compose.ci.env`,
tmux/OpenCode swarm workers, GitHub PR review flow.

**Remote constants:**

- SSH host: `macbook-docker`
- Remote repo: `/Users/aroslav/Documents/rag-fresh`
- Homebrew path: `/opt/homebrew/bin:/usr/local/bin:$PATH`
- Compose files: `compose.yml:compose.dev.yml`
- Docker host LAN IP: `192.168.31.168`
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

## Swarm Execution Model

Run this plan from the orchestrator using `tmux-swarm-orchestration`.

Branch and PR:

- Base branch: `dev`.
- Working branch: `feature/remote-macbook-docker-host`.
- PR target: `dev`.
- PR title: `feat: run dev docker stack on remote macbook`.

Worker waves:

1. **Implementation worker** owns `Makefile` and `compose.yml`.
2. **Docs worker** owns remote Docker docs and indexes.
3. **Runtime verification worker** owns MacBook runtime evidence and must not
   edit source unless the orchestrator explicitly opens a fix wave.
4. **PR review worker** is read-only against the current PR head SHA.
5. **Review-fix worker** fixes only named PR blockers on the PR branch.

Reservation rules:

- No overlapping write reservations in the same wave.
- Runtime worker may run commands against the MacBook but must not copy secrets
  into any isolated worker worktree.
- The orchestrator performs final diff review, verifies evidence, and decides
  merge readiness.
- Runtime, Docker, and Compose workers count as two active swarm slots because
  they contend for shared services.

Worker prompt baseline:

- Required OpenCode skill for implementation/docs workers:
  `project-docs-maintenance`, `swarm-pr-finish` when docs are touched;
  otherwise `swarm-pr-finish`.
- Required OpenCode skill for PR review worker:
  `gh-pr-review`, `swarm-pr-finish`.
- Required OpenCode skill for review-fix worker:
  `swarm-review-fix`, `swarm-pr-finish`.
- Docs lookup policy: local-only unless the orchestrator explicitly allows a
  specific external lookup.
- Finish contract: commit, push, open/update PR when assigned, write valid DONE
  JSON, and wake the orchestrator.

## Task 0: Create Swarm Branch And Launch Envelope

**Files:**

- No source edits.
- Create worker prompts or launch metadata under the swarm system's normal
  signal/prompt locations.

- [ ] Ensure the orchestrator pane has a unique tmux routing identity:

```bash
${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/set_orchestrator_pane.sh --ensure-window-name remote-macbook-docker
```

Expected: `.signals/orchestrator-pane.json` is updated with the current tmux
route.

- [ ] Create the working branch from current `dev`:

```bash
git switch dev
git pull --ff-only
git switch -c feature/remote-macbook-docker-host
```

Expected: branch exists locally and is based on current `dev`.

- [ ] Record existing dirty worktree state before launching workers:

```bash
git status --short --branch
```

Expected: unrelated existing changes are visible and not reverted.

- [ ] Decide reservations for wave 1:

```text
Implementation worker reserved files:
- Makefile
- compose.yml

Docs worker reserved files:
- docs/runbooks/remote-macbook-docker.md
- docs/LOCAL-DEVELOPMENT.md
- DOCKER.md
- docs/indexes/local-runtime.md
- docs/indexes/runtime-services.md
- docs/runbooks/README.md
```

- [ ] Launch at most two workers in wave 1 because Docker/runtime work is heavy:

```text
Worker A: implementation, write scope Makefile/compose.yml.
Worker B: docs, write scope docs listed above.
```

Expected: launch metadata records runner, agent, model, worktree, branch,
reserved files, prompt SHA, required skills, and orchestrator route.

## Task 1: Normalize Remote Docker Make Variables

**Files:**

- Modify: `Makefile`

- [ ] Set remote variables near existing Compose variables:

```make
REMOTE_DOCKER_HOST ?= macbook-docker
REMOTE_DOCKER_IP ?= 192.168.31.168
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

**Commit:**

```bash
git add Makefile compose.yml
git commit -m "feat: add remote macbook docker targets"
```

Expected: commit contains only the implementation worker's reserved files.

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

Expected: `.env` exists on the MacBook after sync, required variable names are
reported only when missing, and no secret values appear in output.

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

**Commit:**

```bash
git add Makefile
git commit -m "feat: add remote docker bot controls"
```

Expected: commit contains remote bot lifecycle targets and no docs-only changes.

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
  - `localhost` vs `192.168.31.168`;
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

**Commit:**

```bash
git add DOCKER.md docs/LOCAL-DEVELOPMENT.md docs/runbooks/remote-macbook-docker.md docs/indexes/local-runtime.md docs/indexes/runtime-services.md docs/runbooks/README.md
git commit -m "docs: document remote macbook docker workflow"
```

Expected: commit contains only documentation updates that are needed for the
remote Docker workflow.

## Task 8: End-To-End Runtime Verification

**Files:**

- No planned edits unless verification exposes bugs.
- Runtime evidence may be written to `docs/reports/` only if a persistent report
  is useful for PR review. Do not store secrets.

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
QDRANT_URL=http://192.168.31.168:6333 \
LITELLM_BASE_URL=http://192.168.31.168:4000 \
make test-bot-health
```

- [ ] Run Docker-local checks over SSH when they depend on Compose networks,
  Docker exec, volumes, or bind mounts:

```bash
ssh macbook-docker 'cd ~/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; make test-smoke'
```

- [ ] Verify the bot container specifically:

```bash
make remote-bot-logs
ssh macbook-docker 'cd ~/Documents/rag-fresh && export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility --env-file .env ps bot'
```

Expected: bot container is running or healthy enough to pass startup preflight.
If it restarts, capture restart count and the first non-secret error.

- [ ] Verify Docker Desktop on Windows/WSL was not used:

```bash
docker context show || true
make remote-docker-status
```

Expected: all required Docker evidence comes from `macbook-docker`, not local
Docker Desktop.

- [ ] Runtime worker writes DONE JSON with:
  - remote git branch and commit;
  - Colima CPU/memory status;
  - Docker/buildx versions;
  - env check result with missing variable names only;
  - Compose services rendered;
  - active services started;
  - bot container status and logs summary;
  - service health summary;
  - test commands and exit codes;
  - skipped checks and reasons.

## Task 9: Open Or Update PR

**Files:**

- No source edits unless PR metadata template files already exist and are
  explicitly reserved.

- [ ] Ensure branch contains implementation, docs, and runtime-fix commits:

```bash
git log --oneline --decorate --max-count=10
git status --short --branch
```

Expected: branch is clean except unrelated pre-existing local changes outside
the PR branch/worktree.

- [ ] Push branch:

```bash
git push -u origin feature/remote-macbook-docker-host
```

Expected: branch is available on GitHub.

- [ ] Open PR to `dev`:

```bash
gh pr create \
  --base dev \
  --head feature/remote-macbook-docker-host \
  --title "feat: run dev docker stack on remote macbook" \
  --body-file /tmp/remote-macbook-docker-pr.md
```

PR body must include:

- summary of Makefile/Compose changes;
- docs changed;
- remote `.env` sync status without values;
- MacBook runtime evidence;
- bot container status;
- WSL endpoint checks;
- Docker-local SSH checks;
- skipped checks and why;
- risk notes for MacBook memory, full stack load, and secrets.

Expected: PR URL is recorded in the worker DONE JSON.

## Task 10: Run Read-Only PR Review Worker

**Files:**

- No source edits.

- [ ] Launch a read-only PR review worker against the current PR head SHA.

Worker constraints:

- Required OpenCode skills: `gh-pr-review`, `swarm-pr-finish`.
- Read-only: no commits, no force-push, no edits.
- Review focus:
  - secret leakage in Makefile/docs/log output;
  - remote `.env` copy safety;
  - path correctness (`/Users/aroslav/Documents/rag-fresh`);
  - buildx/BuildKit handling;
  - bot container included in active remote stack;
  - profile correctness for bot/ml/voice services;
  - `localhost` vs MacBook endpoint handling;
  - test split correctness;
  - docs source-of-truth duplication;
  - whether runtime evidence supports the PR claim.

- [ ] Review worker writes findings as DONE JSON and, if using GitHub review,
  posts comments or a review according to the PR review skill.

Expected: review result is either no blockers or named blockers with file/line
evidence.

## Task 11: Review-Fix Loop

**Files:**

- Reserved based only on named blockers from Task 10.

- [ ] If PR review reports blockers, launch a review-fix worker on the same PR
  branch.

Worker constraints:

- Required OpenCode skills: `swarm-review-fix`, `swarm-pr-finish`.
- Fix only named blockers.
- Do not broaden scope.
- Do not revert unrelated changes.
- Commit and push fixes to the PR branch.

- [ ] After review-fix completes, launch a fresh read-only PR review worker
  against the new head SHA.

Expected: loop repeats until no blockers remain or the orchestrator escalates a
disagreement to the human.

## Task 12: Merge-Readiness Verification

**Files:**

- No source edits unless a final blocker appears.

- [ ] Orchestrator personally inspects the final bounded diff:

```bash
git fetch origin feature/remote-macbook-docker-host
git diff --stat origin/dev...origin/feature/remote-macbook-docker-host
git diff origin/dev...origin/feature/remote-macbook-docker-host -- Makefile compose.yml DOCKER.md docs/LOCAL-DEVELOPMENT.md docs/runbooks/remote-macbook-docker.md docs/indexes/local-runtime.md docs/indexes/runtime-services.md docs/runbooks/README.md
```

Expected: diff matches the approved design and plan; no secret values are
present.

- [ ] Run final focused verification:

```bash
git diff --check origin/dev...origin/feature/remote-macbook-docker-host
make remote-docker-status
make remote-env-check
make remote-compose-config
make remote-active-up
make remote-docker-ps
make remote-bot-logs
make remote-service-health
```

Expected: command evidence supports that the MacBook has a working Docker
runtime copy including the bot container.

- [ ] Run final local checks that do not require Docker Desktop:

```bash
make lint
make type-check
make test-unit
```

Expected: pass, or skipped with explicit reason if unrelated existing failures
or runtime constraints block them.

- [ ] Check PR status:

```bash
gh pr checks --watch
gh pr view --json mergeStateStatus,reviewDecision,statusCheckRollup,url
```

Expected: required checks and review state are known before merge.

## Task 13: Merge Or Handoff

**Files:**

- No source edits.

- [ ] If the PR is merge-ready and the user wants merge, merge using the repo's
  preferred method:

```bash
gh pr merge --squash --delete-branch
```

Expected: PR is merged into `dev`, branch deleted remotely, and local branch can
be cleaned up.

- [ ] If merge is not requested, leave the PR open and report:
  - PR URL;
  - current head SHA;
  - review status;
  - runtime status;
  - passing/failing/skipped checks;
  - remaining blockers or risks.

## Task 14: Report Final State

- [ ] Report exact commands run and their outcomes.
- [ ] Report any services still unhealthy by name.
- [ ] Report tests skipped and why.
- [ ] Report whether `.env` was synced, without printing values.
- [ ] Confirm whether Docker Desktop on WSL/Windows was avoided.
- [ ] Report PR URL, review outcome, final head SHA, and merge/handoff status.
