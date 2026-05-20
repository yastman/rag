***REMOVED*** Weekly Repo Hygiene Runbook

> Operator playbook for keeping local git state, the open PR queue, and the
> issue backlog manageable. Spec: [***REMOVED***1717](https://github.com/yastman/rag/issues/1717).

***REMOVED******REMOVED*** TL;DR (5-minute Monday check)

```bash
make git-hygiene          ***REMOVED*** local branches + worktrees + transient files
make pr-hygiene           ***REMOVED*** open PR queue triage
make issue-hygiene        ***REMOVED*** open issue queue hygiene
```

Each command exits non-zero whenever something is actionable, so they're CI-
friendly and can be wired into a weekly Slack/email digest.

***REMOVED******REMOVED*** What each tool covers

| Tool                              | Covers                                | Issue   |
| --------------------------------- | ------------------------------------- | ------- |
| `make git-hygiene` (native git)   | branches, worktrees, transient files  | ***REMOVED***1718   |
| `scripts/pr_queue_audit.py`       | open PR queue, blocked reasons, SLA   | ***REMOVED***1719   |
| `scripts/issue_queue_audit.py`    | open issue labels, lanes, assignees   | ***REMOVED***1720   |

The PR and issue audits accept `--json` for programmatic consumption and
human-readable output by default. The git hygiene path is now native git
(`git fetch --prune`, `git branch --merged`, `git for-each-ref`,
`git worktree list --porcelain`, `git ls-files --others`) — there is no
Python helper to call directly. See
[`docs/engineering/script-native-migration-matrix.md`](script-native-migration-matrix.md)
for the audit decisions behind this split.

***REMOVED******REMOVED*** Safety guarantees

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

The `--include-requires-human` opt-in flag (in the audit scripts for PR
and issue lanes) will additionally surface borderline items, but git
cleanup itself stays native and conservative — it never force-removes
dirty worktrees.

***REMOVED******REMOVED*** 1. Git hygiene

```bash
make git-hygiene                              ***REMOVED*** report
make git-hygiene-fix                          ***REMOVED*** dry-run cleanup of safe lane
make git-hygiene-fix | sh                     ***REMOVED*** apply cleanup (review first!)
```

`make git-hygiene-fix` prints the exact `git merge-base --is-ancestor … &&
git branch -D <branch>` commands it would run, but does not execute them.
Pipe to `sh` only after reviewing the list. There is no `--json` flag in
this lane; consume the output via standard text tooling (`grep`, `awk`)
or extend the Makefile target.

Lanes you'll see in the output (driven by `git branch --merged` /
`git for-each-ref` / `git worktree list`):

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

***REMOVED******REMOVED*** 2. PR queue triage

```bash
make pr-hygiene                                       ***REMOVED*** report
uv run python scripts/pr_queue_audit.py --json
uv run python scripts/pr_queue_audit.py --bucket conflicts
uv run python scripts/pr_queue_audit.py --base dev
```

Buckets in priority order:

1. **conflicts**          — needs rebase / merge resolution.
2. **ci-failing**         — static CI guardrail failed; author must fix.
3. **ci-pending**         — static CI guardrail is still running; wait or re-run.
4. **changes-requested**  — reviewer asked for changes; ping author.
5. **review-needed**      — static CI green, no approval; assign reviewer.
6. **ready**              — static CI green and approved; confirm local test
                            evidence before merge.
7. **draft**              — author still working.
8. **stale**              — flag is independent; surfaced for any PR older
                            than `--stale-days` (default 14).
9. **unknown**            — gh fields missing; investigate.

***REMOVED******REMOVED******REMOVED*** Triage SLA

The runbook recommends:

- **conflicts / ci-failing / changes-requested**: ping author within 2
  business days.
- **review-needed > 3 days**: assign a reviewer.
- **ready**: merge same-day if author confirms.
- **stale > 30 days**: close with a note, asking author to reopen with
  rebase if still relevant.

***REMOVED******REMOVED******REMOVED*** Ownership rule

Pick the smallest unit:

- The author owns `conflicts`, `ci-failing`, `changes-requested`.
- The reviewer pool owns `review-needed`.
- The merger (CODEOWNER or release manager) owns `ready`.

***REMOVED******REMOVED*** 3. Issue queue hygiene

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

***REMOVED******REMOVED******REMOVED*** Splitting issues

A single issue should:

1. Belong to **one** lane label.
2. Be small enough that a single PR can close it.

If the body needs a checklist longer than 5 items, **split** it into a parent
issue + 1 child issue per lane (the pattern used for ***REMOVED***1717 → ***REMOVED***1718 / ***REMOVED***1719 /
***REMOVED***1720).

***REMOVED******REMOVED******REMOVED*** Lane labels

| Lane                        | When to pick                                              |
| --------------------------- | --------------------------------------------------------- |
| `lane:quick-win`            | Narrow, established change. One PR. Concrete verification. |
| `lane:plan-needed`          | Multi-file or runtime-impacting. Route via `@writing-plans`. |
| `lane:architecture-heavy`   | Structurally ambiguous. Spec → review → plan → execute.   |

These match the existing decision model in
`docs/engineering/issue-triage.md`.

***REMOVED******REMOVED*** Weekly schedule (suggested)

| Day        | Action                                       |
| ---------- | -------------------------------------------- |
| Mon AM     | Run all three reports; post a short summary. |
| Mon-Wed    | Address `conflicts` / `ci-failing` PRs.      |
| Tue        | Add labels/lanes to fresh issues.            |
| Thu        | Triage `review-needed` PRs.                  |
| Fri        | Run `git-hygiene-fix --dry-run`, then apply. |

***REMOVED******REMOVED*** Non-goals

- The runbook does not auto-close stale items; closure is a human decision.
- It does not change branch protection rules.
- It does not enforce a merge order; it surfaces signals.

***REMOVED******REMOVED*** Related

- [***REMOVED***1717](https://github.com/yastman/rag/issues/1717) — parent spec
- [***REMOVED***1718](https://github.com/yastman/rag/issues/1718) — git/worktree safety (this runbook §1)
- [***REMOVED***1719](https://github.com/yastman/rag/issues/1719) — PR queue triage (this runbook §2)
- [***REMOVED***1720](https://github.com/yastman/rag/issues/1720) — issue queue hygiene (this runbook §3)
- [`docs/engineering/issue-triage.md`](issue-triage.md) — decision model & lanes
