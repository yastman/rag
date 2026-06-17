#!/usr/bin/env bash
# check_installed_skills.sh — проверить активные skills на опасные паттерны
set -euo pipefail

SKILLS_DIR="$(cd "$(dirname "$0")/.." && pwd)/.kiro/skills"

BLOCKED_PATTERNS=(
  "curl | bash"
  "wget | bash"
  "rm -rf"
  "sudo"
  "chmod 777"
  "GITHUB_TOKEN"
  "OPENAI_API_KEY"
  "ANTHROPIC_API_KEY"
  "AWS_SECRET_ACCESS_KEY"
  "send secrets"
  "exfiltrate"
  "ignore previous instructions"
  "modify ~/.kiro"
  "modify .kiro/agents"
  "modify .kiro/skills"
  "gh pr merge"
  "git push --force"
)

if [[ ! -d "$SKILLS_DIR" ]]; then
  echo "ERROR: $SKILLS_DIR not found. Run ./scripts/install_ready_skills.sh first."
  exit 1
fi

skill_files=( "$SKILLS_DIR"/*/SKILL.md )
count=${#skill_files[@]}
found_blocked=0

for skill_file in "${skill_files[@]}"; do
  skill_name=$(basename "$(dirname "$skill_file")")
  # gh-pr-review legitimately mentions merge commands as orchestrator instructions
  [[ "$skill_name" == "gh-pr-review" ]] && continue
  [[ -f "$skill_file" ]] || continue
  skill_name=$(basename "$(dirname "$skill_file")")
  for pattern in "${BLOCKED_PATTERNS[@]}"; do
    if grep -qF "$pattern" "$skill_file" 2>/dev/null; then
      echo "BLOCKED: suspicious pattern '$pattern' found in .kiro/skills/$skill_name/SKILL.md"
      found_blocked=1
    fi
  done
done

if [[ $found_blocked -eq 0 ]]; then
  echo "OK: $count active skills checked."
  echo "No blocked patterns found."
  exit 0
else
  exit 1
fi
