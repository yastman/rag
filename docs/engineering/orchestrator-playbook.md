# Orchestrator Playbook

## Purpose

This file defines how the orchestrator should manage work in `yastman/rag`.

The orchestrator does not act like a normal implementation worker. The orchestrator protects `dev`, coordinates worker packs, audits PRs, identifies process failures, and continuously improves the worker/reviewer prompts so the same class of mistake does not repeat.

Read this file before planning worker batches, reviewing worker output, approving PRs, or deciding whether a PR is ready to merge.

---

## Core Operating Rule

```text
Fix the system, not only the current PR.
```

After every worker mistake, the orchestrator must ask:

```text
Was this a code bug, a validation gap, a PR process failure, or a prompt failure?
```

If the root cause is process/prompt-related, propose a concrete update to the relevant prompt, skill, PR template, or contract test.

## Self-Updating Skill Loop

When the orchestrator finds a new recurring bug, it must turn that bug into a durable rule and open a separate process PR to update the right skill file.

Route the rule by ownership:

```text
orchestrator coordination bug -> docs/engineering/orchestrator-playbook.md
worker execution bug -> docs/engineering/codex-web-prompt.md
PR review / gatekeeper bug -> docs/engineering/gh-pr-review.md
PR body / handoff bug -> .github/pull_request_template.md or reviewer skill
must-never-repeat invariant -> tests/unit/test_agents_contract.py
```

Rules:

```text
- Do not bury process fixes inside unrelated runtime PRs.
- If a worker bug is found during review, keep the feature PR focused and create a separate process PR.
- If multiple orchestrators are active, each may create a process PR; the human merges the chosen one into dev.
- The process PR must describe the original failure, the new rule, and which skill owns it.
- If the rule should never regress, add or request an agent contract test.
```

## Worker Prompt Writing

The orchestrator writes task prompts for Codex Web workers. A new orchestrator should be able to read this playbook and produce a complete copy-paste prompt without needing hidden context.

Choose the mode and skill first:

```text
existing PR review/fix -> PR Coordinator -> docs/engineering/gh-pr-review.md
new issue implementation -> Issue Executor -> docs/engineering/codex-web-prompt.md
process/skill update -> process PR -> this playbook + skill-maintenance-guardrails.md
audit only / planning -> Audit Planner -> this playbook
```

A worker prompt must name exactly one primary skill/doc. Do not list multiple skills as equal authorities. If supporting docs are useful, mention them only under context/source-of-truth and keep the primary skill singular.

A worker prompt must include:

```text
Mode / skill:
- Which mode to use.
- Which single primary skill/doc to follow.
- Whether to create a new PR, update an existing PR, or only audit.

Context:
- Repo, base branch, issue/PR number, branch if known.
- What the orchestrator already verified.
- Current blockers/findings.

Source of truth:
- Issue body.
- Recent issue comments.
- Linked audit docs.
- PR review comments or Agent Handoff.

Scope:
- Exact files/subsystems to change.
- Exact behavior to preserve.
- What counts as done.

Non-scope / forbidden:
- No unrelated refactors.
- No workflow/process/control-plane edits in runtime PRs.
- No broad dependency changes unless explicitly in scope.
- Do not merge unless explicitly instructed.

Tasks:
1. Concrete ordered steps.
2. Required searches/preflights.
3. Required code/docs/test changes.

Validation:
- Exact focused commands to run.
- Exact CI-equivalent static commands when needed.
- Explicit skipped checks wording if Docker/K8s/secrets are unavailable.

Handoff:
- PR URL.
- Base/head/head SHA.
- Tests run/skipped.
- Blockers.
- Follow-up issues.
- Agent Handoff with Validated commit.

Skill update hook:
- If the worker discovers a recurring process bug, do not fix the skill inside the runtime PR.
- Report the proposed owner and rule text so the orchestrator can open a separate process PR.
```

Copyable default worker prompt shape:

