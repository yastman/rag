---
name: gh-pr-review
description: 'Use when reviewing PRs, processing the open PR queue, auto-fixing safe PR issues, running focused validation, or merging to dev. Solo-dev workflow: inspect diff → classify risk → run focused checks → auto-fix if safe → update handoff → merge/block. Triggers on "review PR", "process PRs", "merge PR", "fix PR", "open PRs".'
---

# gh-pr-review — Solo Dev PR Workflow

## Purpose

Review, safely auto-fix, validate, and optionally merge PRs into `dev` without mixing PR coordination with new issue execution.

This skill follows the current solo-dev policy:

```text
GitHub required CI = hygiene/static only
Python tests = local/manual or workflow_dispatch-only
The orchestrator validation = focused tests based on changed files
Heavy/full tests = explicit manual request only
```

## Quick Flow

```text
PR → fresh dev check → diff → risk → focused validation → safe auto-fix → update handoff → merge/block
```

## Repo Rules

- Base branch: `dev`.
- Merge strategy: merge commit.
- Never merge into `main` without explicit instruction.
- Never change branch protection.
- Never mark a check as passed unless it actually passed on the current PR head.
- If PR head changed after validation, validation is stale and must be rerun.
- Do not create new feature/refactor PRs while operating in PR Coordinator mode.

## Required GitHub Checks

Only these checks are required for PR merge decisions:

```text
Secret Scan
Semgrep
Lint
Lockfile Check
Compose Config
```

Fast/Heavy Python test workflows, local runners, self-hosted runners, and workflow_dispatch checks are useful diagnostics but are not required merge blockers unless the user explicitly says so.

## Autopilot Mode

When explicitly requested, the agent may review, safe-auto-fix, validate, and merge a PR into `dev`.

### Allowed for autopilot

- docs-only changes;
- style-only changes;
- tests-only changes where the behavior is clearly preserved;
- small local code fixes where focused tests cover the touched seam.

### Restricted

Fix and validate, but do not merge automatically if uncertain:

- runtime behavior changes;
- Docker / Compose / env changes;
- LiteLLM / Qdrant / LangChain / LangGraph integration changes;
- dependency or lockfile changes;
- security-sensitive changes;
- broad test-suite or CI policy changes.

Runtime/security/dependency PRs may be merged by autopilot only when:

- required GitHub checks are green;
- focused validation relevant to changed files passed;
- `make test-core` passed when core/runtime/contracts/test-gate files changed;
- no env_failure is related to the changed subsystem;
- no security uncertainty remains;
- findings explicitly say clean.

## PR Coordinator Flow

1. Read PR title, body, comments, labels, and changed files.
2. Verify base branch is `dev`.
3. Fetch latest `origin/dev`.
4. Compare current PR head with any `Validated commit` in the handoff.
5. Inspect diff and classify risk.
6. Select focused validation from the test policy below.
7. If checks fail, classify failure before fixing.
8. Auto-fix only if safe.
9. Commit fixes to the PR branch when needed.
10. Rerun only the checks made stale by the fix.
11. Update PR body Agent Handoff.
12. Add Agent Run comment.
13. Merge only if merge conditions are satisfied and autopilot merge was explicitly requested.

## Test Selection Policy

Do not run the full test suite by default.

Before validation:

1. Inspect changed files.
2. Pick focused tests for those files.
3. Run `make test-core` only when the PR touches:
   - `src/core/`;
   - `src/runtime/`;
   - `tests/contract/`;
   - `Makefile` test gates;
   - architecture/coupling contracts or docs that define test policy.
4. Run adapter/optional lanes only when that surface changed.
5. Run `make test`, `make test-contract`, `make test-full`, or heavy workflows only if explicitly requested or if a broad runtime/dependency PR really needs them.

### Validation by risk

| Risk | Examples | Validation |
|---|---|---|
| docs | README, docs, comments | `git diff --check`; markdown/link checks if available |
| style | formatting, imports, lint-only | `make format-check`; `make lint` or focused Ruff command |
| test | tests only | targeted pytest for changed tests; no full suite by default |
| core | `src/core`, `src/runtime`, contracts | focused pytest + `make test-core` |
| adapter | `telegram_bot`, `src/api`, voice, mini_app | focused adapter tests; `make test-core` only if core contract touched |
| dependency | `pyproject.toml`, `uv.lock`, extras | lock/import checks + focused contract tests; broad tests only if requested |
| runtime | Compose, Docker, LLM/Qdrant/Redis env | focused subsystem checks; no auto-merge if uncertain |
| security | auth, secrets, tokens, dependency CVEs | required CI + manual review; no auto-merge if uncertain |

## Verification Commands

Use the smallest command set that matches the PR.

```bash
# Docs-only
git diff --check

# Static / style
make format-check
make lint

# Core/runtime
uv run pytest tests/unit/runtime/<relevant_test>.py -q
make test-core

# Contracts only when touched or relevant
make test-contract

# Broad local tests only on explicit request
make test

# Heavy/manual only on explicit request
make test-full
```

Do not use `make ci-local`; it is not the current canonical target in this repo.

## Safe Auto-fix Rules

Allowed without asking:

- Ruff formatting;
- Ruff auto-fixable lint;
- import sorting;
- trailing whitespace;
- obvious docs link/path updates;
- obvious test path/name updates after confirmed file move.

Allowed only after failure classification:

- stale test updates;
- local code regression fixes;
- env/config contract updates.

Never do silently:

- delete tests;
- broad skip or xfail;
- weaken assertions;
- change production logic only to satisfy a bad test;
- change dependencies;
- change branch protection;
- hide env failures as passed.

## Test Failure Classification

When tests fail, classify before fixing:

