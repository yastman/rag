# VPS Parity Fix Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the local Docker stack the release reference, eliminate local/VPS drift, and enforce a safe `dev -> main -> autodeploy -> VPS smoke` release path.

**Architecture:** The implementation proceeds in four layers: restore local validation, remove config and health-check drift, audit VPS against the validated local reference, and harden deploy verification. Fixes land in `dev`, and only a validated state is promoted to `main`. Each task is scoped to a small set of files and finishes with fresh verification evidence.

**Tech Stack:** Python 3.12, pytest, Ruff, Docker Compose, GitHub Actions, Qdrant, LiteLLM, Telegram bot, Bash scripts, Markdown docs.

---

### Task 1: Restore Ruff Gate

**Files:**
- Modify: `src/evaluation/mlflow_integration.py`

**Step 1: Run the failing lint target**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run ruff check src/evaluation/mlflow_integration.py
```

Expected: FAIL with `I001 Import block is un-sorted or un-formatted`.

**Step 2: Apply the minimal import-order fix**

Update the import block in `src/evaluation/mlflow_integration.py` so Ruff import sorting passes without changing runtime behavior.

**Step 3: Re-run the targeted lint**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run ruff check src/evaluation/mlflow_integration.py
```

Expected: PASS.

**Step 4: Re-run the full quick check**

Run:

```bash
cd /home/user/projects/rag-fresh
make check
```

Expected: either PASS or fail on the next independent issue, but no longer fail on `mlflow_integration.py` import ordering.

**Step 5: Commit**

```bash
git add src/evaluation/mlflow_integration.py
git commit -m "fix: restore ruff gate for evaluation module"
```

### Task 2: Fix Kommo Config Test Isolation

**Files:**
- Modify: `tests/unit/config/test_bot_config_kommo_scoring.py`
- Check: `telegram_bot/config.py`
- Check: `tests/unit/config/test_bot_config_kommo.py`

**Step 1: Reproduce the failing test**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/config/test_bot_config_kommo_scoring.py::test_config_kommo_scoring_fields_default_to_zero -vv
```

Expected: FAIL because the test expects zero defaults and is currently reading non-zero values from environment-backed config state.

**Step 2: Write the failing test adjustment**

Update `tests/unit/config/test_bot_config_kommo_scoring.py` so the test fully isolates config construction from ambient env state. Use the existing config test patterns in `tests/unit/config/test_bot_config_kommo.py` as the reference for how this suite resets or controls environment.

**Step 3: Run the single test to verify it still fails for the right reason**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/config/test_bot_config_kommo_scoring.py::test_config_kommo_scoring_fields_default_to_zero -vv
```

Expected: FAIL only until the isolation fix is complete.

**Step 4: Implement the minimal fix**

Keep production config behavior unchanged unless evidence shows the bug is in `telegram_bot/config.py`. Prefer fixing the test if the failure is caused by leaked environment state rather than broken application logic.

**Step 5: Re-run the config test file**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/config/test_bot_config_kommo_scoring.py -vv
```

Expected: PASS.

**Step 6: Commit**

```bash
git add tests/unit/config/test_bot_config_kommo_scoring.py
git commit -m "test: isolate kommo scoring config defaults"
```

### Task 3: Fix Worktree Script Test Contract

**Files:**
- Modify: `tests/unit/scripts/test_create_worktree.py`
- Check: `scripts/create_worktree.sh`

**Step 1: Reproduce the failing test**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/scripts/test_create_worktree.py::test_create_worktree_honors_explicit_start_point -vv
```

Expected: FAIL because the test expects exit code `128` while the script currently returns `255` from the mocked `git worktree add` path.

**Step 2: Decide the contract boundary**

Review `scripts/create_worktree.sh` and confirm whether the script should normalize git exit codes or whether the test should assert the actual observable failure mode. Prefer changing the test if script behavior is acceptable and used elsewhere.

**Step 3: Update the failing test**

Adjust `tests/unit/scripts/test_create_worktree.py` to assert the stable behavior that matters:

- explicit `start-point` is passed through
- worktree creation fails when git reports branch already exists
- stderr contains the expected git failure signal

Do not overfit to a brittle numeric exit code unless that exit code is a deliberate API contract.

**Step 4: Re-run the targeted test**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/scripts/test_create_worktree.py::test_create_worktree_honors_explicit_start_point -vv
```

Expected: PASS.

**Step 5: Re-run the full script test file**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/scripts/test_create_worktree.py -vv
```

Expected: PASS.

**Step 6: Commit**

```bash
git add tests/unit/scripts/test_create_worktree.py
git commit -m "test: stabilize create_worktree failure contract"
```

### Task 4: Fix CocoIndex Async Test

**Files:**
- Modify: `tests/unit/test_cocoindex_flow.py`
- Check: `src/ingestion/cocoindex_flow.py`

