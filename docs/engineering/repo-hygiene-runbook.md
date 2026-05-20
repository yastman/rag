# Weekly Repo Hygiene Runbook

> Operator playbook for keeping local git state, the open PR queue, and the
> issue backlog manageable. Spec: [#1717](https://github.com/yastman/rag/issues/1717).

## TL;DR (5-minute Monday check)

```bash
make git-hygiene          # local branches + worktrees + transient files
make pr-hygiene           # open PR queue triage
make issue-hygiene        # open issue queue hygiene
```

Each command exits non-zero whenever something is actionable, so they're CI-
friendly and can be wired into a weekly Slack/email digest.

## What each tool covers

| Tool                              | Covers                                | Issue   |
| --------------------------------- | ------------------------------------- | ------- |
| `scripts/git_hygiene.py`          | branches, worktrees, transient files  | #1718   |
| `scripts/pr_queue_audit.py`       | open PR queue, blocked reasons, SLA   | #1719   |
| `scripts/issue_queue_audit.py`    | open issue labels, lanes, assignees   | #1720   |

All three accept `--json` for programmatic consumption and human-readable
output by default.

## Safety guarantees

The cleanup tooling is designed so a tired operator running `make ... -fix`
on Monday morning cannot lose work:

- **Never deletes the current branch.** Classified as `protected`.
- **Never deletes long-lived branches** (`dev`, `main`, `master`, `develop`).
- **Never deletes a branch checked out in a worktree** (would fail anyway,
  but we block it explicitly with a clear reason).
- **Never deletes a branch with uncommitted changes in its worktree.**
- **Never deletes a branch ahead of upstream or with upstream `[gone]`** in
  the default `--fix` mode. Those are surfaced under `requires-human` so the
  operator can decide.
- **Default to non-destructive checks.** `--fix` requires an explicit flag;
  `--dry-run` previews any deletion.

The `--include-requires-human` opt-in flag will additionally delete branches
in the requires-human lane, but still refuses dirty worktrees.

## 1. Git hygiene

```bash
make git-hygiene                              # report
make git-hygiene-fix                          # dry-run cleanup of safe lane
uv run python scripts/git_hygiene.py --fix    # apply cleanup
uv run python scripts/git_hygiene.py --json   # machine-readable
```

Lanes you'll see in the output:

| Lane               | Action                                                |
| ------------------ | ----------------------------------------------------- |
| `safe-to-delete`   | `--fix` removes them. Safe by construction.           |
| `protected`        | Informational; never touched.                         |
| `requires-human`   | Decide per branch. Common reasons:                    |
|                    | • upstream gone (remote branch was deleted)           |
|                    | • ahead of upstream (un-pushed commits)               |
|                    | • not merged into base                                |
|                    | • checked out at a worktree                           |
|                    | • uncommitted changes in worktree                     |

Worktrees show up under `requires-human` whenever they are detached, in
`/tmp`, or dirty. None of those are auto-removed; the operator decides
whether to commit, stash, or `git worktree remove --force` after backup.

## 2. PR queue triage

```bash
make pr-hygiene                                       # report
uv run python scripts/pr_queue_audit.py --json
uv run python scripts/pr_queue_audit.py --bucket conflicts
uv run python scripts/pr_queue_audit.py --base dev
```

Buckets in priority order:

1. **conflicts**          — needs rebase / merge resolution.
2. **ci-failing**         — author must fix.
3. **ci-pending**         — wait or re-run.
4. **changes-requested**  — reviewer asked for changes; ping author.
5. **review-needed**      — CI green, no approval; assign reviewer.
6. **ready**              — green and approved; merge it.
7. **draft**              — author still working.
8. **stale**              — flag is independent; surfaced for any PR older
                            than `--stale-days` (default 14).
9. **unknown**            — gh fields missing; investigate.

### Triage SLA

The runbook recommends:

- **conflicts / ci-failing / changes-requested**: ping author within 2
  business days.
- **review-needed > 3 days**: assign a reviewer.
- **ready**: merge same-day if author confirms.
- **stale > 30 days**: close with a note, asking author to reopen with
  rebase if still relevant.

### Ownership rule

Pick the smallest unit:

- The author owns `conflicts`, `ci-failing`, `changes-requested`.
- The reviewer pool owns `review-needed`.
- The merger (CODEOWNER or release manager) owns `ready`.

## 3. Issue queue hygiene

```bash
make issue-hygiene
uv run python scripts/issue_queue_audit.py --json
uv run python scripts/issue_queue_audit.py --bucket no-lane
uv run python scripts/issue_queue_audit.py --bucket no-assignee
```

Buckets:

| Bucket         | Action                                                         |
| -------------- | -------------------------------------------------------------- |
| `no-labels`    | Add at least one functional label (bug/refactor/docs/...).     |
| `no-assignee`  | Pick an owner or surface in standup.                           |
| `no-lane`      | Add `lane:quick-win` / `lane:plan-needed` / `lane:architecture-heavy`. |
| `stale`        | Older than `--stale-days` (default 60). Confirm or close.     |
| `triaged`      | Already has labels + assignee + lane. No action.              |

### Splitting issues

A single issue should:

1. Belong to **one** lane label.
2. Be small enough that a single PR can close it.

If the body needs a checklist longer than 5 items, **split** it into a parent
issue + 1 child issue per lane (the pattern used for #1717 → #1718 / #1719 /
#1720).

### Lane labels

| Lane                        | When to pick                                              |
| --------------------------- | --------------------------------------------------------- |
| `lane:quick-win`            | Narrow, established change. One PR. Concrete verification. |
| `lane:plan-needed`          | Multi-file or runtime-impacting. Route via `@writing-plans`. |
| `lane:architecture-heavy`   | Structurally ambiguous. Spec → review → plan → execute.   |

These match the existing decision model in
`docs/engineering/issue-triage.md`.

## Weekly schedule (suggested)

| Day        | Action                                       |
| ---------- | -------------------------------------------- |
| Mon AM     | Run all three reports; post a short summary. |
| Mon-Wed    | Address `conflicts` / `ci-failing` PRs.      |
| Tue        | Add labels/lanes to fresh issues.            |
| Thu        | Triage `review-needed` PRs.                  |
| Fri        | Run `git-hygiene-fix --dry-run`, then apply. |

## Non-goals

- The runbook does not auto-close stale items; closure is a human decision.
- It does not change branch protection rules.
- It does not enforce a merge order; it surfaces signals.

## Related

- [#1717](https://github.com/yastman/rag/issues/1717) — parent spec
- [#1718](https://github.com/yastman/rag/issues/1718) — git/worktree safety (this runbook §1)
- [#1719](https://github.com/yastman/rag/issues/1719) — PR queue triage (this runbook §2)
- [#1720](https://github.com/yastman/rag/issues/1720) — issue queue hygiene (this runbook §3)
- [`docs/engineering/issue-triage.md`](issue-triage.md) — decision model & lanes
