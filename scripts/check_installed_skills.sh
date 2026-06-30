#!/usr/bin/env bash
# check_installed_skills.sh — проверить активные skills на опасные паттерны
set -euo pipefail

# Global ~/.kiro/skills/ is canonical (the project .kiro/skills/ copy was
# migrated to global and removed). Override with the SKILLS_DIR env var.
# card_8b4812e5777a.
SKILLS_DIR="${SKILLS_DIR:-$HOME/.kiro/skills}"

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
  echo "ERROR: no skills directory found (tried project .kiro/skills/ and $HOME/.kiro/skills/)."
  exit 1
fi

# Per-skill pattern exemptions. A skill that legitimately documents a blocked
# pattern as an ORCHESTRATOR instruction or a documented cleanup step (never as a
# worker command) is exempted for THAT (skill, pattern) pair only — every other
# pattern is still enforced for the skill. Narrower than skipping the whole skill,
# which silenced all blocked patterns for gh-pr-review. card_56674e2201a8.
declare -A PATTERN_EXEMPTIONS=(
  ["gh-pr-review|gh pr merge"]=1        # orchestrator merge step, not a worker command
  ["swarm-acceptance|gh pr merge"]=1    # orchestrator disposition instruction
  ["swarm-orchestrator|gh pr merge"]=1  # orchestrator auto-merge policy (mirror step), not a worker command
  ["swarm-pr-review-flow|gh pr merge"]=1 # orchestrator merge-disposition prose ("not a gh pr merge"), not a worker command
  ["codeindex-index-transfer|rm -rf"]=1 # documented index-cleanup step in prose
)

skill_files=( "$SKILLS_DIR"/*/SKILL.md )
count=${#skill_files[@]}
found_blocked=0

for skill_file in "${skill_files[@]}"; do
  [[ -f "$skill_file" ]] || continue
  skill_name=$(basename "$(dirname "$skill_file")")
  for pattern in "${BLOCKED_PATTERNS[@]}"; do
    [[ -n "${PATTERN_EXEMPTIONS["${skill_name}|${pattern}"]:-}" ]] && continue
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
