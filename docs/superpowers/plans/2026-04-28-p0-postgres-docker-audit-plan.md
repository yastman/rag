# P0 Postgres Docker Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `#1081` with fresh Postgres shutdown evidence, audit the local Docker Compose runtime, and create separate GitHub issues for newly discovered broken services.

**Architecture:** Treat `#1081` as a root-cause/evidence close-out, not a catch-all Docker cleanup. Keep runtime findings in a dated audit report, update only the relevant runbook/docs, and turn distinct reproducible service failures into their own GitHub issues. Use Docker Compose native env/config handling and avoid destructive volume or database operations.

**Tech Stack:** Docker Compose, PostgreSQL/pgvector container, GitHub CLI, pytest, shell scripts, Markdown runbooks.

---

## File Structure

- Modify: `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md`
  - Add a short shutdown-safety and Docker Desktop WSL bind-mount recovery section.
- Create: `docs/plans/2026-04-28-docker-runtime-audit-report.md`
  - Capture commands, service inventory, health status, failures, and created issue links.
- Reference only: `compose.yml`, `compose.dev.yml`, `tests/unit/test_compose_config.py`, `scripts/test_bot_health.sh`
  - Use these for validation; do not modify unless the audit proves a missing repo guardrail.
- GitHub: `#1081`
  - Close or update with evidence after validation.
- GitHub: new issues as needed
  - Create only for distinct, reproducible failures not already tracked.

## Task 1: Confirm Clean Working Context And Issue State

**Files:**
- Read: `docs/superpowers/specs/2026-04-28-p0-postgres-docker-audit-design.md`
- Read: `docs/superpowers/plans/2026-04-28-p0-postgres-docker-audit-plan.md`
- Read: GitHub issue `#1081`

- [ ] **Step 1: Check branch and worktree**

Run:

```bash
git branch --show-current
git status --short
```

Expected: branch is `dev`; only known unrelated untracked Hermes docs may be present.

- [ ] **Step 2: Re-read the issue**

Run:

```bash
gh issue view 1081 --json number,title,body,labels,comments,url
```

Expected: issue is still open and still describes Postgres unclean shutdown/WAL recovery.

- [ ] **Step 3: Check for duplicate Docker/Postgres issues before creating new ones later**

Run:

```bash
gh issue list --state open --limit 100 --json number,title,labels --jq \
  '.[] | select((.title | test("postgres|docker|compose|container|health|runtime"; "i")) or ([.labels[].name] | any(. == "infra"))) | {number,title,labels: [.labels[].name]}'
```

Expected: existing related issues are visible so new issues do not duplicate tracked work.

## Task 2: Verify Postgres Shutdown Contract For `#1081`

**Files:**
- Reference: `compose.yml`
- Reference: `compose.dev.yml`
- Test: `tests/unit/test_compose_config.py`
- Report: `docs/plans/2026-04-28-docker-runtime-audit-report.md`

- [ ] **Step 1: Render effective compose config**

Run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config \
  | sed -n '/^  postgres:/,/^  [a-zA-Z0-9_-]\+:/p'
```

Expected: rendered `postgres` service includes `stop_grace_period: 30s`.

- [ ] **Step 2: Run the existing shutdown contract test**

Run:

```bash
uv run pytest tests/unit/test_compose_config.py::TestPostgresShutdownSafety::test_postgres_has_explicit_stop_grace_period -q
```

Expected: PASS.

- [ ] **Step 3: Ensure Postgres is running through Compose**

Run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d postgres
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps postgres
```

Expected: `postgres` is running or healthy. If a stale bind mount blocks startup, record the full error and retry with:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --force-recreate postgres
```

- [ ] **Step 4: Inspect live timeout and signal**

Run:

```bash
container="$(COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps -q postgres)"
docker inspect "$container" --format 'Name={{.Name}} StopTimeout={{json .Config.StopTimeout}} StopSignal={{json .Config.StopSignal}} RestartPolicy={{json .HostConfig.RestartPolicy}} OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}'
```

Expected: `StopTimeout=30`, `StopSignal="SIGINT"`, `OOMKilled=false`.

- [ ] **Step 5: Run a controlled Compose stop/start**

Run:

```bash
before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility stop postgres
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d postgres
sleep 3
container="$(COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps -q postgres)"
docker logs "$container" --since "$before" 2>&1
```

Expected: logs include `database system was shut down at ...` on restart and do not include `database system was interrupted` for the controlled stop/start window.

- [ ] **Step 6: Record evidence in the audit report**

Add a `#1081 Postgres Evidence` section to `docs/plans/2026-04-28-docker-runtime-audit-report.md` with:

