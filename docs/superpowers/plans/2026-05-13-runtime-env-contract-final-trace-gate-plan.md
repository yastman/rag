# Runtime Env Contract Final Trace Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local runtime verification reproducible from swarm worktrees, then finish the remaining Langfuse trace gate once the external Telegram/voice prerequisites are available.

**Architecture:** Split the work into two parts: first, fix the repo/orchestration env contract so non-secret Compose defaults and root `.env` runtime credentials are loaded explicitly instead of depending on the worker worktree. Second, rerun the final runtime gate through `tmux-swarm-orchestration` and close `#1486` only after an approved voice fixture is supplied. Do not copy secrets into worktrees or commit fixture audio without approval.

**Tech Stack:** GNU Make, Docker Compose v2, `uv`, Python E2E runner, Telethon, Langfuse SDK/CLI audit, pytest, tmux/OpenCode swarm workers.

---

## Current State

- PR `#1504` is merged and issue `#1490` is closed.
- Runtime health checks passed on 2026-05-13 for:
  - Langfuse `http://localhost:3001/api/public/health`
  - LiteLLM `http://localhost:4000/health/readiness`
  - Qdrant `http://localhost:6333/readyz`
  - mini-app API `http://localhost:8090/health`
  - mini-app frontend `http://localhost:8091/health`
  - rag-api `http://localhost:8080/health`
  - bge-m3 `http://localhost:8000/health`
- Final worker `W-final-runtime-verify-20260513` blocked on:
  - `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` missing from the runtime environment.
  - direct `docker compose ps` from a worktree missing `GDRIVE_SYNC_DIR`.
- `#1486` remains externally blocked until an approved non-secret `.ogg/.oga/.opus` voice fixture exists and `E2E_VOICE_NOTE_PATH` points to it.

## File Structure

- Modify `Makefile`
  - Add a reusable `RAG_RUNTIME_ENV_FILE` variable that defaults to root `.env` when present, otherwise `tests/fixtures/compose.ci.env`.
  - Make `e2e-telegram-test`, `e2e-test-traces`, and `e2e-test-traces-core` run through `uv run --env-file "$$RAG_RUNTIME_ENV_FILE" ...`.
  - Add a worker-safe `runtime-ps` or update docs/prompts to use existing `make docker-ps`, not raw `docker compose ps`.
- Modify `tests/unit/test_makefile_contract.py`
  - Assert E2E trace targets use `--env-file "$$RAG_RUNTIME_ENV_FILE"`.
  - Assert `RAG_RUNTIME_ENV_FILE` fallback includes `tests/fixtures/compose.ci.env`.
- Modify `docs/LOCAL-DEVELOPMENT.md`
  - Document the env contract for worktrees: Compose uses `tests/fixtures/compose.ci.env` for non-secret interpolation; Telethon uses root `.env` via explicit `RAG_RUNTIME_ENV_FILE=/abs/path/.env`.
- Modify `/home/USER/.codex/skills/tmux-swarm-orchestration/worker-contract.md` or `references/prompt-snippets.md`
  - Runtime worker prompts must use Make targets or explicit env-file paths.
  - Do not ask workers to run raw `docker compose ps` from isolated worktrees.
- Optional issue update only
  - Add a final comment to `#1486` after rerun, with artifact paths and exact blocker/pass status.

## Task 1: Make E2E Trace Targets Env-File Aware

**Files:**
- Modify: `Makefile`
- Test: `tests/unit/test_makefile_contract.py`

- [ ] **Step 1: Write failing Makefile contract tests**

Add tests near the existing `e2e-test-traces-core` tests:

```python
def test_e2e_trace_targets_use_runtime_env_file() -> None:
    text = _makefile_text()
    for target in ("e2e-telegram-test", "e2e-test-traces", "e2e-test-traces-core"):
        block_match = re.search(
            rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\\Z)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        assert block_match, f"{target} target not found in Makefile"
        block = block_match.group(0)
        assert '--env-file "$$RAG_RUNTIME_ENV_FILE"' in block


def test_runtime_env_file_has_safe_fallback() -> None:
    text = _makefile_text()
    assert "RAG_RUNTIME_ENV_FILE" in text
    assert "tests/fixtures/compose.ci.env" in text
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
uv run pytest tests/unit/test_makefile_contract.py::test_e2e_trace_targets_use_runtime_env_file tests/unit/test_makefile_contract.py::test_runtime_env_file_has_safe_fallback -q
```

