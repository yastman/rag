#!/usr/bin/env bash
# scripts/check_self_hosted_runner.sh
#
# Diagnostic for the self-hosted GitHub Actions runners that
# .github/workflows/trusted-heavy.yml and
# .github/workflows/nightly-heavy.yml depend on.
#
# Closes #1531 and follow-up runner scheduling hardening: PR and nightly
# self-hosted jobs use explicit label groups. If the matching runner is not
# registered + online, the corresponding job queues forever.
#
# The repo uses two custom label groups on self-hosted runners:
#   - pr-fast:      runner with labels self-hosted, Linux, X64, pr-fast
#   - nightly-heavy: runner with labels self-hosted, Linux, X64, nightly-heavy
#
# This script is operator-runnable. It does not mutate anything.
#
# Usage:
#   scripts/check_self_hosted_runner.sh             # require both label groups (default)
#   scripts/check_self_hosted_runner.sh --pr-only   # require only pr-fast
#   scripts/check_self_hosted_runner.sh --owner X --repo Y
#   OWNER=X REPO=Y scripts/check_self_hosted_runner.sh
#   scripts/check_self_hosted_runner.sh --help
#
# Exit codes:
#   0  required label groups have at least one online runner
#   1  no runner registered, all runners offline, or label group missing
#   2  invalid arguments / missing prerequisites (gh, jq)

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: scripts/check_self_hosted_runner.sh [--pr-only] [--owner OWNER --repo REPO]

Verifies that the required self-hosted GitHub Actions runners are registered
and online for this repository.

Label groups required by default:
  pr-fast:        self-hosted, Linux, X64, pr-fast
                    (used by trusted-heavy.yml fast-tests and
                     heavy-contract-tests jobs)
  nightly-heavy:  self-hosted, Linux, X64, nightly-heavy
                    (used by nightly-heavy.yml heavy-tier job)

Options:
  --pr-only       Require only the pr-fast label group (skip nightly-heavy)
  --owner OWNER   GitHub owner/org (default: parsed from `gh repo view`)
  --repo REPO     Repository name  (default: parsed from `gh repo view`)
  -h, --help      Show this help and exit

Environment:
  OWNER, REPO     Same as --owner / --repo (flags win if both are set)
  GH_TOKEN        Optional; otherwise `gh auth status` must be authenticated
                  with a token that has `repo` + `actions:read` scopes.

Prerequisites:
  - GitHub CLI (`gh`) authenticated as a user with admin/Actions read on the repo
  - `jq` for JSON parsing

Exit codes:
  0   required label groups have at least one online runner each
  1   no runners, or every runner is offline, or required label group missing
  2   missing prerequisites or invalid arguments

Resource checklist (both workflows use pytest -n auto; nightly also loads
BGE-M3 + ColBERT models):
  - CPU:   >= 4 vCPU recommended
  - RAM:   >= 8 GiB recommended
  - Disk:  >= 20 GiB free for uv cache, model downloads, and pytest artifacts
  - Net:   outbound HTTPS to GitHub, PyPI, HuggingFace
  - Tools: docker (for compose-backed e2e), Python 3.12 via uv, git, jq
USAGE
}

err() {
  printf '%s: %s\n' "${SCRIPT_NAME}" "$*" >&2
}

resource_checklist() {
  cat <<'CHECKLIST'

Resource checklist (both workflows use pytest -n auto;
nightly also loads BGE-M3 + ColBERT models):
  [ ] CPU:   >= 4 vCPU
  [ ] RAM:   >= 8 GiB
  [ ] Disk:  >= 20 GiB free for uv cache + model weights + pytest artifacts
  [ ] Net:   outbound HTTPS to GitHub, PyPI, HuggingFace
  [ ] Tools: docker, Python 3.12 (via uv), git, jq
  [ ] Service/autostart: GitHub Actions runner starts after host or WSL restart
CHECKLIST
}

# Label-group definition: a human name, the exact labels a runner must carry,
# and the workflows that depend on it.
declare -A LABEL_GROUP_NAMES
LABEL_GROUP_NAMES[pr-fast]="self-hosted, Linux, X64, pr-fast"
LABEL_GROUP_NAMES[nightly-heavy]="self-hosted, Linux, X64, nightly-heavy"

declare -A LABEL_GROUP_PURPOSE
LABEL_GROUP_PURPOSE[pr-fast]="trusted-heavy.yml (fast-tests, heavy-contract-tests)"
LABEL_GROUP_PURPOSE[nightly-heavy]="nightly-heavy.yml (heavy-tier)"

