# Solo-Local Quality Gates Design

## Goal

Make local verification authoritative for a powerful single-developer workstation while keeping GitHub as a small, independent security and configuration backstop.

## Principles

- Local tests are the delivery gate. GitHub does not duplicate the full pytest matrix.
- Commit hooks stay fast; push and candidate gates carry progressively broader checks.
- GitHub runs no pytest. It keeps only checks that benefit from GitHub-native security data or validate repository configuration and reproducibility.
- Every declared gate must be runnable, blocking when named as a gate, and scoped to paths that exist.
- Build inputs and dependency audits must be reproducible across every shipped Python environment.

## Local flow

1. `pre-commit` runs syntax, Ruff, formatting, file hygiene, Markdown links, and Gitleaks.
2. `pre-push` runs lint/format plus the deterministic core test gate.
3. Developers run the scope-specific commands documented in `AGENTS.md`: `test-core`, `test`, or `test-contract`.
4. `candidate-check` runs static checks plus the deterministic local test gates required before integration.
5. `test-full` remains a manual local pre-integration gate for major candidates.

Hooks are installed by the standard developer setup. They remain convenience enforcement; the candidate gate is the delivery contract.

## GitHub flow

Keep:

- Gitleaks and GitHub secret scanning;
- CodeQL and project Semgrep rules;
- Ruff formatting/linting and actionlint;
- Compose validation;
- lockfile and vulnerability checks for root, Telegram, and BGE-M3 projects;

Remove:

- the broken coverage ratchet;
- every hosted pytest job, including the duplicate core and broad test workflows;
- the misleading manually triggered `Nightly` workflow and offline self-hosted dependency;
- stale path filters and nonexistent dependency update directories.

## Security and reproducibility

- Gitleaks exclusions target explicit fake fixtures, never whole source-like trees.
- Bandit scans operational scripts as well as application packages.
- Every shipped lockfile receives a frozen-lock check and vulnerability audit.
- GitHub tools use locked project dependencies or explicit versions.
- Container builds pin external Python packages and Hugging Face revisions.
- Published images are built before registry login, scanned before push, and retain SBOM/provenance.

## Verification

- Contract tests assert the intended local/GitHub split and forbid stale paths.
- Focused tests prove each configuration change before broad gates run.
- Final candidate must pass `git diff --check`, pre-commit, local static checks, `test-core`, `test`, `test-contract`, and `test-full` where the environment supports its declared service requirements.
- Hosted workflow syntax is validated with actionlint.
- Linux portability is verified locally through WSL/container execution when preparing a release candidate.

## Non-goals

- Mandatory reviewers for a one-person repository.
- Full pytest, coverage, live-service, chaos, or benchmark execution on GitHub.
- New CI orchestration frameworks or new permanent services.