Expected: FAIL because current E2E Make targets call `uv run python` without `--env-file`.

- [ ] **Step 3: Add runtime env variable in `Makefile`**

Near `LOCAL_COMPOSE_CMD`, add:

```make
RAG_RUNTIME_ENV_FILE ?= $$( [ -f .env ] && echo .env || echo tests/fixtures/compose.ci.env )
```

- [ ] **Step 4: Update E2E Make targets**

Change:

```make
uv run python scripts/e2e/runner.py
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1 --scenario 8.1
```

To:

```make
uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py
E2E_VALIDATE_LANGFUSE=1 uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py
E2E_VALIDATE_LANGFUSE=1 uv run --env-file "$$RAG_RUNTIME_ENV_FILE" python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1 --scenario 8.1
```

- [ ] **Step 5: Run focused Makefile tests**

Run:

```bash
uv run pytest tests/unit/test_makefile_contract.py tests/unit/test_local_compose_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add Makefile tests/unit/test_makefile_contract.py
git commit -m "fix(e2e): load runtime env file for trace gates"
```

## Task 2: Document Worktree Runtime Env Contract

**Files:**
- Modify: `docs/LOCAL-DEVELOPMENT.md`

- [ ] **Step 1: Add a short documentation section**

Add after the Telegram E2E prerequisites:

```markdown
Runtime env in worktrees:
- Compose commands must use `$(LOCAL_COMPOSE_CMD)` or `docker compose --env-file tests/fixtures/compose.ci.env ...` so non-secret interpolation values such as `GDRIVE_SYNC_DIR` are available.
- Telethon/E2E commands must use `uv run --env-file "$RAG_RUNTIME_ENV_FILE" ...`.
- For swarm worktrees, set `RAG_RUNTIME_ENV_FILE=/repo/.env` when local Telegram credentials live only in the main checkout.
- Do not copy `.env`, Telegram sessions, or provider keys into worker worktrees.
```

- [ ] **Step 2: Run docs-adjacent tests**

Run:

```bash
uv run pytest tests/unit/test_env_example.py tests/unit/test_local_compose_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/LOCAL-DEVELOPMENT.md
git commit -m "docs: clarify runtime env use from worktrees"
```

## Task 3: Patch Swarm Runtime Prompt Guidance

**Files:**
- Modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/worker-contract.md`
- Optional modify: `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
- Test: `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/`

- [ ] **Step 1: Add a failing contract test**

In the swarm skill tests, add or update a contract assertion that runtime worker guidance contains:

```python
assert "RAG_RUNTIME_ENV_FILE" in worker_contract
assert "Do not run raw `docker compose" in worker_contract
assert "tests/fixtures/compose.ci.env" in worker_contract
```

- [ ] **Step 2: Run the target test**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/test_skill_docs_contract.py
```

Expected: FAIL before guidance is added.

- [ ] **Step 3: Update worker prompt guidance**

Add a concise runtime-worker rule:

```markdown
Runtime workers must not run raw `docker compose ...` from isolated worktrees.
Use repo Make targets that include `$(LOCAL_COMPOSE_CMD)`, or pass
`--env-file tests/fixtures/compose.ci.env` for non-secret Compose interpolation.
For Telethon/E2E runtime credentials, use an explicit
`RAG_RUNTIME_ENV_FILE=/abs/path/to/main/.env` and `uv run --env-file "$RAG_RUNTIME_ENV_FILE" ...`.
Never copy `.env`, Telegram session files, or provider keys into a worker worktree.
```

- [ ] **Step 4: Run skill validation**

Run:

```bash
uv run pytest -q /home/USER/.codex/skills/tmux-swarm-orchestration/tests/
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py /home/USER/.codex/skills/tmux-swarm-orchestration
```

Expected: PASS.

- [ ] **Step 5: Commit or record skill maintenance**

If the skill directory is versioned separately, commit there. If not, append a short note to:

```text
/home/USER/.codex/swarm-feedback/rag-fresh.md
```

with evidence, fix, and validation.

## Task 4: Launch a Runtime Verification Worker With Fixed Env Contract

**Files:**
- Create: `.codex/prompts/worker-final-runtime-verify-r2.md`
- Worktree: `/repo-wt-final-runtime-verify-r2`
- Signal: `/repo-wt-final-runtime-verify-r2/.signals/W-final-runtime-verify-r2.json`

- [ ] **Step 1: Create a clean worktree**

Run from main checkout:

