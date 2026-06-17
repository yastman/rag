#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <branch> <title> <body-file> [base-branch]" >&2
    echo "  base-branch default: dev" >&2
    exit 1
}

[[ $# -lt 3 ]] && usage

BRANCH="$1"
TITLE="$2"
BODY_FILE="$3"
BASE="${4:-dev}"

if [[ ! -f "$BODY_FILE" ]]; then
    echo "Error: body-file '$BODY_FILE' not found" >&2
    exit 1
fi

PR_URL=$(gh pr create \
    --base "$BASE" \
    --head "$BRANCH" \
    --title "$TITLE" \
    --body-file "$BODY_FILE") || {
    echo "Error: gh pr create failed" >&2
    exit 1
}

echo "$PR_URL"
