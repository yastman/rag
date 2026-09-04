# Runbook: dev branch protection and required checks (#3327)

## Required status checks on `dev`

All of these are deterministic: no credentials, no live external providers,
no stateful services.

| Check (exact name) | Workflow | Covers |
| --- | --- | --- |
| `CodeQL` | codeql | static security analysis |
| `Compose Config` | CI | Compose topology renders |
| `CVE Scan` | CI | dependency CVE gate (critical/high) |
| `Candidate Gate` | CI | mypy + monolith core unit + no-service lane |
| `GitHub Actions Lint` | CI | actionlint |
| `Lint` | CI | Ruff lint + Ruff format check |
| `Lockfile Check` | CI | `uv lock --locked` |
| `Secret Scan` | CI | gitleaks |
| `Semgrep` | CI | project Semgrep guardrails |

`Candidate Gate` mirrors the local candidate lanes (`mypy`, `make test-core`,
`make test-no-service-lane`). The contract suite intentionally joins this job
only after #3437 (env-ownership ownership repair) lands through #3328; until
then it still carries a known red pair and must not gate `dev`.

## Intentionally advisory

- Live credentialed checks (real Telegram/LLM/STT smokes, #3412) never gate.
- Local-only gates (`make candidate-check` full run, deptry, pip-audit
  advisory output) stay authoritative for delivery but do not run in hosted
  CI; local gates remain the delivery contract per `AGENTS.md`.

## Emergency procedure

Required checks block PR merges into `dev` for everyone, including admins
(`enforce_admins` is enabled). If hosted CI is broken and an urgent fix must
land:

1. Fix forward if at all possible — a revert PR also passes CI.
2. If CI itself is the outage, an admin may temporarily update the
   protection: `gh api -X PUT repos/yastman/rag/branches/dev/protection
   --input <payload-without-required-checks>` (or via Settings → Branches →
   dev). Record the reason and the window in this file's changelog section
   below.
3. Restore the payload immediately after the outage and re-run the failed
   checks on the final head so the promoted SHA has green evidence.

Direct pushes to `dev` bypass required status checks by GitHub design; the
AGENTS.md delivery flow (branch → focused tests → `--no-ff` merge of a
tested candidate) remains the only sanctioned way to move `dev`, and CI runs
on every push to `dev` as the post-hoc gate.

## Changelog

- 2026-09-04 — #3327: required status checks enabled for the nine contexts
  above (`strict: false`, `enforce_admins: true`). Proof of enforcement:
  PR #3463 with failing `Lint`/`Candidate Gate` was refused
  (`mergeStateStatus: BLOCKED`, "base branch policy prohibits the merge").
  This PR is the companion green-path proof: all required checks pass and
  the merge is accepted under the same policy.
