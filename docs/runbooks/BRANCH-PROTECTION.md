# Delivering to dev

## Required checks

The protected branch uses these check names. Verify the live policy before changing delivery
configuration; the GitHub API is authoritative for its current settings.

| Check | Workflow | Scope |
| --- | --- | --- |
| CodeQL | codeql | Static security analysis |
| Compose Config | CI | Compose rendering |
| CVE Scan | CI | Dependency severity gate |
| Candidate Gate | CI | MyPy, core, no-service integration/smoke |
| GitHub Actions Lint | CI | actionlint |
| Lint | CI | Ruff lint and format |
| Lockfile Check | CI | Lock consistency |
| Secret Scan | CI | Gitleaks |

See [ci.yml](../../.github/workflows/ci.yml) and
[codeql.yml](../../.github/workflows/codeql.yml) for execution. Candidate Gate covers
deterministic tests but does not currently run the full contract suite. The local
`make candidate-check` delivery gate remains required, including contracts.

## Normal delivery

1. Run the local checks required by [AGENTS.md](../../AGENTS.md) on the candidate.
2. Push the task branch and open a PR targeting dev.
3. Wait for required checks; inspect failures and fix forward.
4. Merge through the normal protected-branch workflow. Fetch and verify the resulting
   commit is contained in origin/dev before reporting delivery.

Do not assume a direct push bypasses protection. Do not use admin merge, force-push,
disable checks, or edit branch protection to deliver an ordinary task.

## Failure and recovery

Distinguish a candidate failure from infrastructure failure using the actual log and commit.
A rerun is appropriate for a diagnosed transient fault; repeating a deterministic failure
does not establish success. Keep blocked work committed on its task branch.

Emergency protection changes require explicit owner authorization for that operation,
a recorded reason and restoration plan, and verification after restoration. Keep incident
evidence with the issue/PR, not in this runbook. Never weaken policy as an automatic fallback.

Live credentialed tests are separate operator checks. They are not silently required or
silently claimed by a hosted deterministic check.
