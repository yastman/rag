#!/usr/bin/env bash
# Detect and (optionally) remove Docker volumes left behind by
# `git worktree remove` on this repository. Tracks issue #1546.
#
# When a worktree is removed (`git worktree remove ...`) Docker Compose does
# NOT tear down its named volumes. Over time this accumulates many GB of
# orphaned data (HuggingFace caches, Postgres data, Qdrant data, Redis data).
#
# This script:
#   1. Lists active git worktrees in this repository.
#   2. Lists Docker volumes whose project prefix looks like a worktree.
#   3. Reports as orphaned any volume whose project prefix does not map to
#      an active worktree.
#   4. Defaults to dry-run; deletes only when invoked with `--apply`.
#
# Safety:
#   - Active worktree volumes are always preserved.
#   - Long-lived local/dev project prefixes (`dev`, `rag`, `rag-fresh`) are
#     reserved as protected — even if no matching worktree dir exists.
#   - The script itself never calls Docker Compose `down`.
#   - Without `--apply`, no destructive command runs.
#
# Usage:
#   scripts/cleanup_orphaned_worktree_volumes.sh           # dry-run, default
#   scripts/cleanup_orphaned_worktree_volumes.sh --apply   # delete orphans
#   scripts/cleanup_orphaned_worktree_volumes.sh --help    # usage
#
# References:
#   docs/engineering/repo-hygiene-runbook.md
#   DOCKER.md (worktree cleanup section)
#   GitHub issue: https://github.com/yastman/rag/issues/1546

set -euo pipefail

APPLY="false"

# Project prefixes that are NEVER classified as orphan, even when a
# matching worktree directory cannot be found. These are the canonical
# Compose project names used by the main checkout, the VPS, and historic
# `rag-fresh` clones.
PROTECTED_PREFIXES=(
    "dev"
    "rag"
    "rag-fresh"
    "vps"
)

usage() {
    cat <<'USAGE'
Usage: cleanup_orphaned_worktree_volumes.sh [--apply] [--help]

Report or delete Docker volumes left behind by removed git worktrees.

Modes:
  (default)     dry-run report; lists orphan volumes, exits 0 even if any
                are found
  --apply       actually run `docker volume rm` on detected orphans
  -h, --help    show this help and exit 0

Safety:
  - Volumes for active git worktrees are always preserved.
  - Volumes whose project prefix is in the protected list
    (dev, rag, rag-fresh, vps) are always preserved.
  - Without --apply, no Docker mutating command runs.

Exit codes:
  0   success (orphans found in dry-run still returns 0)
  1   docker is not available, or required tooling is missing
  2   bad arguments

USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

# --- preflight ---------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found in PATH; nothing to do." >&2
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "git not found in PATH; cannot enumerate worktrees." >&2
    exit 1
fi

# --- enumerate active worktree project prefixes -----------------------------

# Compose default project name = sanitized basename of the working directory.
# We approximate that by taking each worktree's directory basename, lowercased,
# and stripping characters Compose itself strips. This matches the project
# names emitted by Docker Compose when COMPOSE_PROJECT_NAME is unset.
declare -a active_prefixes=()
while read -r path; do
    [[ -z "$path" ]] && continue
    base="$(basename "$path")"
    # Compose project sanitization: lowercase, replace runs of non-alnum with `-`,
    # then strip leading/trailing `-`. This matches Compose's own normalization.
    sanitized="$(echo "$base" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
    [[ -n "$sanitized" ]] && active_prefixes+=("$sanitized")
done < <(git worktree list --porcelain 2>/dev/null | sed -n 's/^worktree //p')

# Always include protected prefixes
for protected in "${PROTECTED_PREFIXES[@]}"; do
    active_prefixes+=("$protected")
done

is_active_prefix() {
    local candidate="$1"
    for p in "${active_prefixes[@]}"; do
        [[ "$candidate" == "$p" ]] && return 0
    done
    return 1
}

# --- enumerate docker volumes ----------------------------------------------

# We only care about volumes that look like Compose-managed volumes (i.e.
# `<project>_<volume_name>`). We skip volumes without an underscore.
declare -a orphan_volumes=()
declare -a orphan_sizes=()

while read -r vol; do
    [[ -z "$vol" ]] && continue
    if [[ "$vol" != *"_"* ]]; then
        continue
    fi
    project_prefix="${vol%%_*}"
    if is_active_prefix "$project_prefix"; then
        continue
    fi
    orphan_volumes+=("$vol")
done < <(docker volume ls --format '{{.Name}}' 2>/dev/null)

# --- report ----------------------------------------------------------------

if [[ ${#orphan_volumes[@]} -eq 0 ]]; then
    echo "No orphan worktree volumes detected."
    exit 0
fi

echo "Orphan volume report (project prefixes not matching any active worktree):"
echo
printf '  %-60s %s\n' "VOLUME" "PROJECT_PREFIX"
for vol in "${orphan_volumes[@]}"; do
    printf '  %-60s %s\n' "$vol" "${vol%%_*}"
done
echo
echo "Total orphan volumes: ${#orphan_volumes[@]}"

if [[ "$APPLY" != "true" ]]; then
    echo
    echo "Dry-run mode (default). Re-run with --apply to delete the volumes above."
    exit 0
fi

# --- apply ------------------------------------------------------------------

echo
echo "Applying: removing ${#orphan_volumes[@]} volume(s) ..."
removed=0
failed=0
for vol in "${orphan_volumes[@]}"; do
    if docker volume rm "$vol" >/dev/null 2>&1; then
        echo "  removed: $vol"
        removed=$((removed + 1))
    else
        echo "  FAILED:  $vol (still in use? skipping)" >&2
        failed=$((failed + 1))
    fi
done
echo
echo "Removed $removed volume(s); $failed failure(s)."
exit 0
