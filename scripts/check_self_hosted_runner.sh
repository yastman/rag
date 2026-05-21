***REMOVED***!/usr/bin/env bash
***REMOVED*** scripts/check_self_hosted_runner.sh
***REMOVED***
***REMOVED*** Diagnostic for the self-hosted GitHub Actions runner that
***REMOVED*** .github/workflows/nightly-heavy.yml depends on.
***REMOVED***
***REMOVED*** Closes ***REMOVED***1531: nightly-heavy.yml uses `runs-on: self-hosted` (no labels).
***REMOVED*** If no runner is registered + online, the nightly heavy-tier job will
***REMOVED*** queue forever and silently miss its 02:30 UTC schedule.
***REMOVED***
***REMOVED*** This script is operator-runnable. It does not mutate anything.
***REMOVED***
***REMOVED*** Usage:
***REMOVED***   scripts/check_self_hosted_runner.sh             ***REMOVED*** check current repo (auto-detect)
***REMOVED***   scripts/check_self_hosted_runner.sh --owner X --repo Y
***REMOVED***   OWNER=X REPO=Y scripts/check_self_hosted_runner.sh
***REMOVED***   scripts/check_self_hosted_runner.sh --help
***REMOVED***
***REMOVED*** Exit codes:
***REMOVED***   0  at least one runner is registered AND online
***REMOVED***   1  no runner registered, or all registered runners are offline
***REMOVED***   2  invalid arguments / missing prerequisites (gh, jq)

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<'USAGE'
Usage: scripts/check_self_hosted_runner.sh [--owner OWNER --repo REPO]

Verifies that a self-hosted GitHub Actions runner is registered and online for
the repository that runs `.github/workflows/nightly-heavy.yml`.

Options:
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
  0   at least one runner is registered AND status="online"
  1   no runners, or every runner is offline
  2   missing prerequisites or invalid arguments

Resource checklist for the heavy-tier job (markers:
requires_extras / load / chaos / e2e / benchmark):
  - CPU:   >= 4 vCPU recommended (the workflow uses pytest -n auto)
  - RAM:   >= 8 GiB recommended (e2e + benchmark suites load BGE/ColBERT models)
  - Disk:  >= 20 GiB free for uv cache, model downloads, and pytest artifacts
  - Net:   outbound HTTPS to GitHub, PyPI, HuggingFace
  - Tools: docker (for compose-backed e2e), Python 3.12 via uv, git
USAGE
}

err() {
  printf '%s: %s\n' "${SCRIPT_NAME}" "$*" >&2
}

resource_checklist() {
  cat <<'CHECKLIST'

Resource checklist for nightly-heavy.yml (markers:
requires_extras / load / chaos / e2e / benchmark):
  [ ] CPU:   >= 4 vCPU (workflow runs `pytest -n auto`)
  [ ] RAM:   >= 8 GiB (e2e/benchmark load embedding + reranker models)
  [ ] Disk:  >= 20 GiB free for uv cache + model weights + pytest artifacts
  [ ] Net:   outbound HTTPS to GitHub, PyPI, HuggingFace
  [ ] Tools: docker, Python 3.12 (via uv), git, jq
  [ ] Service: GitHub Actions runner installed as a systemd unit and enabled
CHECKLIST
}

OWNER="${OWNER:-}"
REPO="${REPO:-}"

while [[ $***REMOVED*** -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --owner)
      [[ $***REMOVED*** -ge 2 ]] || { err "--owner requires a value"; exit 2; }
      OWNER="$2"
      shift 2
      ;;
    --repo)
      [[ $***REMOVED*** -ge 2 ]] || { err "--repo requires a value"; exit 2; }
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

***REMOVED*** Prerequisite checks.
if ! command -v gh >/dev/null 2>&1; then
  err "GitHub CLI ('gh') is required but not on PATH"
  exit 2
fi
if ! command -v jq >/dev/null 2>&1; then
  err "'jq' is required but not on PATH"
  exit 2
fi

***REMOVED*** Auto-detect owner/repo via gh if not provided.
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

***REMOVED*** Query the runners API. If the call itself fails (auth, scope, network),
***REMOVED*** treat it as a hard failure (exit 1) so the nightly-heavy gate stays red.
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
  err "nightly-heavy.yml will queue forever until at least one runner registers"
  resource_checklist
  exit 1
fi

***REMOVED*** Pretty summary of every runner: name, status, OS, labels, busy.
printf '%s\n' "${runners_json}" \
  | jq '.[] | {name, status, os, labels: [.labels[].name], busy}'

online="$(printf '%s' "${runners_json}" | jq '[.[] | select(.status == "online")] | length')"

if [[ "${online}" -eq 0 ]]; then
  err "found ${count} runner(s), but NONE are online"
  err "see docs/runbooks/SELF_HOSTED_RUNNER.md for recovery steps"
  resource_checklist
  exit 1
fi

printf '\nOK: %s runner(s) online out of %s registered.\n' "${online}" "${count}"
resource_checklist
exit 0
