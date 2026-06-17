#!/usr/bin/env bash
# list_installed_skills.sh — показать установленные skills
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/.kiro/skills"
REFERENCE_DIR="$REPO_ROOT/.kiro/skills_reference/superpowers"

echo "Active skills:"
if [[ -d "$SKILLS_DIR" ]]; then
  for skill_dir in "$SKILLS_DIR"/*/; do
    [[ -f "$skill_dir/SKILL.md" ]] && echo "- $(basename "$skill_dir")"
  done
else
  echo "  (none — run ./scripts/install_ready_skills.sh)"
fi

echo ""
echo "Reference-only:"
if [[ -d "$REFERENCE_DIR" ]]; then
  for skill_dir in "$REFERENCE_DIR"/*/; do
    [[ -f "$skill_dir/SKILL.md" ]] && echo "- $(basename "$skill_dir")"
  done
else
  echo "  (none)"
fi

LOCK="$REPO_ROOT/.kiro/skills.lock.json"
if [[ -f "$LOCK" ]]; then
  echo ""
  echo "Lock file: $LOCK"
  python3 -c "
import json
from pathlib import Path
lock = json.loads(Path('$LOCK').read_text())
for src in lock['sources']:
    print(f\"  {src['name']}: {src['commit'][:8]}\")
"
fi