**Step 1: Reproduce the failing test**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/test_cocoindex_flow.py::TestSetupAndRunFlow::test_successful_flow_execution -vv
```

Expected: FAIL because `setup_and_run_flow()` now passes an awaitable into `asyncio.run(...)`, while the test still injects a plain `MagicMock`.

**Step 2: Write the failing async-aware test setup**

Update the mock for `cocoindex.update_all_flows_async` to an awaitable mock such as `AsyncMock`, keeping the rest of the test behavior unchanged.

**Step 3: Re-run the single test before finalizing**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/test_cocoindex_flow.py::TestSetupAndRunFlow::test_successful_flow_execution -vv
```

Expected: FAIL until the async mock is wired correctly.

**Step 4: Implement the minimal fix**

Modify only the test unless evidence shows runtime code is actually broken. Preserve the current async production path in `src/ingestion/cocoindex_flow.py`.

**Step 5: Re-run the targeted file**

Run:

```bash
cd /home/user/projects/rag-fresh
uv run pytest tests/unit/test_cocoindex_flow.py -vv
```

Expected: PASS.

**Step 6: Commit**

```bash
git add tests/unit/test_cocoindex_flow.py
git commit -m "test: update cocoindex flow tests for async updater"
```

### Task 5: Fix Local Bot Health Contract

**Files:**
- Modify: `scripts/test_bot_health.sh`
- Check: `telegram_bot/config.py`
- Check: `docs/LOCAL-DEVELOPMENT.md`
- Check: `DOCKER.md`

**Step 1: Reproduce the local preflight failure**

Run:

```bash
cd /home/user/projects/rag-fresh
make test-bot-health
```

Expected: FAIL because the script defaults to `contextual_bulgaria_voyage` while the active runtime uses a different collection.

**Step 2: Decide the source of truth for collection selection**

Confirm the canonical collection name for the local release reference. Prefer one of these approaches:

- remove the stale hard-coded default and require `QDRANT_COLLECTION`
- align the default with the actual canonical collection

Prefer requiring explicit env if collection naming varies by environment.

**Step 3: Update the script**

Implement the minimal change in `scripts/test_bot_health.sh` so the check validates the actual local runtime contract and does not encode a stale collection default.

**Step 4: Re-run the local preflight**

Run:

```bash
cd /home/user/projects/rag-fresh
make test-bot-health
```

Expected: PASS, or fail only on a real runtime issue rather than the stale default collection name.

**Step 5: Document the contract**

Update `docs/LOCAL-DEVELOPMENT.md` and, if needed, `DOCKER.md` to state how `QDRANT_COLLECTION` must be set for local and VPS health checks.

**Step 6: Commit**

```bash
git add scripts/test_bot_health.sh docs/LOCAL-DEVELOPMENT.md DOCKER.md
git commit -m "fix: align local bot health check with canonical collection"
```

### Task 6: Investigate Mini App Runtime Health

**Files:**
- Check: `compose.yml`
- Check: `compose.dev.yml`
- Check: `compose.vps.yml`
- Check: `mini_app/`
- Check: any mini app Dockerfiles or healthcheck definitions
- Modify: the exact mini app file(s) implicated by the investigation
- Test: add or update the most relevant mini app runtime test if a gap is found

**Step 1: Reproduce the unhealthy state**

Run:

```bash
cd /home/user/projects/rag-fresh
docker compose ps
docker compose logs --since=15m mini-app-frontend mini-app-api
```

Expected: collect evidence showing why `mini-app-frontend` is `unhealthy`.

**Step 2: Write a failing regression test if the issue is code/config-driven**

If the unhealthy state comes from application or config logic that can be unit-tested or integration-tested, add the smallest failing test that captures the problem before changing code.

**Step 3: Implement the minimal fix**

Modify the exact Docker, frontend, or backend config needed to restore health without broad refactoring.

**Step 4: Re-run the runtime check**

Run:

```bash
cd /home/user/projects/rag-fresh
docker compose up -d mini-app-frontend mini-app-api
docker compose ps
```

Expected: `mini-app-frontend` becomes `healthy` if mini app is part of the required stack.

**Step 5: Commit**

```bash
git add compose.yml compose.dev.yml compose.vps.yml mini_app
git commit -m "fix: restore mini app runtime health"
```

### Task 7: Re-run Full Local Release Gate

**Files:**
- No code changes expected unless a new blocker is discovered

**Step 1: Run the full local quick gate**

Run:

```bash
cd /home/user/projects/rag-fresh
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-bot-health
```

Expected: PASS for all three commands.

**Step 2: Capture local runtime evidence**

Run:

```bash
cd /home/user/projects/rag-fresh
docker compose ps
```

Expected: all mandatory local services healthy or explicitly understood if a service is intentionally excluded.

**Step 3: Commit any final follow-up**

If no changes were needed, skip commit. If a new blocker required a fix, commit that fix with a narrowly scoped message.

### Task 8: Freeze Local Release Reference

**Files:**
- Modify: `docs/LOCAL-DEVELOPMENT.md`
- Modify: `DOCKER.md`
- Modify: `README.md`
- Optionally Modify: `docs/plans/2026-03-17-vps-parity-audit-design.md`

**Step 1: Document the canonical local release reference**

Write down:

- mandatory local services
- canonical compose invocation
- required env keys
- canonical Qdrant collection
- required smoke checks