# ---------------------------------------------------------------------------
# check_label_group  <group_key>  <runners_json>
#
# Returns 0 if at least one online runner carries every label in the group.
# Returns 1 if no online runner satisfies the group.
# ---------------------------------------------------------------------------
check_label_group() {
  local group_key="$1"
  local runners_json="$2"
  local label_names="${LABEL_GROUP_NAMES[$group_key]}"

  # Build a jq filter that chains select() calls: one for online status,
  # then one per required label. Each select() acts as a narrowing gate.
  # When all succeed, the runner object flows through; otherwise it is dropped.
  local jq_filter="[.[] | select(.status == \"online\")"
  IFS=', ' read -r -a label_arr <<< "${label_names}"
  local label
  for label in "${label_arr[@]}"; do
    jq_filter+=" | select(.labels[].name == \"${label}\")"
  done
  jq_filter+="] | length"

  local online_count
  online_count="$(printf '%s' "${runners_json}" | jq "${jq_filter}")"

  if [[ "${online_count}" -gt 0 ]]; then
    return 0
  fi
  return 1
}

# ---------------------------------------------------------------------------
# fail_label_group  <group_key>
#
# Print a clear error describing which label group is missing and its purpose.
# ---------------------------------------------------------------------------
fail_label_group() {
  local group_key="$1"
  err "no online runner found with labels: ${LABEL_GROUP_NAMES[$group_key]}"
  err "this label group is required by: ${LABEL_GROUP_PURPOSE[$group_key]}"
}

OWNER="${OWNER:-}"
REPO="${REPO:-}"
PR_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --pr-only)
      PR_ONLY=1
      shift
      ;;
    --owner)
      [[ $# -ge 2 ]] || { err "--owner requires a value"; exit 2; }
      OWNER="$2"
      shift 2
      ;;
    --repo)
      [[ $# -ge 2 ]] || { err "--repo requires a value"; exit 2; }
      REPO="$2"
      shift 2
      ;;
    *)
      err "unknown argument: $1"
      usage >&2
      exit 2
      ;;
  esac
done

# Prerequisite checks.
if ! command -v gh >/dev/null 2>&1; then
  err "GitHub CLI ('gh') is required but not on PATH"
  exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
  err "'jq' is required but not on PATH"
  exit 2
fi

# Auto-detect owner/repo via gh if not provided.
if [[ -z "${OWNER}" || -z "${REPO}" ]]; then
  if gh_view="$(gh repo view --json owner,name 2>/dev/null)"; then
    [[ -z "${OWNER}" ]] && OWNER="$(printf '%s' "${gh_view}" | jq -r '.owner.login')"
    [[ -z "${REPO}" ]]  && REPO="$(printf '%s' "${gh_view}" | jq -r '.name')"
  fi
fi

if [[ -z "${OWNER}" || -z "${REPO}" ]]; then
  err "could not determine OWNER/REPO; pass --owner and --repo or run inside a gh-aware checkout"
  exit 2
fi

printf 'Checking self-hosted runners for %s/%s ...\n' "${OWNER}" "${REPO}"
if [[ "${PR_ONLY}" -eq 1 ]]; then
  printf 'Mode: --pr-only (only pr-fast label group is required)\n'
else
  printf 'Mode: default (both pr-fast and nightly-heavy label groups required)\n'
fi

# Query the runners API. If the call itself fails (auth, scope, network),
# treat it as a hard failure (exit 1) so the nightly-heavy gate stays red.
if ! runners_json="$(gh api \
  "repos/${OWNER}/${REPO}/actions/runners" \
  --jq '.runners // []' 2>&1)"; then
  err "gh api call failed:"
  printf '%s\n' "${runners_json}" >&2
  resource_checklist
  exit 1
fi

count="$(printf '%s' "${runners_json}" | jq 'length')"

if [[ "${count}" -eq 0 ]]; then
  err "no self-hosted runners are registered on ${OWNER}/${REPO}"
  if [[ "${PR_ONLY}" -eq 1 ]]; then
    err "trusted-heavy.yml PR jobs will queue forever until at least one runner registers with label 'pr-fast'"
  else
    err "trusted-heavy.yml AND nightly-heavy.yml will queue forever until runners register with labels 'pr-fast' and 'nightly-heavy'"
  fi
  resource_checklist
  exit 1
fi

# Pretty summary of every runner: name, status, OS, labels, busy.
printf '%s\n' "${runners_json}" \
  | jq '.[] | {name, status, os, labels: [.labels[].name], busy}'

online="$(printf '%s' "${runners_json}" | jq '[.[] | select(.status == "online")] | length')"

if [[ "${online}" -eq 0 ]]; then
  err "found ${count} runner(s), but NONE are online"
  err "see docs/runbooks/SELF_HOSTED_RUNNER.md for recovery steps"
  resource_checklist
  exit 1
fi

# Verify required label groups.
exit_code=0

if ! check_label_group "pr-fast" "${runners_json}"; then
  fail_label_group "pr-fast"
  exit_code=1
else
  printf '\npr-fast label group: OK\n'
fi

if [[ "${PR_ONLY}" -eq 0 ]]; then
  if ! check_label_group "nightly-heavy" "${runners_json}"; then
    fail_label_group "nightly-heavy"
    exit_code=1
  else
    printf 'nightly-heavy label group: OK\n'
  fi
fi

if [[ "${exit_code}" -eq 0 ]]; then
  printf '\nOK: all required label groups have at least one online runner.\n'
else
  printf '\nFAIL: one or more required label groups are missing or offline.\n'
fi

resource_checklist
exit "${exit_code}"