```text
Ты работаешь в repo `yastman/rag`.

Mode / skill:
- Use <Issue Executor | PR Coordinator | Audit Planner>.
- Follow exactly one primary skill/doc: `<skill/doc path>`.
- Base branch is `dev`.
- Do not merge unless explicitly instructed.

Context:
- Issue/PR: <number and title>.
- Current branch/head if applicable: <branch/sha>.
- Relevant findings: <short bullets>.

Source of truth:
- Read the issue body.
- Read recent issue comments.
- Read linked audit docs: <paths or none>.
- If issue comments re-scope the issue, use the latest re-scope and document stale checklist items.

Scope:
- Change only: <files/subsystems>.
- Preserve: <contracts/behavior>.
- Done means: <acceptance criteria>.

Non-scope / forbidden:
- Do not create duplicate PRs.
- Do not touch process/control-plane files unless this is a process PR.
- Do not broaden into unrelated baseline cleanup.
- Do not skip/delete/weaken tests to pass.

Tasks:
1. <step>
2. <step>
3. <step>

Validation:
Run:
```bash
<focused commands>
```

If Python paths changed, also run:
```bash
uvx ruff check src/ telegram_bot/ mini_app/ services/ scripts/ --output-format=github
uvx ruff format --target-version py312 --check src/ telegram_bot/ mini_app/ services/ scripts/
uv lock --locked
```

If Docker/K8s/live services are unavailable, document exactly what was skipped and why.

Handoff:
Update PR body/comment with:
- Status
- Base
- Head
- Validated commit
- Risk
- Failure class
- Validation checklist
- Findings
- Next action
```

Example PR Coordinator prompt:

```text
Ты работаешь в repo `yastman/rag`.

Mode / skill:
- Use PR Coordinator mode.
- Follow exactly one primary skill/doc: `docs/engineering/gh-pr-review.md`.
- Update existing PR #<number>; do not create a duplicate PR.
- Do not merge unless explicitly instructed.

Context:
- PR #<number>: <title>.
- Base must be `dev`.
- Current blockers from orchestrator review:
  - <blocker 1>
  - <blocker 2>

Source of truth:
- Read PR body, comments, labels, changed files, and Agent Handoff.
- Read related issues and recent issue comments.
- If issue comments re-scope the work, use the latest re-scope.

Tasks:
1. Rebase on current `origin/dev` if stale.
2. Fix only the listed blockers.
3. Add or update focused tests for changed behavior.
4. Update PR body with complete Agent Handoff.
5. Report remaining blockers instead of broadening scope.

Validation:
Run focused tests for touched files plus required static checks.
Report skipped Docker/K8s/live checks with reason.

Handoff:
Return PR URL, head SHA, validation results, skipped checks, findings, and next action.
```

---

## Role Separation

Use separate mental modes.

### Issue Worker

The issue worker implements a scoped issue.

Rules:

```text
Worker pack = queue, not one PR.
1 issue = 1 branch = 1 PR.
Before each issue: duplicate PR preflight.
Do not mix unrelated issues.
Do not merge.
```

### PR Reviewer / Gatekeeper

The reviewer audits and protects `dev`.

Use:

```text
skills/gh-pr-review.md
```

Reviewer responsibilities:

```text
inspect PR -> classify risk -> check scope -> validate -> safe autofix -> block or approve merge
```

Reviewer must not become a second feature worker.

Allowed reviewer autofix:

```text
- Ruff format/check issues
- import sorting
- PR body / handoff updates
- obvious test path updates after file moves
- small PR-caused fixes with focused test coverage
```

Forbidden reviewer autofix:

```text
- unrelated baseline failures
- broad dependency changes
- workflow/prompt/template edits inside feature PRs
- weakening/removing tests just to pass
- production logic changes only to satisfy stale tests
```

---

## Worker Pack Policy

A worker may receive 2-5 related issues for context locality.

But:

```text
Worker pack = queue of separate PRs.
Worker pack != one large PR.
```

For each issue in a pack:

```text
1. Read issue body and linked audit docs.
2. Check issue is open.
3. Search for duplicate open PRs.
4. Create/update branch from current `dev`.
5. Implement only issue scope.
6. Run required validation.
7. Open or update one PR.
8. Stop and report PR URL, head SHA, tests, skipped checks, and blockers.
```

If an issue already has an open PR:

```text
Do not create a duplicate PR.
Switch to PR Coordinator mode for that issue.
Report the existing PR and overlap.
```

---

## PR Readiness Gate

A PR is not ready unless all are true:

```text
- base branch is dev
- PR is not accidentally targeting main
- PR body follows template
- changed files match issue scope
- no process/workflow/prompt/template contamination unless explicitly in scope
- duplicate PR preflight completed
- required local validation run or explicitly documented
- static CI-equivalent checks green locally
- GitHub required checks are visible and green
- statusCheckRollup is not empty
- mergeable is true or blocker is documented
- baseline/unrelated failures are documented with follow-up issues
```

If a PR head changes after validation:

```text
Validation is stale.
Rerun relevant validation.
```

---

## Required GitHub Checks

Required merge blockers:

```text
- Secret Scan
- Semgrep
- Lint
- Lockfile Check
- Compose Config
- CodeQL / Analyze (Python)
```

Manual-only / non-blocking unless explicitly requested:

```text
- core-tests.yml
- trusted-heavy.yml
- nightly-heavy.yml
- broad local unit suite
- full/heavy tests
```

