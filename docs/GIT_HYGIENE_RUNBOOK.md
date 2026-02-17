***REMOVED*** Git Hygiene Runbook

Weekly maintenance procedures for keeping the repository clean.

***REMOVED******REMOVED*** Quick Start

```bash
make git-hygiene           ***REMOVED*** Report only
make git-hygiene-fix       ***REMOVED*** Preview cleanup (dry-run)
```

***REMOVED******REMOVED*** Weekly Cleanup Checklist

***REMOVED******REMOVED******REMOVED*** 1. Prune Remote References

```bash
git fetch --prune
```

Removes local refs to branches deleted on the remote.

***REMOVED******REMOVED******REMOVED*** 2. Merged Branch Detection

```bash
***REMOVED*** List branches merged to origin/main
git branch --merged origin/main | grep -vE '^\*|main|master|develop'

***REMOVED*** Delete merged branches (safe — only fully merged)
git branch --merged origin/main | grep -vE '^\*|main|master|develop' | xargs -r git branch -d
```

Or use the automated script:

```bash
uv run python scripts/git_hygiene.py --fix --dry-run   ***REMOVED*** Preview
uv run python scripts/git_hygiene.py --fix              ***REMOVED*** Execute
```

***REMOVED******REMOVED******REMOVED*** 3. Stale Worktree Detection

```bash
git worktree list
git worktree prune    ***REMOVED*** Remove entries for deleted directories
```

The hygiene script also reports worktrees that are detached or in `/tmp`.

***REMOVED******REMOVED******REMOVED*** 4. Stash Review

```bash
git stash list
```

Review stashes older than 2 weeks. Map each to a branch:

```bash
***REMOVED*** Show stash details
git stash show -p stash@{0}

***REMOVED*** Drop stale stashes (oldest first)
git stash drop stash@{N}
```

**Rule:** Keep at most 5 stashes. Drop anything older than 30 days.

***REMOVED******REMOVED******REMOVED*** 5. Transient File Cleanup

The hygiene script checks for: `coverage.json`, `test_output*`, `*.log` in the repo root.

```bash
***REMOVED*** Manual cleanup
rm -f coverage.json test_output* *.log
```

***REMOVED******REMOVED*** Safe Deletion Rules

| What | Safe to delete? | Condition |
|------|----------------|-----------|
| Branch merged to `origin/main` | Yes | Always safe (`git branch -d`) |
| Branch **not** merged | No | Use `git branch -D` only after manual review |
| Worktree in `/tmp` | Yes | After confirming no active work |
| Detached worktree | Maybe | Investigate first — may have uncommitted work |
| Stash > 30 days | Yes | After reviewing contents |

***REMOVED******REMOVED*** One-Command Cleanup

```bash
make git-hygiene       ***REMOVED*** Full report
make git-hygiene-fix   ***REMOVED*** Safe cleanup preview (dry-run)
```

***REMOVED******REMOVED*** JSON Output

For CI/automation:

```bash
uv run python scripts/git_hygiene.py --json
```

Returns structured JSON with `merged_branches`, `no_upstream_branches`, `stale_worktrees`, `transient_files`, and `total_issues`.
