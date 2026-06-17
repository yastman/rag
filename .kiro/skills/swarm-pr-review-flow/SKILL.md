---
name: swarm-pr-review-flow
description: Coordinate tmux/Kiro swarm PR review cycles. Use when swarm review waves are requested, when accepted artifacts route to next_skill:"swarm-pr-review-flow", or when review-fix and re-review routing is required before merge readiness. Keep merge judgment in the orchestrator and use Markdown-first review evidence.
---

# Swarm PR Review Flow

Coordinate PR review and review-fix waves while keeping merge judgment in the orchestrator.

## Workflow

1. For runtime/code PRs, prefer a read-only `pr-review` worker on the current
   head SHA before merge readiness.
2. Review workers are read-only. They write `logs/PR_REVIEW.<worker>.md` and
   finish with `[DONE] worker logs/PR_REVIEW.<worker>.md`.
3. If blockers are found, launch `pr-review-fix` only for named blockers, on
   the same PR branch, with explicit reserved files and focused checks.
4. After a review-fix wave, use the orchestrator bounded checks only for tiny docs/test
   metadata fixes. Launch a fresh read-only re-review for behavior/runtime/
   security changes or semantic blockers.
5. Disposition new bugs: fix only if they block the current PR and fit reserved
   scope; otherwise record follow-up disposition.
6. Merge readiness requires current-head evidence, required checks, no
   in-scope blockers, and resolved safety/product/access questions.
7. For PRs linked to issue, bugfix, duplicate, recurrence, or umbrella work,
   `merge_ready` must be false when the chain
   `duplicate_scan -> anti_regression_contract -> anti_regression_evidence` is
   missing or contradictory. File a PR review blocker instead of treating this
   as a documentation gap.

## Agent Selection

Always use `kiro-worker-opus` (claude-opus-4.8) for review and re-review workers.
Use `kiro-worker` (claude-sonnet-4.6) only for review-fix workers (implementation).

Launch pattern for review workers:
```bash
WORKER_AGENT=kiro-worker-opus \
WORKER_MODEL=claude-opus-4.8 \
WORKER_ROLE=review \
KIRO_REQUIRED_SKILLS=swarm-pr-review-flow,verification-before-completion \
./scripts/launch_kiro_worker.sh <worker-name> <prompt-file>
```

Launch pattern for review-fix workers:
```bash
WORKER_AGENT=kiro-worker \
WORKER_MODEL=claude-sonnet-4.6 \
WORKER_ROLE=implementation \
KIRO_REQUIRED_SKILLS=swarm-pr-review-flow,receiving-code-review,executing-plans,test-driven-development,verification-before-completion \
./scripts/launch_kiro_worker.sh <worker-name> <prompt-file>
```

## Review-Fix Prompt Contract

Bound every `pr-review-fix` prompt to named findings and include:

- `pr`, `base`, `head_sha`, and current branch/worktree.
- `exact blocker IDs` copied from the accepted review or acceptance evidence.
- `allowed_files` and reserved files; these must match the launch plan.
- `forbidden_changes`, including unrelated refactors, broad rewrites, merge,
  branch deletion, cleanup, and unassigned PR disposition.
- `validation_commands` that reproduce or verify the named blockers.
- For `rag-fresh` Python checks, require the reusable root environment command
  form `UV_PROJECT_ENVIRONMENT=/home/user/projects/rag-fresh/.venv uv run
  --no-sync ...` when that `.venv` exists. Do not ask review-fix workers to run
  `uv sync`, create a new Python 3.14 environment, upgrade dependency groups, or
  build heavy packages such as `grpcio` unless dependency installation is the
  named blocker.
- Required skills and Required Superpowers, including
  `superpowers:receiving-code-review` and, for code edits,
  `superpowers:executing-plans`, `superpowers:test-driven-development`, and
  `superpowers:verification-before-completion`.
- `retry_count` and `max_attempts` from acceptance repair loop.
- fresh report path, wake-up command using `ORCH_TARGET`, and
  `re_review_trigger` describing when a fresh read-only review is required.

Require review-fix workers to fix only named blockers. If blocker resolution
needs out-of-scope files, report `BLOCKED` instead of broadening scope.

## Ownership

- Allow workers to edit, commit, push, or create/update PR only when prompt
  explicitly assigns that operation.
- the orchestrator owns merge readiness and merge decisions, using current-head review and
  required-check evidence. In autonomous mode, when `merge_ready: true` and no blockers exist,
  the orchestrator merges into `dev` automatically. Manual confirmation is required only for
  merges to `main`/`master`, PRs with blockers, or PRs touching secrets/auth/destructive ops.
- Acceptance owns verified post-merge worktree/branch cleanup through explicit
  disposition; workers do not delete worktrees or branches by default.

## Output

Produce Markdown `MERGE_READINESS` with:

- `pr`
- `head_sha`
- `review_reports`
- `review_decision`
- `blockers`
- `fix_waves`
- `required_checks`
- `new_bugs_disposition`
- `merge_ready`
- `next_action`
- `next_skill`

When `merge_ready: true`, set `next_skill: swarm-acceptance` and
`next_action: disposition=merge_done` so the orchestrator routes directly
to acceptance for merge execution. Do not merge from within this skill —
merge ownership stays with `swarm-acceptance`.

Use strict JSON only for explicit legacy machine orchestration.
