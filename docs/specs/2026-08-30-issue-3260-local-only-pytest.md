# Issue #3260 Local-Only Pytest CI Specification

## Outcome

GitHub Actions remains a fast static and security gate. Every pytest suite runs locally through
the repository's documented quality ladder and pre-push hooks instead of a hosted workflow job.

## Evidence

Repository documentation already states that GitHub runs no pytest, but `.github/workflows/ci.yml`
defines a `windows-smoke` job that performs a full dependency sync and invokes
`scripts/windows_preflight.ps1 -Mode Tests`. That mode runs pytest, so the executable policy and
the documented policy disagree.

## Contract

- Remove the complete hosted `windows-smoke` job from `.github/workflows/ci.yml`.
- Keep `scripts/windows_preflight.ps1` and its `Tests` mode unchanged as the native-Windows local
  route.
- Structurally inspect every active `.github/workflows/*.yml` and `*.yaml` workflow command and
  reject direct pytest, `Mode Tests`, and Make test-target execution.
- Preserve Ruff, actionlint, gitleaks Secret Scan, Semgrep, CodeQL, lockfile, Compose, and CVE
  checks.
- Do not add dependencies or change `pyproject.toml` or `uv.lock`.

## Acceptance

The focused policy contract fails against the existing `windows-smoke` job and passes after that
job is removed. Mutation tests prove that direct pytest and wrapped local test routes are rejected
in any active workflow. Local Windows test commands remain documented and executable.

## Rollback

Revert this issue's commit. No runtime, dependency, secret, or data state changes.