- timestamp
- rendered config result
- pytest result
- inspect result
- controlled stop/start log summary
- any stale bind-mount error observed

## Task 3: Update Postgres Runbook

**Files:**
- Modify: `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md`
- Report: `docs/plans/2026-04-28-docker-runtime-audit-report.md`

- [ ] **Step 1: Add the minimal runbook section**

Append a section named `Shutdown Safety And Local Docker Desktop Recovery` that says:

```markdown
## Shutdown Safety And Local Docker Desktop Recovery

The Compose contract gives Postgres at least 30 seconds to shut down cleanly:

    COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config \
      | sed -n '/^  postgres:/,/^  [a-zA-Z0-9_-]\+:/p'

If Docker Desktop/WSL reports a stale bind mount when starting an existing container directly, recreate the service through Compose instead of using `docker start`:

    COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --force-recreate postgres

Do not delete the Postgres volume unless a recovery plan explicitly calls for it and a backup exists.
```

- [ ] **Step 2: Verify Markdown formatting manually**

Run:

```bash
sed -n '1,180p' docs/runbooks/POSTGRESQL_WAL_RECOVERY.md
```

Expected: headings and fenced blocks render correctly.

- [ ] **Step 3: Commit runbook and audit report draft**

Run:

```bash
git add docs/runbooks/POSTGRESQL_WAL_RECOVERY.md docs/plans/2026-04-28-docker-runtime-audit-report.md
git commit -m "docs: document postgres shutdown recovery evidence"
```

Expected: commit succeeds; pre-commit passes.

## Task 4: Audit Local Docker Compose Runtime

**Files:**
- Report: `docs/plans/2026-04-28-docker-runtime-audit-report.md`
- Reference: `compose.yml`
- Reference: `compose.dev.yml`
- Reference: `scripts/test_bot_health.sh`

- [ ] **Step 1: Capture effective service list**

Run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
```

Expected: service list is captured in the audit report.

- [ ] **Step 2: Capture current container status**

Run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps --all
docker ps -a --filter "label=com.docker.compose.project=dev" --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
```

Expected: statuses are captured; `Restarting`, `Dead`, `unhealthy`, and non-zero `Exited` services are marked as failures.

- [ ] **Step 3: Start the local core/default service set**

Run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d postgres redis qdrant bge-m3 user-base docling
```

Expected: command succeeds or each failure is recorded with logs.

- [ ] **Step 4: Check core service health**

Run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps postgres redis qdrant bge-m3 user-base docling
docker ps -a --filter "label=com.docker.compose.project=dev" --format '{{.Names}}\t{{.Status}}' \
  | grep -E 'postgres|redis|qdrant|bge|user-base|docling' || true
```

Expected: services are running or healthy. Failures are recorded.

- [ ] **Step 5: Run local bot health helper if dependencies are available**

Run:

```bash
make test-bot-health
```

Expected: PASS, or record the precise failing dependency and whether it is already tracked.

- [ ] **Step 6: Audit profile-gated groups without destructive cleanup**

Run each group separately, recording output:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --profile bot --compatibility up -d litellm bot
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --profile voice --compatibility up -d rag-api livekit livekit-sip voice-agent
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --profile ml --compatibility up -d clickhouse minio redis-langfuse langfuse-worker langfuse
```

Expected: services either start successfully or fail with actionable logs. Missing production secrets are not counted as local runtime bugs unless local defaults are promised by docs/compose.

- [ ] **Step 7: Capture failure logs**

For each failed service, run:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose logs --tail 120 <service>
docker inspect "$(COMPOSE_FILE=compose.yml:compose.dev.yml docker compose ps -q <service>)" --format '{{json .State}}' || true
```

