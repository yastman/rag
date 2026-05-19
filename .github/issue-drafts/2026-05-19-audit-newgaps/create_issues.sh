#!/usr/bin/env bash
# Create 3 new GitHub issues from the audit-newgap markdown drafts.
#
# Each markdown file's first H1 (`# title`) becomes the issue title;
# everything after the title becomes the issue body.
#
# Requires: GITHUB_TOKEN env var with `repo` scope, plus `curl` and `jq`.
# Run from the repo root:
#   GITHUB_TOKEN=ghp_xxx bash .github/issue-drafts/2026-05-19-audit-newgaps/create_issues.sh
#
# Or with gh CLI (no token plumbing needed if you're logged in):
#   bash .github/issue-drafts/2026-05-19-audit-newgaps/create_issues.sh --gh

set -euo pipefail

OWNER="yastman"
REPO="rag"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# File -> labels mapping. Labels follow the repo's convention seen in #1658-#1666
# and #1647-#1656 (domain:observability / refactor / status:triaged / priority).
declare -A FILES=(
  ["01-langgraph-send-parallel-fanout.md"]="domain:observability,refactor,SDK-audit,P3-backlog,lane:plan-needed,status:triaged"
  ["02-langgraph-streamwriter-custom-mode.md"]="domain:observability,refactor,SDK-audit,P2-backlog,lane:plan-needed,status:triaged"
  ["03-instructor-streaming-partial.md"]="domain:observability,SDK-audit,P3-backlog,lane:plan-needed,status:triaged"
)

# Ordered keys (associative array iteration order isn't stable in bash)
ORDERED_FILES=(
  "01-langgraph-send-parallel-fanout.md"
  "02-langgraph-streamwriter-custom-mode.md"
  "03-instructor-streaming-partial.md"
)

USE_GH="false"
if [[ "${1:-}" == "--gh" ]]; then
  USE_GH="true"
fi

if [[ "$USE_GH" == "false" && -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN is not set. Either:" >&2
  echo "  - export GITHUB_TOKEN=ghp_xxx (with 'repo' scope), or" >&2
  echo "  - re-run with --gh flag if you have 'gh' CLI installed and authenticated." >&2
  exit 1
fi

create_issue() {
  local file="$1"
  local labels="$2"
  local full_path="${DIR}/${file}"

  if [[ ! -f "$full_path" ]]; then
    echo "  SKIP: file not found: $full_path" >&2
    return 0
  fi

  # Extract title from first H1 (strip leading "# " and any trailing whitespace).
  local title
  title=$(grep -m1 "^# " "$full_path" | sed -E 's/^# +//' | tr -d '\r' | sed -E 's/[[:space:]]+$//')

  if [[ -z "$title" ]]; then
    echo "  FAIL: no H1 found in $file" >&2
    return 1
  fi

  # Body = everything AFTER the first H1 line.
  local body
  body=$(awk 'BEGIN{found=0} /^# /{if(!found){found=1; next}} {if(found) print}' "$full_path")

  echo "==> Creating issue: $title"
  echo "    File:   $file"
  echo "    Labels: $labels"

  if [[ "$USE_GH" == "true" ]]; then
    # gh CLI accepts comma-separated --label values, but its convention is one --label per item.
    local label_args=()
    IFS=',' read -ra LABEL_ARR <<< "$labels"
    for l in "${LABEL_ARR[@]}"; do
      label_args+=(--label "$l")
    done
    gh issue create -R "${OWNER}/${REPO}" \
      --title "$title" \
      --body "$body" \
      "${label_args[@]}" \
      >/dev/null
  else
    # Build JSON payload via jq to handle newlines / special chars safely.
    local labels_json
    # Convert "a,b,c" -> ["a","b","c"]
    labels_json=$(jq -nc --arg s "$labels" '$s | split(",")')
    local payload
    payload=$(jq -n \
      --arg title "$title" \
      --arg body "$body" \
      --argjson labels "$labels_json" \
      '{title: $title, body: $body, labels: $labels}')

    local response_status
    response_status=$(
      curl -sS -o /tmp/create_issue_resp.json -w "%{http_code}" \
        -X POST \
        -H "Authorization: Bearer ${GITHUB_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "https://api.github.com/repos/${OWNER}/${REPO}/issues" \
        --data "$payload"
    )
    if [[ "$response_status" != "201" ]]; then
      echo "    FAIL: HTTP ${response_status}" >&2
      cat /tmp/create_issue_resp.json >&2
      return 1
    fi

    local issue_num
    issue_num=$(jq -r '.number' < /tmp/create_issue_resp.json)
    local issue_url
    issue_url=$(jq -r '.html_url' < /tmp/create_issue_resp.json)
    echo "    OK: #${issue_num} — ${issue_url}"
  fi
}

echo "==> Creating 3 audit follow-up issues from cross-domain SDK audit"
echo ""

for file in "${ORDERED_FILES[@]}"; do
  create_issue "$file" "${FILES[$file]}"
  echo ""
done

echo "==> Done. 3 new issues created."
echo "   Cross-link them under #1538 (SDK-vs-custom audit) for traceability."
