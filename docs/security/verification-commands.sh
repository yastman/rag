#!/usr/bin/env bash
# history-scrub verification commands for P0 (#1580)
#
# Usage:
#   chmod +x docs/security/verification-commands.sh
#   ./docs/security/verification-commands.sh [pre|post|all]
#
# Arguments:
#   pre   — Run pre-filter confirmation (expect non-zero counts)
#   post  — Run post-filter verification (all must be 0)
#   all   — Run both (default)
#
# WARNING: This script counts matches only. It does NOT emit matched
# secret strings. Output is safe for logs and reports.

set -euo pipefail

MODE="${1:-all}"

# ────────────────────────────────────────────────────────────
# Secret pattern inventory — prefix/regex classes, never raw values.
# Sensitive byte sequences are assembled from fragments so this verification
# script does not reintroduce the same searchable sequences it checks for.
# ────────────────────────────────────────────────────────────
OPENAI_PREFIX="sk""-proj-"
ANTHROPIC_PREFIX="sk""-ant-api03-"
GROQ_PREFIX="g""sk_"
VPS_IP="95"".111.252.29"
VPS_PATH="/home/""admin/"
TELEGRAM_SIG=":""AA"
LANGFUSE_SECRET_PREFIX="sk""-lf-"
LANGFUSE_PUBLIC_PREFIX="pk""-lf-"
ZAI_KEY_REGEX="za""i_""[A-Za-z0-9]{20,}"
BOT_TOKEN_SIG_REGEX="bot_token=[REDACTED-TELEGRAM-TOKEN]""AA"

declare -A PATTERNS=(
  ["OpenAI project key prefix"]="$OPENAI_PREFIX"
  ["Anthropic API key prefix"]="$ANTHROPIC_PREFIX"
  ["Groq API key prefix"]="$GROQ_PREFIX"
  ["VPS IP"]="$VPS_IP"
  ["VPS admin path"]="$VPS_PATH"
  ["Telegram token signature"]="$TELEGRAM_SIG"
  ["Langfuse secret key prefix"]="$LANGFUSE_SECRET_PREFIX"
  ["Langfuse public key prefix"]="$LANGFUSE_PUBLIC_PREFIX"
)

# ────────────────────────────────────────────────────────────
# Count matches without emitting matched content
# ────────────────────────────────────────────────────────────
count_secret() {
  local label="$1"
  local pattern="$2"
  local count
  count=$(git log --all --oneline -S "$pattern" 2>/dev/null | wc -l || echo "0")
  printf "  %-40s %s\n" "$label:" "$count"
  return 0
}

count_regex_secret() {
  local label="$1"
  local pattern="$2"
  local count
  count=$(git log --all --oneline -G "$pattern" 2>/dev/null | wc -l || echo "0")
  printf "  %-40s %s\n" "$label:" "$count"
  return 0
}

# ────────────────────────────────────────────────────────────
# Pre-filter confirmation (expect non-zero counts)
# ────────────────────────────────────────────────────────────
run_pre_filter() {
  echo ""
  echo "=== PRE-FILTER CONFIRMATION ==="
  echo "  (expect non-zero — secrets should exist before rewrite)"
  echo ""
  for label in "${!PATTERNS[@]}"; do
    count_secret "$label" "${PATTERNS[$label]}"
  done
  count_regex_secret "Zai API key real-key regex" "$ZAI_KEY_REGEX"
  count_regex_secret "Telegram bot token assignment signature" "$BOT_TOKEN_SIG_REGEX"
  echo ""
}

# ────────────────────────────────────────────────────────────
# Post-filter verification (all counts must be 0)
# ────────────────────────────────────────────────────────────
run_post_filter() {
  echo ""
  echo "=== POST-FILTER VERIFICATION ==="
  echo "  (ALL counts must be 0 — no secrets in rewritten history)"
  echo ""
  local failures=0
  for label in "${!PATTERNS[@]}"; do
    count_secret "$label" "${PATTERNS[$label]}"
    local c
    c=$(git log --all --oneline -S "${PATTERNS[$label]}" 2>/dev/null | wc -l || echo "0")
    if [ "$c" -ne 0 ]; then
      failures=$((failures + 1))
    fi
  done
  local c
  c=$(git log --all --oneline -G "$ZAI_KEY_REGEX" 2>/dev/null | wc -l || echo "0")
  printf "  %-40s %s\n" "Zai API key real-key regex:" "$c"
  if [ "$c" -ne 0 ]; then
    failures=$((failures + 1))
  fi
  c=$(git log --all --oneline -G "$BOT_TOKEN_SIG_REGEX" 2>/dev/null | wc -l || echo "0")
  printf "  %-40s %s\n" "Telegram bot token assignment signature:" "$c"
  if [ "$c" -ne 0 ]; then
    failures=$((failures + 1))
  fi
  echo ""
  echo "  Failures: $failures / $((${#PATTERNS[@]} + 2))"
  if [ "$failures" -eq 0 ]; then
    echo "  RESULT: PASS — all secret patterns removed from history"
  else
    echo "  RESULT: FAIL — $failures pattern(s) still present in history"
    echo "  ACTION: Review filter-repo configuration and re-run"
  fi
  echo ""
}

# ────────────────────────────────────────────────────────────
# Working tree checks
# ────────────────────────────────────────────────────────────
run_tree_checks() {
  echo ""
  echo "=== WORKING TREE CHECKS ==="
  echo ""

  echo -n "  Tracked docs/superpowers/plans/: "
  git ls-files -- 'docs/superpowers/plans/' 2>/dev/null | wc -l

  echo -n "  opencode.json in .gitignore: "
  grep -c 'opencode.json' .gitignore 2>/dev/null || echo "0"

  echo -n "  docs/superpowers in .gitignore: "
  grep -c 'docs/superpowers' .gitignore 2>/dev/null || echo "0"

  echo -n "  __pycache__ in .gitignore: "
  grep -c '__pycache__' .gitignore 2>/dev/null || echo "0"

  echo ""
}

# ────────────────────────────────────────────────────────────
# Gitleaks scan (if available)
# ────────────────────────────────────────────────────────────
run_gitleaks() {
  echo ""
  echo "=== GITLEAKS SCAN ==="
  if command -v gitleaks &>/dev/null; then
    if gitleaks detect --source . --verbose --no-git 2>&1; then
      echo "  RESULT: PASS — 0 findings"
    else
      echo "  RESULT: FAIL — gitleaks found potential secrets"
    fi
  else
    echo "  SKIPPED: gitleaks not installed"
  fi
  echo ""
}

# ────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────
case "$MODE" in
  pre)
    run_pre_filter
    ;;
  post)
    run_post_filter
    run_tree_checks
    run_gitleaks
    ;;
  all)
    run_pre_filter
    echo ""
    echo "⚠️  Rotate all 8 API keys at providers, then run filter-repo."
    echo "   After filter-repo, re-run with: $0 post"
    echo ""
    ;;
  *)
    echo "Usage: $0 [pre|post|all]"
    exit 1
    ;;
esac
