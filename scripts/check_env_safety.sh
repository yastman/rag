#!/usr/bin/env bash
# Safe structural check: verify no real .env files are tracked or present
# in the working tree, and that .gitignore properly ignores them.
#
# Usage:
#   ./scripts/check_env_safety.sh          # Check env safety
#   ./scripts/check_env_safety.sh --ci     # Strict mode (fails on warnings)
#
# Related: scripts/validate_prod_env.sh (production env validation)

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

STRICT_MODE=false
if [ "${1:-}" = "--ci" ]; then
  STRICT_MODE=true
fi

errors=0
warnings=0

# ── Check 1: .gitignore must ignore .env files ──────────────────────────────

if ! grep -qE '^\.env\s*$' .gitignore 2>/dev/null; then
  echo "FAIL: .env is not ignored in .gitignore" >&2
  errors=$((errors + 1))
else
  echo "  OK: .env is ignored"
fi

if ! grep -qE '^\.env\.\*\s*$' .gitignore 2>/dev/null; then
  echo "FAIL: .env.* is not ignored in .gitignore" >&2
  errors=$((errors + 1))
else
  echo "  OK: .env.* is ignored"
fi

if ! grep -qE '^credentials\.json\s*$' .gitignore 2>/dev/null; then
  echo "FAIL: credentials.json is not ignored in .gitignore" >&2
  errors=$((errors + 1))
else
  echo "  OK: credentials.json is ignored"
fi

if ! grep -qE '^secrets\.ya?ml\s*$' .gitignore 2>/dev/null; then
  echo "FAIL: secrets.yaml is not ignored in .gitignore" >&2
  errors=$((errors + 1))
else
  echo "  OK: secrets.yaml is ignored"
fi

# ── Check 2: No non-example .env files tracked in git ───────────────────────

tracked_envs=$(git ls-files | grep -E '^\.env' | grep -v '\.example$' || true)
if [ -n "$tracked_envs" ]; then
  echo "FAIL: Non-example .env files are tracked in git:" >&2
  echo "$tracked_envs" | sed 's/^/  - /' >&2
  errors=$((errors + 1))
else
  echo "  OK: no non-example .env files tracked"
fi

# ── Check 3: No non-example .env files in working tree ──────────────────────

while IFS= read -r -d '' file; do
  basename_file=$(basename "$file")
  # Skip example/template files and common virtualenv paths
  if [[ "$basename_file" == *.example ]]; then
    continue
  fi
  echo "FAIL: Non-example env file detected in working tree: $file" >&2
  echo "  Remove it or rename to .env.example if it's a template." >&2
  errors=$((errors + 1))
done < <(find . -maxdepth 2 -name ".env*" -type f \
  -not -path "./.git/*" \
  -not -path "./node_modules/*" \
  -not -path "./.venv/*" \
  -not -path "./venv/*" \
  -print0)

# ── Check 4: .env.example files should use obvious placeholders ─────────────
# Warn about values that look like real API key prefixes (not empty or <...>)

_real_key_prefixes='sk-ant-|sk-proj-|sk-|gsk_|csk-|pa-|pk-lf-|sk-lf-|Bearer '
_placeholder_pattern='^\s*[A-Z_][A-Z0-9_]*=\s*(<.*>|\s*)$'

for env_example in .env.example .env.local.example telegram_bot/.env.example k8s/secrets/.env.example; do
  if [ ! -f "$env_example" ]; then
    continue
  fi

  # Find lines with real-looking key prefixes that are NOT placeholder-style
  bad_lines=$(grep -nE "^\s*[A-Z_][A-Z0-9_]*=\s*.*(${_real_key_prefixes})" "$env_example" | grep -vE "${_placeholder_pattern}" || true)
  if [ -n "$bad_lines" ]; then
    echo "WARN: $env_example contains values that resemble real API key prefixes:" >&2
    echo "$bad_lines" | sed 's/^/  /' >&2
    warnings=$((warnings + 1))
  fi
done

# ── Summary ─────────────────────────────────────────────────────────────────

if [ "$warnings" -gt 0 ] && [ "$STRICT_MODE" = true ]; then
  echo "" >&2
  echo "Env safety check failed: $warnings warning(s) in strict mode." >&2
  exit 1
fi

if [ "$errors" -gt 0 ]; then
  echo "" >&2
  echo "Env safety check failed with $errors error(s)." >&2
  exit 1
fi

echo "Env safety check passed."
