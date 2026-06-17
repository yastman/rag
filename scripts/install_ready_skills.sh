#!/usr/bin/env bash
# install_ready_skills.sh — скачать и установить community skills
# Usage: ./scripts/install_ready_skills.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/.kiro/skills"
REFERENCE_DIR="$REPO_ROOT/.kiro/skills_reference/superpowers"
LOCK_FILE="$REPO_ROOT/.kiro/skills.lock.json"
TMPDIR_WORK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_WORK"' EXIT

MATT_REPO="https://github.com/mattpocock/skills"
OBRA_REPO="https://github.com/obra/superpowers"

ACTIVE_MATT=(
  "skills/productivity/grill-me"
  "skills/engineering/grill-with-docs"
)

ACTIVE_OBRA=(
  # Orchestrator/planner skills (forbidden in worker Required Superpowers per
  # validate_worker_prompt.py FORBIDDEN_WORKER_SUPERPOWERS; valid for orchestrator use).
  "skills/writing-plans"
  "skills/using-git-worktrees"
  "skills/finishing-a-development-branch"
  # Worker superpowers (allowed in worker Required Superpowers).
  "skills/test-driven-development"
  "skills/requesting-code-review"
  "skills/receiving-code-review"
)

REFERENCE_OBRA=(
  "skills/using-superpowers"
  "skills/subagent-driven-development"
  "skills/executing-plans"
  "skills/dispatching-parallel-agents"
)

echo "Cloning repositories..."
git clone --depth=1 "$MATT_REPO" "$TMPDIR_WORK/mattpocock" -q
git clone --depth=1 "$OBRA_REPO" "$TMPDIR_WORK/superpowers" -q

MATT_SHA=$(git -C "$TMPDIR_WORK/mattpocock" rev-parse HEAD)
OBRA_SHA=$(git -C "$TMPDIR_WORK/superpowers" rev-parse HEAD)

mkdir -p "$SKILLS_DIR" "$REFERENCE_DIR"

echo ""
echo "Installed active skills:"
for path in "${ACTIVE_MATT[@]}"; do
  name=$(basename "$path")
  mkdir -p "$SKILLS_DIR/$name"
  cp "$TMPDIR_WORK/mattpocock/$path/SKILL.md" "$SKILLS_DIR/$name/SKILL.md"
  echo "- $name"
done
for path in "${ACTIVE_OBRA[@]}"; do
  name=$(basename "$path")
  mkdir -p "$SKILLS_DIR/$name"
  cp "$TMPDIR_WORK/superpowers/$path/SKILL.md" "$SKILLS_DIR/$name/SKILL.md"
  echo "- $name"
done

echo ""
echo "Installed reference-only skills:"
for path in "${REFERENCE_OBRA[@]}"; do
  name=$(basename "$path")
  mkdir -p "$REFERENCE_DIR/$name"
  cp "$TMPDIR_WORK/superpowers/$path/SKILL.md" "$REFERENCE_DIR/$name/SKILL.md"
  echo "- $name"
done

# Write lock file
python3 - << PYEOF
import json
from pathlib import Path

active_matt = [p.split("/")[-1] for p in """$(printf '%s\n' "${ACTIVE_MATT[@]}")""".strip().splitlines()]
active_obra = [p.split("/")[-1] for p in """$(printf '%s\n' "${ACTIVE_OBRA[@]}")""".strip().splitlines()]
reference_obra = [p.split("/")[-1] for p in """$(printf '%s\n' "${REFERENCE_OBRA[@]}")""".strip().splitlines()]

lock = {
    "sources": [
        {
            "name": "mattpocock-skills",
            "repo": "$MATT_REPO",
            "commit": "$MATT_SHA",
            "active": [f"skills/productivity/{s}" if s in ["grill-me"] else f"skills/engineering/{s}" for s in active_matt]
        },
        {
            "name": "superpowers",
            "repo": "$OBRA_REPO",
            "commit": "$OBRA_SHA",
            "active": [f"skills/{s}" for s in active_obra],
            "reference_only": [f"skills/{s}" for s in reference_obra]
        }
    ]
}
Path("$LOCK_FILE").write_text(json.dumps(lock, indent=2) + "\n")
PYEOF

echo ""
echo "Lock file written:"
echo "$LOCK_FILE"