| Class | Meaning | Action |
|---|---|---|
| code_regression | test is valid and changed code broke it | fix production code, keep/add regression coverage, rerun relevant checks |
| stale_test | test asserts removed old architecture | update assertions to current behavior while preserving coverage |
| env_failure | missing Docker/services/API keys/env | non-blocking if optional/unrelated; blocker if PR touches that subsystem |
| flaky_or_race | nondeterministic/shared state/timing | stabilize if related to changed code; otherwise report as known/unrelated |

### Stale Test Rule

`stale_test` does not mean delete the test.

Do not skip, xfail, or weaken. Rewrite it to cover the current architecture.

Example: old Docker LiteLLM proxy expectations should become in-process LiteLLM router expectations.

## Merge Conditions

The agent may merge into `dev` only when all are true:

- PR base is `dev`.
- Current PR head equals `Validated commit` in Agent Handoff.
- Working tree is clean.
- Required GitHub checks are green.
- Focused validation for the changed files passed.
- `make test-core` passed if core/runtime/contracts/test-gate files changed.
- Optional/self-hosted checks are ignored if not required.
- No unresolved findings.
- No security uncertainty.
- No related env_failure remains.
- No related flaky_or_race remains.

If a new commit is pushed after validation, validation is stale and must be rerun.

If required GitHub checks are red, do not merge.

If only optional/self-hosted checks are red, queued, skipped, or offline, do not block solo-dev merge unless the user explicitly made them required for the PR.

## Agent Handoff

Every PR processed by this skill should contain or receive this section:

```md
## Agent Handoff

Status: ready_for_review | fixing | blocked | clean | merged
Base: dev
Head: <branch>
Validated commit: <sha or none>
Risk: docs | style | test | core | adapter | dependency | runtime | security
Failure class: none | code_regression | stale_test | env_failure | flaky_or_race

## Validation

- [ ] Required GitHub checks: not checked
- [ ] Focused validation: not run
- [ ] make test-core: not required | passed | failed | not run
- [ ] Optional/heavy checks: not required | passed | failed | skipped

## Findings

- None

## Next action

<what the next worker should do>
```

## Agent Run Comment

After every meaningful worker run, add a PR comment:

```md
## Agent Run

Worker: kiro-worker
Commit: <sha>
Action: <review | auto-fix | validation | merge>
Result: <clean | fixing | blocked | merged>

Validation:
- Required GitHub checks: <green | red | pending | not checked>
- Focused validation: <passed | failed | skipped>
- make test-core: <passed | failed | not required | skipped>
- Optional/heavy checks: <passed | failed | not required | skipped>

Next worker:
- Re-check that PR head is still <sha>.
- If head changed, rerun relevant validation.
- If unchanged and required GitHub checks are green, continue with decision.
```

## Labels

Queue:

- `agent:ready-review`
- `agent:fixing`
- `agent:blocked`
- `agent:clean`

Risk:

- `risk:docs`
- `risk:style`
- `risk:test`
- `risk:core`
- `risk:adapter`
- `risk:dependency`
- `risk:runtime`
- `risk:security`

Failure:

- `failure:stale-test`
- `failure:code-regression`
- `failure:env`
- `failure:flaky`

## Freshness Check

Before trusting validation, compare PR body `Validated commit` with current PR head:

```bash
VALIDATED=$(gh pr view <PR> --json body --jq '.body' | grep "Validated commit" | awk '{print $NF}')
HEAD=$(gh pr view <PR> --json headRefOid --jq '.headRefOid')

if [ "$VALIDATED" != "$HEAD" ]; then
  echo "STALE: rerun focused validation"
fi
```

## Merge Decision Tree

```text
if current head != Validated commit:
    rerun relevant validation

if required GitHub checks green
and focused validation green
and make test-core green when required
and no unresolved findings:
    update PR body Status: clean
    merge into dev using merge commit if autopilot merge was explicitly requested

if stale_test:
    update tests while preserving coverage
    rerun focused validation

if code_regression:
    fix production code
    keep/add regression coverage
    rerun focused validation

if env_failure:
    if optional or unrelated to changed subsystem:
        report clearly and allow solo-dev merge
    else:
        block until environment or test tier is fixed

if flaky_or_race:
    if related to changed code:
        stabilize before merge
    else:
        report as known/unrelated and allow solo-dev merge

if required GitHub checks are red:
    wait or fix required CI

if security uncertainty:
    block and do not auto-merge
```

## Quick Commands

```bash
# Get PR context
gh pr view <PR> --json number,title,body,headRefName,headRefOid,baseRefName,mergeStateStatus,statusCheckRollup,labels

# See diff
gh pr diff <PR>

# Check required status checks
gh pr checks <PR> --required

# Update PR body
gh pr edit <PR> --body-file /tmp/pr-body.md

# Add comment
gh pr comment <PR> --body-file /tmp/pr-comment.md

# Merge only when allowed
gh pr merge <PR> --merge
```

## Open PR Queue Processing

When asked to process open PRs:

1. List all open PRs targeting `dev`.
2. Classify each PR by risk and changed files.
3. Check Agent Handoff freshness.
4. Run only relevant validation if stale/missing.
5. Auto-fix only safe issues.
6. Update PR body and add Agent Run comment.
7. Merge only if user explicitly requested autopilot merge and merge conditions are met.

Priority order:

1. `agent:clean` — clean, just needs freshness + required checks.
2. `agent:ready-review` — already validated, needs review/freshness.
3. No labels — needs full PR Coordinator review.
4. `agent:fixing` — in progress, check status.
5. `agent:blocked` — report blocker.

Queue mode reviews and updates handoff by default. It may merge only if the user explicitly requested autopilot merge.