**Step 2: Verify docs against actual commands**

Run each documented command exactly as written where practical.

Expected: docs match current working behavior and do not describe stale collection names or startup paths.

**Step 3: Commit**

```bash
git add docs/LOCAL-DEVELOPMENT.md DOCKER.md README.md docs/plans/2026-03-17-vps-parity-audit-design.md
git commit -m "docs: freeze local release reference for vps parity"
```

### Task 9: Audit VPS Config And Data Parity

**Files:**
- Create: `docs/plans/2026-03-17-vps-parity-audit-report.md`
- Check: `scripts/deploy-vps.sh`
- Check: `.github/workflows/ci.yml`
- Check: VPS `/opt/rag-fresh/.env`

**Step 1: Capture local reference config**

Run:

```bash
cd /home/user/projects/rag-fresh
docker compose -f compose.yml -f compose.vps.yml config > /tmp/local-vps-rendered.yml
docker compose config > /tmp/local-dev-rendered.yml
```

Expected: rendered configs available for comparison.

**Step 2: Capture VPS runtime facts**

Run:

```bash
ssh -i "$HOME/.ssh/vps_access_key" -p 1654 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no admin@95.111.252.29 '
  cd /opt/rag-fresh &&
  docker compose config > /tmp/vps-rendered.yml &&
  docker compose ps &&
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" &&
  printenv | sort > /tmp/vps-env.txt
'
```

Expected: VPS config, status, and environment evidence collected.

**Step 3: Compare critical runtime facts**

Verify:

- collection names
- service list
- healthchecks
- critical env key presence
- mini app exposure
- ingestion target assumptions

**Step 4: Write the audit report**

Create `docs/plans/2026-03-17-vps-parity-audit-report.md` with findings grouped into `P0`, `P1`, `P2`.

**Step 5: Commit**

```bash
git add docs/plans/2026-03-17-vps-parity-audit-report.md
git commit -m "docs: record vps parity audit findings"
```

### Task 10: Fix VPS Drift Findings

**Files:**
- Modify: exact files implicated by the audit, likely among:
  - `compose.vps.yml`
  - `compose.yml`
  - `scripts/deploy-vps.sh`
  - `.github/workflows/ci.yml`
  - docs or service config files

**Step 1: Select the highest-severity finding**

Start with `P0`, then `P1`. Do not batch unrelated findings into one large change.

**Step 2: Write a failing test or executable check**

For each finding, add the smallest guard possible:

- a unit test
- a compose config test
- a shell smoke check
- a rendered config assertion

**Step 3: Run the check to prove failure**

Use the exact command that demonstrates the finding.

Expected: FAIL before the fix.

**Step 4: Implement the minimal fix**

Change only the files necessary to remove the specific drift.

**Step 5: Re-run the check**

Expected: PASS.

**Step 6: Commit**

```bash
git add <exact changed files>
git commit -m "fix: close <finding-id-or-short-description>"
```

Repeat Task 10 until all `P0` and required `P1` findings are closed.

### Task 11: Harden GitHub Autodeploy Verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/deploy-vps.sh` if needed
- Create or Modify: any reusable VPS smoke script, for example `scripts/test_release_health_vps.sh`

**Step 1: Write the failing deploy verification contract**

Add or update a script that checks the mandatory VPS release contract:

- `docker compose ps`
- bot health
- mini app endpoint
- critical service reachability

Run it manually on VPS first and confirm the current workflow does not yet provide the same guarantee.

**Step 2: Integrate the check into workflow logic**

Update `.github/workflows/ci.yml` so deploy verification executes the stronger smoke check after `docker compose up -d`.

**Step 3: Verify the workflow logic locally where possible**

Run shell commands equivalent to the workflow’s SSH script against VPS.

Expected: PASS when VPS is healthy.

**Step 4: Commit**

```bash
git add .github/workflows/ci.yml scripts/deploy-vps.sh scripts/test_release_health_vps.sh
git commit -m "ci: add post-deploy smoke verification for vps"
```

### Task 12: Final Release Verification

**Files:**
- No new code changes expected

**Step 1: Re-run local release-gate**

Run:

```bash
cd /home/user/projects/rag-fresh
make check
PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit
make test-bot-health
```

Expected: PASS.

**Step 2: Re-run VPS smoke manually**

Run:

```bash
ssh -i "$HOME/.ssh/vps_access_key" -p 1654 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no admin@95.111.252.29 '
  cd /opt/rag-fresh &&
  make test-bot-health-vps
'
```

Expected: PASS.

**Step 3: Validate mandatory runtime state**

Run:

```bash
cd /home/user/projects/rag-fresh
docker compose ps
ssh -i "$HOME/.ssh/vps_access_key" -p 1654 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no admin@95.111.252.29 '
  cd /opt/rag-fresh &&
  docker compose ps
'
```

Expected: mandatory services healthy locally and on VPS.

**Step 4: Prepare release**

Only after all prior steps are green:

```bash
git push origin dev
```

Then open PR `dev -> main`.

**Step 5: Post-merge verification**

After merge and autodeploy, run the same VPS smoke again and record the result in the PR or release notes.
