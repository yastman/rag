# Git Hygiene Runbook

Weekly maintenance procedures for keeping the repository clean.

## Quick Start

```bash
make git-hygiene           # Report only
make git-hygiene-fix       # Preview cleanup (dry-run)
```

## Weekly Cleanup Checklist

### 1. Prune Remote References

```bash
git fetch --prune
```

Removes local refs to branches deleted on the remote.

### 2. Merged Branch Detection

```bash
# List branches merged to origin/main
git branch --merged origin/main | grep -vE '^\*|main|master|develop'

# Delete merged branches (safe — only fully merged)
git branch --merged origin/main | grep -vE '^\*|main|master|develop' | xargs -r git branch -d
```

Or use the automated script:

```bash
uv run python scripts/git_hygiene.py --fix --dry-run   # Preview
uv run python scripts/git_hygiene.py --fix              # Execute
```

### 3. Stale Worktree Detection

```bash
git worktree list
git worktree prune    # Remove entries for deleted directories
```

The hygiene script also reports worktrees that are detached or in `/tmp`.

### 4. Stash Review

```bash
git stash list
```

Review stashes older than 2 weeks. Map each to a branch:

```bash
# Show stash details
git stash show -p stash@{0}

# Drop stale stashes (oldest first)
git stash drop stash@{N}
```

**Rule:** Keep at most 5 stashes. Drop anything older than 30 days.

### 5. Transient File Cleanup

The hygiene script checks for: `coverage.json`, `test_output*`, `*.log` in the repo root.

```bash
# Manual cleanup
rm -f coverage.json test_output* *.log
```

## Safe Deletion Rules

| What | Safe to delete? | Condition |
|------|----------------|-----------|
| Branch merged to `origin/main` | Yes | Always safe (`git branch -d`) |
| Branch **not** merged | No | Use `git branch -D` only after manual review |
| Worktree in `/tmp` | Yes | After confirming no active work |
| Detached worktree | Maybe | Investigate first — may have uncommitted work |
| Stash > 30 days | Yes | After reviewing contents |

## One-Command Cleanup

```bash
make git-hygiene       # Full report
make git-hygiene-fix   # Safe cleanup preview (dry-run)
```

## JSON Output

For CI/automation:

```bash
uv run python scripts/git_hygiene.py --json
```

Returns structured JSON with `merged_branches`, `no_upstream_branches`, `stale_worktrees`, `transient_files`, and `total_issues`.