```bash
git fetch origin dev
git worktree add /repo-wt-final-runtime-verify-r2 -b swarm/final-runtime-verify-r2 origin/dev
mkdir -p /repo-wt-final-runtime-verify-r2/.signals /repo-wt-final-runtime-verify-r2/logs
```

- [ ] **Step 2: Prepare worker prompt**

Prompt must include:

```text
WORKER MODEL: runner=opencode; agent=pr-worker; model=opencode-go/kimi-k2.6
Docs lookup policy: forbidden
SDK/custom decision: sdk_native_check:not_applicable
RAG_RUNTIME_ENV_FILE=/repo/.env
Use `make docker-ps`, not raw `docker compose ps`.
Run: RAG_RUNTIME_ENV_FILE=/repo/.env make e2e-test-traces-core
If voice fixture is absent, return blocked and do not invent audio.
If core gate passes, run: uv run --env-file /repo/.env python -m scripts.e2e.langfuse_latest_trace_audit --limit 12 --output-dir .artifacts/langfuse-local-audit --sdk-only
```

- [ ] **Step 3: Route-check if multiple Codex panes exist**

Run:

```bash
ORCH_MARKER="$PROJECT_ROOT/.signals/orchestrator-pane.json" \
/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/set_orchestrator_pane.sh --ensure-window-name final-runtime-r2
```

If multiple live Codex/node panes exist, send a nonce and launch only after it appears in the intended chat.

- [ ] **Step 4: Launch worker**

Run:

```bash
OPENCODE_AGENT=pr-worker \
OPENCODE_MODEL=opencode-go/kimi-k2.6 \
OPENCODE_REQUIRED_SKILLS= \
SWARM_LOCAL_ONLY=1 \
ORCH_MARKER="$PROJECT_ROOT/.signals/orchestrator-pane.json" \
/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh \
  W-final-runtime-verify-r2 \
  /repo-wt-final-runtime-verify-r2 \
  /repo/.codex/prompts/worker-final-runtime-verify-r2.md
```

- [ ] **Step 5: Validate terminal signal**

Run after `[DONE]`:

```bash
/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py \
  --role quick \
  --signal /repo-wt-final-runtime-verify-r2/.signals/W-final-runtime-verify-r2.json \
  --launch /repo-wt-final-runtime-verify-r2/.signals/launch-W-final-runtime-verify-r2.json \
  --registry .signals/active-workers.jsonl \
  --worker W-final-runtime-verify-r2
```

Expected:
- PASS if env credentials and fixture exist.
- BLOCKED if `TELEGRAM_API_ID`/`TELEGRAM_API_HASH`, authorized Telethon session, or `E2E_VOICE_NOTE_PATH` are still absent.

## Task 5: Close or Re-Block Issue `#1486`

**Files:**
- GitHub issue only: `#1486`

- [ ] **Step 1: If voice gate passes, close issue**

Run:

```bash
gh issue close 1486 --comment "Fixed: full voice trace gate passed with approved non-secret fixture. Evidence: <worker signal path>, latest-trace audit artifact: <path>."
```

- [ ] **Step 2: If voice gate remains blocked, update issue**

Run:

```bash
gh issue comment 1486 --body "Still blocked after env-contract fix. Runtime env now loads correctly; remaining blocker is <exact missing prerequisite>. Evidence: <worker signal path>."
```

- [ ] **Step 3: Cleanup worker artifacts**

Run:

```bash
git worktree remove /repo-wt-final-runtime-verify-r2
git branch -D swarm/final-runtime-verify-r2
python3 /home/USER/.codex/skills/tmux-swarm-orchestration/scripts/registry_state.py --registry .signals/active-workers.jsonl
```

Expected: no current active OpenCode workers related to final runtime verification.

## Acceptance Criteria

- E2E Make targets use an explicit runtime env file.
- Compose status/runtime commands no longer fail in worktrees because of missing `GDRIVE_SYNC_DIR`.
- Swarm runtime prompts no longer ask workers to run raw `docker compose ...` without `--env-file` or Make wrapper.
- Final runtime verification worker is launched through `tmux-swarm-orchestration` on `opencode-go/kimi-k2.6`.
- `#1486` is either closed with passing voice trace evidence or updated with a single exact remaining external blocker.

## Residual Risks

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and authorized Telethon session are real credentials/state and must remain outside the repo.
- Voice fixture cannot be generated or committed without explicit approval and license/privacy safety.
- Main checkout currently contains unrelated docs/worktree changes; workers should use isolated worktrees and avoid cleanup outside their reserved scope.
