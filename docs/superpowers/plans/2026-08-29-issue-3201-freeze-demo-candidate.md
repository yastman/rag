# Issue #3201 Freeze Demo Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze one clean, recoverable `origin/dev` candidate for the presentation and publish the atomic issue/worktree/PR execution contract without changing product behavior.

**Architecture:** This is an operational and documentation-only issue. Git provides the immutable candidate/rollback identity, an ignored in-repository worktree isolates delivery from the user's primary checkout, the Windows static preflight records missing prerequisites without mutating services, and GitHub issue/PR evidence closes the loop.

**Tech Stack:** Git worktrees, GitHub CLI, PowerShell, repository Windows preflight, Markdown.

**Spec:** `docs/specs/2026-08-29-atomic-audit-delivery.md`

## Global Constraints

- One executable GitHub issue maps to one branch, one `.worktrees/issue-<number>` worktree, one PR, and one merge to `dev`.
- Preserve the primary checkout and its user-owned `.gitignore` modification.
- Do not print environment-file contents or start/mutate shared Redis, Qdrant, BGE, Telegram, or database services.
- Treat the non-zero static preflight as evidence of missing operator paths, not as authorization to repair them in this issue.
- Use `72bf7da1838ccee6496febf37e3976572273013d` as the recorded rollback point for this frozen candidate.

---

## Task 1: Prove the Candidate Identity and Isolation

**Files:**

- Create: `docs/specs/2026-08-29-atomic-audit-delivery.md`
- Create: `docs/superpowers/plans/2026-08-29-issue-3201-freeze-demo-candidate.md`

- [x] Fetch `origin` and record the exact `origin/dev` SHA.
- [x] Prove branch `codex/issue-3201-freeze-demo-candidate` was created from that SHA.
- [x] Prove the worktree resides at `.worktrees/issue-3201` and `.worktrees/` is ignored.
- [x] Record the primary checkout HEAD and only the path/status of user WIP, never its contents.
- [x] Confirm no tracked product file changed.

Verification:

```powershell
git fetch origin --prune
git rev-parse HEAD
git rev-parse origin/dev
git merge-base --is-ancestor 72bf7da1838ccee6496febf37e3976572273013d HEAD
git worktree list --porcelain
git check-ignore -v .worktrees/issue-3201
git status --short
```

## Task 2: Capture the Read-Only Windows Preflight

- [x] Run static preflight with the existing operator environment file as input.
- [x] Record only tool/lock/Compose pass/fail results and missing host paths.
- [x] Confirm no secret value or production record was copied into tracked documentation.
- [x] Leave shared services stopped and their data unchanged.

Verification:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/windows_preflight.ps1 -Mode Static -OperatorEnvFile 'C:\Dev\projects-wsl-migrated-2026-07-13\rag-fresh\.env'
```

Expected issue-local result: non-zero until the operator replaces the stale Linux BGE model and Drive sync host paths.

## Task 3: Publish the Atomic Delivery DAG

- [x] Record the presentation/runtime/dependency/product-honesty/tooling predecessor graph for `#3199`–`#3245`.
- [x] Record lock/Compose collision serialization rules in addition to hard GitHub predecessors.
- [x] Record the per-issue branch/worktree/spec/plan/test/review/PR/merge protocol.
- [x] Record SDK and data-ownership decisions from the completed audits.
- [x] Explicitly forbid bundled executable issues and premature parent-epic closure.

Verification:

```powershell
git diff --check
git diff -- docs/specs/2026-08-29-atomic-audit-delivery.md docs/superpowers/plans/2026-08-29-issue-3201-freeze-demo-candidate.md
```

## Task 4: Deliver #3201 Independently

- [ ] Review the full two-file diff for correctness, secret leakage, and accidental scope expansion.
- [ ] Commit on the issue branch only.
- [ ] Push the issue branch and open one PR targeting `dev` with `Closes #3201`.
- [ ] Attach candidate SHA, branch, worktree, clean-state, rollback, and static-preflight evidence to `#3197` without secrets.
- [ ] Run `make candidate-check` successfully on the exact candidate before merge. A failure blocks merge and preserves the issue branch/worktree for diagnosis and retry.
- [ ] Merge after checks, fetch `origin`, and prove the accepted commit is an ancestor of `origin/dev`.
- [ ] Close `#3201` if necessary and safely remove only `.worktrees/issue-3201` after merge proof.

Verification:

```powershell
git status --short
git log -1 --oneline
make candidate-check
gh pr checks <pr-number>
git fetch origin --prune
git merge-base --is-ancestor <accepted-commit> origin/dev
gh issue view 3201 --json state,url
```
