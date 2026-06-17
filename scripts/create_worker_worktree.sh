#!/usr/bin/env bash
# create_worker_worktree.sh — create a git worktree for swarm workers
# Usage: ./scripts/create_worker_worktree.sh <branch-name> [base-branch] [--force]
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
    echo "Usage: $SCRIPT_NAME <branch-name> [base-branch] [--force]" >&2
    echo "  branch-name   new branch to create" >&2
    echo "  base-branch   base ref (default: current HEAD)" >&2
    echo "  --force       delete existing worktree/branch and recreate" >&2
    exit 1
}

# Parse args
BRANCH=""
BASE=""
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        -*) usage ;;
        *)
            if [[ -z "$BRANCH" ]]; then
                BRANCH="$arg"
            elif [[ -z "$BASE" ]]; then
                BASE="$arg"
            else
                usage
            fi
            ;;
    esac
done

[[ -z "$BRANCH" ]] && usage

WORKTREE_DIR=".worktrees/${BRANCH}"
GITIGNORE=".gitignore"

# Must run from repo root
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "error: not inside a git repository" >&2
    exit 1
fi

# Ensure .worktrees/ is in .gitignore
if ! grep -qxF ".worktrees/" "$GITIGNORE" 2>/dev/null; then
    echo ".worktrees/" >> "$GITIGNORE"
    echo "info: added .worktrees/ to $GITIGNORE"
fi

# Check if branch already exists
BRANCH_EXISTS=0
if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
    BRANCH_EXISTS=1
fi

# Check if worktree already exists
WORKTREE_EXISTS=0
if [[ -d "$WORKTREE_DIR" ]]; then
    WORKTREE_EXISTS=1
fi

if [[ "$BRANCH_EXISTS" -eq 1 || "$WORKTREE_EXISTS" -eq 1 ]]; then
    if [[ "$FORCE" -eq 0 ]]; then
        echo "error: branch '${BRANCH}' or worktree '${WORKTREE_DIR}' already exists; use --force to recreate" >&2
        exit 1
    fi
    # Remove existing worktree then delete branch
    if [[ "$WORKTREE_EXISTS" -eq 1 ]]; then
        git worktree remove --force "$WORKTREE_DIR"
    fi
    if [[ "$BRANCH_EXISTS" -eq 1 ]]; then
        git branch -D "$BRANCH"
    fi
fi

# Resolve the start point. Prefer the FRESH remote tip so a worker never
# branches off a stale local base (root cause of the #2582 conflict): when a
# base is given, fetch origin/<base> and branch from it if it exists; otherwise
# fall back to the given ref (local branch / SHA / detached).
START="$BASE"
NO_TRACK=()
if [[ -n "$BASE" ]]; then
    if git fetch origin "$BASE" --quiet 2>/dev/null \
        && git show-ref --verify --quiet "refs/remotes/origin/${BASE}"; then
        START="origin/${BASE}"
        # --no-track: base the worker branch on the fresh remote tip WITHOUT
        # adopting origin/<base> as upstream (else a bare `git push` would target
        # <base>). The worker must push with an explicit refspec to its own branch.
        NO_TRACK=(--no-track)
        echo "info: basing worktree on fresh ${START} (--no-track)"
    fi
fi

# Create worktree on a new branch
if [[ -n "$START" ]]; then
    git worktree add -b "$BRANCH" "${NO_TRACK[@]}" "$WORKTREE_DIR" "$START"
else
    git worktree add -b "$BRANCH" "$WORKTREE_DIR"
fi

FULL_PATH="$(realpath "$WORKTREE_DIR")"
echo "$FULL_PATH"
