# Script Native Migration Matrix

Audit snapshot for issue [#1726](https://github.com/yastman/rag/issues/1726)
and child issue [#1728](https://github.com/yastman/rag/issues/1728).

## Migration Targets

| Script | Current Callsites | Native Replacement | Decision | Owner | Verification |
|---|---|---|---|---|---|
| `scripts/git_hygiene.py` | Former `Makefile` hygiene targets, tests, docs | `git fetch --prune origin`; `git branch --merged origin/$REPO_BASE_BRANCH`; `git for-each-ref`; `git worktree list --porcelain`; `git ls-files --others --exclude-standard` | archived as `scripts/archive/git_hygiene.py`; no active callsites | DevEx | `make -n git-hygiene git-hygiene-fix`; focused unit test |
| `scripts/repo_cleanup.sh` | Former `Makefile` cleanup targets, tests, docs | `git fetch --prune origin`; `git branch --merged`; `git branch -r --merged`; `gh pr list --head`; `git worktree prune`; `git stash list` | archived as `scripts/archive/repo_cleanup.sh`; no active callsites | DevEx | `make -n repo-cleanup repo-cleanup-force`; focused unit test |
| `scripts/pr_queue_audit.py` | `make pr-hygiene` | `gh pr list --json ...` plus project triage policy | keep custom audit wrapper | DevEx | existing target smoke/focused tests |
| `scripts/issue_queue_audit.py` | `make issue-hygiene` | `gh issue list --json ...` plus project triage policy | keep custom audit wrapper | DevEx | existing target smoke/focused tests |

## Required Safety Checks

- Native cleanup excludes `dev`, `main`, `master`, `develop`, the current branch,
  and branches checked out in any worktree.
- Dirty or active worktrees are not force-removed by `make repo-cleanup-force`.
- Remote branch cleanup remains report-only and includes open-PR status.
- Destructive local branch deletion remains interactive.
