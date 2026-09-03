# Candidate freeze record — 2026-09-03

Scope: presentation-candidate freeze for the demo (#3201, parent #3197). Evidence comes from
read-only Git inspection plus the local `test-core` and docs-link gates on a clean, isolated
worktree. No stateful service or production data was touched. Following the precedent of
[`worktree-recovery-2026-07-23.md`](worktree-recovery-2026-07-23.md), this record intentionally
does not self-reference its own commit SHA; the presentation SHA is the HEAD of the branch below
and is recorded in #3197.

## Frozen candidate

| Item | Value |
| --- | --- |
| Presentation base (`origin/dev`, fetched 2026-09-03) | `cd70fb98f59542e0a005af78998567293c261702` |
| Rollback point | the same `cd70fb98f…` (pre-candidate `origin/dev`, per the #3201 rollback section) |
| Candidate branch | `codex/issue-3201-freeze-candidate-sha` |
| Candidate worktree | `/Users/aroslav/Documents/rag-fresh-wt/issue-3201` (isolated, created fresh from the exact `origin/dev`; the stale candidate tree was not reused) |
| Presentation SHA | HEAD of the candidate branch — the commit carrying this record; resolvable with `git rev-parse codex/issue-3201-freeze-candidate-sha`, recorded in #3197 |

The candidate content is exactly `origin/dev` at freeze time: tracked status clean and
`git diff origin/dev..HEAD` empty before this record was added. The record commit adds
documentation only (`docs/audits/candidate-freeze-2026-09-03.md` plus its hub link in
`docs/README.md`), so the presentation delta versus the base is this record alone.

## Superseded prior candidate

`44ccb9ee40b333d875759aea38bce42e53cee638` (branch `codex/issue-3201-freeze-demo-candidate`,
2 commits ahead / 25 behind `origin/dev`, internal worktree removed during cleanup) is stale
evidence only. It must not be pushed or merged as the presentation SHA; the candidate branch
above supersedes it.

## Gate evidence (run on the exact candidate tree)

| Check | Result |
| --- | --- |
| `make test-core` | 235 passed (matches the 235-passed baseline) |
| `make docs-check` | All relative Markdown links OK |
| Tracked status | `git status --porcelain` clean |
| Ancestry | `git merge-base --is-ancestor origin/dev HEAD` passes |
| Diff vs base | empty before the record commit; the two documentation files only after |

## Remaining operational prerequisites (owned by the presentation runbook / #3197)

1. `make candidate-check` (`check-frozen` + `test` + `test-contract`) from the supported POSIX
   shell with an isolated frozen `.venv`.
2. `scripts/windows_preflight.ps1 -Mode Full` on native Windows. Not run for this record (the
   freeze host is macOS); clearly external prerequisites remain owned by the documented
   presentation runbook, which verifies them without hiding a repository defect.
3. Record the resolved presentation SHA and this gate evidence in #3197.

## Recovery instructions

```bash
# Resolve the presentation SHA (or use the SHA recorded in #3197).
git rev-parse codex/issue-3201-freeze-candidate-sha

# Recreate a clean worktree at the candidate.
git worktree add /Users/aroslav/Documents/rag-fresh-wt/issue-3201-recovered <SHA>

# Verify recovery: ancestry, clean status, record-only delta.
git merge-base --is-ancestor cd70fb98f59542e0a005af78998567293c261702 <SHA>
git -C /Users/aroslav/Documents/rag-fresh-wt/issue-3201-recovered status --porcelain
git diff --stat cd70fb98f59542e0a005af78998567293c261702..<SHA>
```

The code rollback point is `git checkout cd70fb98f59542e0a005af78998567293c261702` (the exact
pre-candidate `origin/dev`). #3201 authorizes no stateful service or production data mutation,
so no data rollback applies.
