#!/usr/bin/env bash
# list_installed_skills.sh — показать установленные skills
set -euo pipefail

# Global ~/.kiro/skills/ is canonical (the project .kiro/skills/ copy was
# migrated to global and removed). Override with the SKILLS_DIR env var.
# card_8b4812e5777a.
SKILLS_DIR="${SKILLS_DIR:-$HOME/.kiro/skills}"
SKILLS_HOME="$(dirname "$SKILLS_DIR")"
REFERENCE_DIR="$SKILLS_HOME/skills_reference/superpowers"

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

LOCK="$SKILLS_HOME/skills.lock.json"
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
