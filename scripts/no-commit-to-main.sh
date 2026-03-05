#!/usr/bin/env bash
# Block direct commits to main/master. Merges from dev are allowed
# because git merge doesn't trigger the pre-commit stage.
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
    echo "Blocked: direct commit to $BRANCH. Use dev branch."
    echo "Workflow: commit in dev -> merge to main -> push."
    exit 1
fi
