# AGENTS.md

## Purpose
- Define repository-wide instructions for Codex.
- Keep rules concise, deterministic, and conflict-free.
- Keep deep procedures in `docs/agent-rules/*.md` runbooks.

## Scope Resolution
- Instruction precedence follows Codex scope rules:
  1. Root `AGENTS.md` provides baseline rules.
  2. The nearest `AGENTS.override.md` for the target path overrides root rules in that scope.
  3. Deeper nested overrides supersede parent overrides in their own scope.
- Directory-specific guidance belongs only in scoped overrides.
- If external skill instructions conflict with repository AGENTS rules, follow repository AGENTS unless user says otherwise.

## Git Workflow
- **Branch model:** `dev` → `main`. Main = prod (auto-deploy to VPS on push).
- **Default branch for work:** `dev`. Never commit directly to main (pre-commit hook blocks it).
- **Worktrees:** base off `dev`, not main: `git worktree add <path> -b feat/xxx dev`
- **PRs:** target `dev` branch (not main). After merge to dev, deploy: merge dev → main → push.
- Before PR review/diff analysis, refresh remote refs (`git fetch --prune`) and compare against the PR base branch (`origin/<base>`). If base is unknown, use `origin/dev`.

## Workflow
- Before non-trivial edits, read:
  - `README.md`
  - nearest `AGENTS*.md`
  - at least one relevant `docs/agent-rules/*.md` runbook for the changed area
- For behavior changes, add or update tests in the nearest `tests/` scope.
- Run pytest in parallel mode (`-n auto --dist=worksteal`) unless explicitly told otherwise.

## Skill Routing
- If user explicitly names a skill, use it.
- At conversation start (if no explicit skill), run discovery via `using-superpowers`.
- If multiple skills apply, prefer this order:
  1. process (`using-superpowers`, `systematic-debugging`, `writing-plans`)
  2. execution (`executing-plans`, `subagent-driven-development`, `test-driven-development`)
  3. verification/review (`verification-before-completion`, `comprehensive-pr-review`, `requesting-code-review`)

### Default Skills For This Repo
- `systematic-debugging`: any bug/failure/flaky behavior before proposing fixes.
- `test-driven-development`: feature/bugfix behavior changes.
- `test-suite-optimizer`: pytest/xdist speed, flakiness, test-tiering, gate strategy.
- `writing-plans`: multi-step work requiring implementation plan first.
- `executing-plans`: execute approved plan in batches with checkpoints.
- `verification-before-completion`: mandatory before completion claims.
- `using-git-worktrees`: isolated implementation/review work.
- `comprehensive-pr-review`: PR-wide findings + verification + remediation.
- `plan-reviewer`: plan-only review and point edits (without implementation).

### Situational Skills
- `brainstorming`: ambiguous requirements or architecture exploration before coding.
- `subagent-driven-development`: when plan tasks are independent and reviewer loops are desired.
- `requesting-code-review` / `receiving-code-review`: structured review exchange after milestones.
- `finishing-a-development-branch`: explicit branch wrap-up / merge / cleanup flow.
- `claude-md-writer`: editing `AGENTS.md` / `AGENTS.override.md` docs.

### Deprioritized Skills (Not Default For Product Work)
- `skill-creator`, `writing-skills`, `.system/skill-creator`, `.system/skill-installer`: only for Codex skill catalog maintenance.
- `dispatching-parallel-agents`: use only for truly independent failures with no shared state; otherwise prefer `systematic-debugging`.

## Required Verification
- Minimum gate before completion for code/runtime changes:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- For docs/plan-only changes (no runtime/test/infra code changes), skip full test gate and run documentation validation from:
  - `docs/agent-rules/testing-and-validation.md`
- For infra/integration/runtime-sensitive changes, run targeted checks from:
  - `docs/agent-rules/testing-and-validation.md`
- If required gates fail due to pre-existing or out-of-scope failures, do not silently ignore:
  - report exact failing tests with command output summary;
  - avoid bundling unrelated fixes unless user explicitly requests;
  - link an existing tracking issue or create one per Issue Policy.

## Issue Policy
- Do not auto-create issues by default.
- Create/update an issue only when:
  - user explicitly requests it; or
  - review finds a new unresolved `High`/`Medium` defect outside current change scope and no duplicate issue exists.
- Before creating a new issue, deduplicate with `gh issue list --state open --search "<keywords>"`.
- `Low` severity findings stay in PR comments unless user asks for issue tracking.

## Safety
- Do not run destructive git commands (`git reset --hard`, `git checkout --`, force-push) unless explicitly requested.
- Do not commit `.env` secrets.
- Prefer minimal, focused diffs.
- Capture `git status --short --branch` at start and end of non-trivial tasks.
- Preserve unrelated dirty files/worktree state; never revert changes you did not make.
- Keep all AGENTS files concise (target <= 200 lines).

## Project Map
- `telegram_bot/` - LangGraph bot pipeline and integrations.
- `src/api/` - FastAPI RAG endpoint.
- `src/voice/` - LiveKit/SIP voice integration.
- `src/ingestion/unified/` - unified ingestion runtime.
- `src/retrieval/` - search engines and retrieval logic.
- `src/evaluation/` - retrieval/RAG evaluation tooling.
- `k8s/` - k3s manifests and overlays.
- `docs/` - operational docs and plans.

## Canonical References
- `README.md`
- `docs/PROJECT_STACK.md`
- `docs/PIPELINE_OVERVIEW.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/QDRANT_STACK.md`
- `docs/INGESTION.md`
- `docs/ALERTING.md`
- `docs/agent-rules/workflow.md`
- `docs/agent-rules/testing-and-validation.md`
- `docs/agent-rules/infra-and-deploy.md`
- `docs/agent-rules/architecture-map.md`
- `docs/agent-rules/project-analysis.md`
- `docs/agent-rules/skills-authoring.md`