Never report a PR as ready if GitHub required checks are red, missing, or not started.

If `statusCheckRollup` is empty:

```text
Blocker: CI did not start.
Do not mark ready.
Investigate branch/ref/workflow trigger.
```

---

## Exact CI Static Commands

For final ready validation, approximate per-file Ruff checks are not enough.

Use exact CI-equivalent commands when Python paths changed:

```bash
uvx ruff check src/ telegram_bot/ mini_app/ services/ scripts/ --output-format=github
uvx ruff format --target-version py312 --check src/ telegram_bot/ mini_app/ services/ scripts/
uv lock --locked
```

If Telegram lockfile changed:

```bash
uv --directory telegram_bot lock --check
```

If Compose changed and Docker is available:

```bash
docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml config --quiet
```

If Docker is unavailable locally, document it and rely on GitHub Compose Config.

---

## Test Failure Triage

When validation fails, classify before fixing.

```text
PR-caused failure:
  Fix in current PR.

Static CI-equivalent failure:
  Fix in current PR before ready.

Existing baseline failure outside scope:
  Do not fix in this PR.
  Document as baseline.
  Create/follow separate issue.

Missing optional dependency:
  Do not install blindly.
  Classify as optional lane / test infra.
  Create/follow TEST-INFRA issue.

Legacy typing failure outside touched files:
  Do not fix in this PR.
  Create/follow TYPE-BASELINE issue.

Focused validation failure related to changed architecture:
  Cannot be treated as unrelated baseline.
  Classify as stale_test or code_regression.
  PR stays draft/blocked until test is rewritten, archived with explicit issue reference, or user explicitly accepts a follow-up.
```

---

## Scope Contamination Guard

Feature/runtime PRs must not include process/control-plane files unless explicitly requested.

Control-plane files include:

```text
docs/engineering/codex-web-prompt.md
skills/gh-pr-review.md
.github/pull_request_template.md
.github/workflows/*
AGENTS.md
tests/unit/test_agents_contract.py
```

If they appear in a feature PR without explicit scope:

```text
Block PR.
Request cleanup/cherry-pick.
Suggest separate process PR.
```

---

## PR Body Requirements

Every implementation PR should include:

```text
Issue / Mode
Changed files / Scope
Duplicate PR preflight
Validation
Skipped checks + reason
Failed checks triage
Follow-up issues
Risk / rollback
```

Every reviewed PR should contain or receive an Agent Handoff:

```text
Status
Base
Head
Validated commit
Risk
Failure class
Validation checklist
Findings
Next action
```

---

## Merge Policy

Merge only when:

```text
- user requested/allowed merge or orchestrator decision says merge
- PR base is dev
- current PR head equals validated commit
- required GitHub checks are green
- focused validation passed or acceptable baseline is documented
- make test-core passed when required, or failure is accepted as known baseline with follow-up
- no unresolved scope contamination
- no security uncertainty
- no related env_failure remains
```

Use merge commit strategy.

Never merge into `main` unless explicitly instructed.

---

## How To Improve Prompts

After every worker or reviewer failure, produce a copyable block:

```text
Prompt improvement

Добавить в <path>:

<exact rule text>
```

Keep it one continuous block so it can be copied directly into a worker task.

Common target files:

```text
docs/engineering/codex-web-prompt.md
skills/gh-pr-review.md
.github/pull_request_template.md
tests/unit/test_agents_contract.py
```

If the mistake should never repeat, add or request a contract test.

---

## Orchestrator Checklist

Before assigning work:

```text
- read current open PRs
- identify duplicates
- group issues into worker packs as queues
- do not assign already-covered issues
- define exact issue order and dependencies
```

When worker reports a PR:

```text
- verify PR exists
- verify base/head
- verify draft state
- verify changed files
- verify CI started
- verify CI green before merge
- check PR body
- check tests/skipped/follow-ups
- classify any failures
- decide: merge, request changes, draft, close, or split
```

When a process mistake happens:

```text
- identify root cause
- choose the owning skill: orchestrator, worker, PR reviewer, PR template, or contract test
- create or request a separate process PR updating that skill
- keep runtime feature PRs free of unrelated process edits
```

---

## Current Known Baselines

Track baseline issues separately. Do not fix them inside unrelated PRs.

Examples:

```text
TYPE-BASELINE: existing Telegram MyPy failures
TEST-INFRA: broad unit suite missing optional deps / stubs
```

If a broad suite fails due known baseline:

```text
Document it.
Link follow-up issue.
Do not expand feature PR.
```

---

## Default Orchestrator Response Style

Keep responses short, direct, and operational.

Preferred format:

```text
Status
Blockers
Next action
Prompt improvement
```

Avoid long explanations unless asked.