Expected: logs and state are summarized in the audit report.

- [ ] **Step 8: Commit completed audit report**

Run:

```bash
git add docs/plans/2026-04-28-docker-runtime-audit-report.md
git commit -m "docs: add local docker runtime audit report"
```

Expected: commit succeeds if the report changed after the previous commit.

## Task 5: Create GitHub Issues For New Failures

**Files:**
- Report: `docs/plans/2026-04-28-docker-runtime-audit-report.md`
- GitHub: new issues only as needed

- [ ] **Step 1: Compare failures against open issues**

Run:

```bash
gh issue list --state open --limit 100 --json number,title,labels,url
```

Expected: every audit failure is classified as already tracked, expected/out of local scope, or new issue needed.

- [ ] **Step 2: Create issue body files for new failures**

For each distinct new failure, create a temporary body file under `/tmp`, for example:

```markdown
## Summary
Local Docker runtime audit found `<service>` failing during `<command>`.

## Evidence
- Timestamp: 2026-04-28T...
- Command: `...`
- Status: `...`
- Logs:

      ...

## Expected
The service should start in the documented local Compose profile, or docs should state required prerequisites.

## Audit Source
Found during the 2026-04-28 local Docker runtime audit while closing #1081.

## Proposed Triage
- Priority: P1-next or P2-backlog
- Lane: lane:quick-execution or lane:plan-needed
- Labels: infra, bug
```

- [ ] **Step 3: Create GitHub issues**

Run:

```bash
gh issue create \
  --title "infra: <service> fails local Docker runtime audit" \
  --body-file /tmp/<issue-body>.md \
  --label infra \
  --label bug \
  --label "lane:plan-needed"
```

Expected: issue URL is returned and copied into the audit report.

- [ ] **Step 4: Commit issue links into the audit report**

Run:

```bash
git add docs/plans/2026-04-28-docker-runtime-audit-report.md
git commit -m "docs: link docker audit follow-up issues"
```

Expected: commit succeeds if new issues were created.

## Task 6: Close Or Update `#1081`

**Files:**
- Report: `docs/plans/2026-04-28-docker-runtime-audit-report.md`
- GitHub: `#1081`

- [ ] **Step 1: Prepare the close-out comment**

Create `/tmp/issue-1081-closeout.md` with:

```markdown
Resolved/verified in the 2026-04-28 audit.

Evidence:
- `compose.yml` now declares `postgres.stop_grace_period: 30s`.
- Live container exposes `StopTimeout=30` and Postgres image `SIGINT` stop signal.
- Controlled Compose stop/start produced clean shutdown evidence.
- Existing shutdown contract test passed.

Operational note:
- Direct `docker start` can fail under Docker Desktop/WSL when bind mounts are stale.
- Recovery path is `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility up -d --force-recreate postgres`.

Audit report:
- `docs/plans/2026-04-28-docker-runtime-audit-report.md`

Follow-up issues:
- <list new Docker audit issues or "none">
```

- [ ] **Step 2: Close `#1081` if evidence supports closure**

Run:

```bash
gh issue close 1081 --comment-file /tmp/issue-1081-closeout.md
```

Expected: issue closes. If evidence does not support closure, comment with the blocker instead and leave it open.

- [ ] **Step 3: Verify issue state**

Run:

```bash
gh issue view 1081 --json number,state,title,url
```

Expected: `state` is `CLOSED`, unless a blocker was documented.

## Task 7: Final Verification

**Files:**
- Modified docs from previous tasks

- [ ] **Step 1: Run focused docs/static checks**

Run:

```bash
git status --short
git log --oneline -5
```

Expected: only unrelated pre-existing untracked Hermes docs remain; commits are visible.

- [ ] **Step 2: Run repo baseline checks if code/config changed**

If only docs and GitHub issue comments changed, skip `make check` and `make test-unit` with a note. If any code, Compose, scripts, or tests changed, run:

```bash
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
```

Expected: PASS or documented failure unrelated to the change.

- [ ] **Step 3: Summarize results**

Report:

- `#1081` final state
- audit report path
- new issue URLs
- verification commands and results
- skipped checks and rationale
