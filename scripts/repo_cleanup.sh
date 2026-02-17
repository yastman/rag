#!/usr/bin/env bash
# scripts/repo_cleanup.sh — Repository hygiene: branches, worktrees, stashes
# Usage: ./scripts/repo_cleanup.sh [--dry-run] [--force] [--help]
#
# Stages:
#   1. Prune stale remote tracking refs
#   2. List/delete remote branches merged into main
#   3. List/delete local branches merged into main
#   4. List/remove stale worktrees (merged/orphaned)
#   5. Show stash aging report
#
# With --force: actually deletes (requires confirmation per batch).
# Default: dry-run (report only).

set -euo pipefail

DRY_RUN=true
MAIN_BRANCH="main"

show_help() {
    sed -n '2,14p' "$0" | sed 's/^# \?//'
    exit 0
}

for arg in "$@"; do
    case "$arg" in
        --force) DRY_RUN=false ;;
        --dry-run) DRY_RUN=true ;;
        --help|-h) show_help ;;
        *) echo "Usage: $0 [--dry-run] [--force] [--help]"; exit 1 ;;
    esac
done

# ---- Prerequisites ----
if ! command -v gh &>/dev/null; then
    echo "ERROR: 'gh' CLI is required for PR protection. Install: https://cli.github.com/"
    exit 1
fi
if ! gh auth status &>/dev/null; then
    echo "ERROR: 'gh' is not authenticated. Run: gh auth login"
    exit 1
fi

echo "=== Repository Cleanup ==="
echo "Mode: $(if $DRY_RUN; then echo 'DRY RUN (report only)'; else echo 'FORCE (will delete)'; fi)"
echo

# ---- 1. Fetch & prune ----
echo "--- Step 1: Fetch & prune remote refs ---"
git fetch --prune origin 2>&1
echo

# ---- 2. Remote merged branches ----
echo "--- Step 2: Remote branches merged into $MAIN_BRANCH ---"
mapfile -t MERGED_REMOTE < <(git branch -r --merged "origin/$MAIN_BRANCH" \
    | grep -v "$MAIN_BRANCH" | grep -v HEAD | sed 's|^ *origin/||' || true)

# Filter out branches with open PRs
SAFE_REMOTE=()
PROTECTED_REMOTE=()
for branch in "${MERGED_REMOTE[@]+"${MERGED_REMOTE[@]}"}"; do
    [ -z "$branch" ] && continue
    open_prs=$(gh pr list --head "$branch" --state open --json number --jq length 2>/dev/null || echo "0")
    if [ "$open_prs" = "0" ] || [ -z "$open_prs" ]; then
        SAFE_REMOTE+=("$branch")
    else
        PROTECTED_REMOTE+=("$branch")
    fi
done

echo "  Safe to delete: ${#SAFE_REMOTE[@]}"
for b in "${SAFE_REMOTE[@]+"${SAFE_REMOTE[@]}"}"; do echo "    - $b"; done
if [ "${#PROTECTED_REMOTE[@]}" -gt 0 ]; then
    echo "  Protected (open PRs): ${#PROTECTED_REMOTE[@]}"
    for b in "${PROTECTED_REMOTE[@]}"; do echo "    - $b (has open PR)"; done
fi

if ! $DRY_RUN && [ "${#SAFE_REMOTE[@]}" -gt 0 ]; then
    echo
    read -rp "  Delete ${#SAFE_REMOTE[@]} remote branches? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy] ]]; then
        git push origin --delete "${SAFE_REMOTE[@]}"
        echo "  Deleted ${#SAFE_REMOTE[@]} remote branches."
    fi
fi
echo

# ---- 3. Local merged branches ----
echo "--- Step 3: Local branches merged into $MAIN_BRANCH ---"
mapfile -t MERGED_LOCAL < <(git branch --merged "$MAIN_BRANCH" \
    | grep -v "$MAIN_BRANCH" | grep -v '\*' | sed 's/^[+ ]*//' || true)

SAFE_LOCAL=()
WORKTREE_LOCAL=()
for branch in "${MERGED_LOCAL[@]+"${MERGED_LOCAL[@]}"}"; do
    [ -z "$branch" ] && continue
    # Check if branch is checked out in a worktree
    if git worktree list | grep -q "\[$branch\]"; then
        WORKTREE_LOCAL+=("$branch")
    else
        SAFE_LOCAL+=("$branch")
    fi
done

echo "  Safe to delete: ${#SAFE_LOCAL[@]}"
for b in "${SAFE_LOCAL[@]+"${SAFE_LOCAL[@]}"}"; do echo "    - $b"; done
if [ "${#WORKTREE_LOCAL[@]}" -gt 0 ]; then
    echo "  In worktrees (skip): ${#WORKTREE_LOCAL[@]}"
    for b in "${WORKTREE_LOCAL[@]}"; do echo "    - $b"; done
fi

if ! $DRY_RUN && [ "${#SAFE_LOCAL[@]}" -gt 0 ]; then
    echo
    read -rp "  Delete ${#SAFE_LOCAL[@]} local branches? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy] ]]; then
        for b in "${SAFE_LOCAL[@]}"; do
            if ! git branch -d "$b" 2>&1; then
                echo "    Warning: -d failed for $b, using -D (branch was merged into $MAIN_BRANCH)"
                git branch -D "$b"
            fi
        done
        echo "  Deleted ${#SAFE_LOCAL[@]} local branches."
    fi
fi
echo

# ---- 4. Stale worktrees ----
echo "--- Step 4: Worktree status ---"
STALE_WORKTREES=()
while read -r line; do
    wt_path=$(echo "$line" | awk '{print $1}')
    wt_branch=$(echo "$line" | sed -n 's/.*\[\(.*\)\].*/\1/p')
    # Skip empty branch (detached HEAD) and main branch
    if [ -z "$wt_branch" ] || [ "$wt_branch" = "$MAIN_BRANCH" ]; then
        echo "    OK:    $wt_path [$wt_branch]"
        continue
    fi
    # Check if branch is merged into main
    if git branch --merged "$MAIN_BRANCH" | grep -qw "$wt_branch"; then
        echo "    STALE: $wt_path [$wt_branch] (merged into $MAIN_BRANCH)"
        STALE_WORKTREES+=("$wt_path")
    else
        echo "    OK:    $wt_path [$wt_branch]"
    fi
done < <(git worktree list)

if ! $DRY_RUN && [ "${#STALE_WORKTREES[@]}" -gt 0 ]; then
    echo
    echo "  ${#STALE_WORKTREES[@]} stale worktrees found."
    read -rp "  Remove stale worktrees? [y/N] " confirm
    if [[ "$confirm" =~ ^[Yy] ]]; then
        for wt in "${STALE_WORKTREES[@]}"; do
            echo "    Removing: $wt"
            git worktree remove --force "$wt" 2>&1 || echo "    FAILED: $wt"
        done
        git worktree prune
        echo "  Removed ${#STALE_WORKTREES[@]} stale worktrees."
    fi
fi
echo

# ---- 5. Stash report ----
echo "--- Step 5: Stash aging report ---"
STASH_COUNT=$(git stash list | wc -l)
if [ "$STASH_COUNT" -eq 0 ]; then
    echo "  No stashes. Clean."
else
    echo "  $STASH_COUNT stash entries:"
    git stash list | while read -r stash; do
        echo "    $stash"
    done
    echo
    echo "  Review stashes manually before dropping: git stash show stash@{N}"
    if ! $DRY_RUN; then
        read -rp "  Drop all $STASH_COUNT stashes? [y/N] " confirm
        if [[ "$confirm" =~ ^[Yy] ]]; then
            git stash clear
            echo "  All stashes dropped."
        fi
    fi
fi
echo

# ---- Summary ----
echo "=== Summary ==="
echo "  Remote branches: $(git branch -r | grep -v HEAD | wc -l)"
echo "  Local branches:  $(git branch | wc -l)"
echo "  Worktrees:       $(git worktree list | wc -l)"
echo "  Stashes:         $(git stash list | wc -l)"
echo
echo "Recommended weekly: git fetch --prune && ./scripts/repo_cleanup.sh"
