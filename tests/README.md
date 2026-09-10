# Tests

[AGENTS.md](../AGENTS.md) owns required checks by change type.
This page explains executable lanes; [test-writing guide](../docs/engineering/test-writing-guide.md)
owns conventions. [Makefile](../Makefile) and [pyproject.toml](../pyproject.toml) own selectors,
markers, and tool configuration.

## Environment

Run from the repository root in an isolated worktree. Use Python 3.12 and the frozen lock.

```bash
uv sync --frozen                    # Base + dev; exact check-frozen environment
uv sync --frozen --extra telegram   # When exercising Telegram owners
uv sync --frozen --extra redis      # Redis client cohort (redis-py + RedisVL, #3365)
uv sync --frozen --extra bge-extras # FastAPI endpoint tests, not the BGE model environment
```

These are alternative dependency selections. An exact sync may remove packages installed
by the previous selection. The current check-frozen recipe checks the base+dev selection;
return the isolated environment to `uv sync --frozen` before `make candidate-check`.
Do not alter a shared developer environment to satisfy this requirement. Service-local
model/image dependencies are separate from root endpoint-test extras.

## Choose a lane

| Command | Proves | Prerequisites |
| --- | --- | --- |
| Focused `uv run --no-sync pytest <path> -q` | Changed behavior/contract | Dependencies for that test |
| `make test-core` | Core/runtime, regression, characterization, selected import boundaries | Base + dev |
| `make test` | test-core plus no-service integration/smoke | Base + dev |
| `make test-contract` | Repository contracts, excluding requires_extras | Base + dev; optional checks may skip |
| `make test-unit` | Broad lean unit lane with explicit exclusions | Base + dev; exclusions are in Makefile |
| `make test-telegram-adapter` | Telegram adapter owners | Target syncs Telegram dependencies |
| `make test-ingestion` | Markdown ingestion | Target syncs dev groups |
| `make test-bge-extras` | Mocked BGE HTTP endpoint behavior | Target syncs bge-extras; no model/service needed |
| `make candidate-check` | Required local delivery gate | Exact base+dev environment |
| `make test-full` | Full manual suite, parallel-safe then stateful/live lanes | All extras/groups; required services/credentials |
| `make e2e-core-live` | Real known-corpus core ingestion/answer path | Qdrant, BGE-M3, provider configuration |
| `make demo-gate` | Operator demo readiness and Telegram journey | Configured stack, test account/credentials |

candidate-check runs check-frozen (environment + Ruff + MyPy), format-check, test, and
test-contract. A skipped optional/live check is not proof that capability works.
Coverage is a separate `make test-cov` check, configured in pyproject.toml.

## Native Windows checks

Use PowerShell with the root lock; Make recipes require POSIX tools. For a focused test:

```powershell
uv run --no-sync --python 3.12 pytest tests/unit/core/ -q
uv run --no-sync --python 3.12 pytest tests/contract -q -n 0 -m "not requires_extras"
```

The cross-platform pre-push hook in [.pre-commit-config.yaml](../.pre-commit-config.yaml)
contains the complete core selector. Do not replace it with only tests/unit/core and claim
the full core gate ran.

[scripts/windows_preflight.ps1](../scripts/windows_preflight.ps1) offers Static, Tests,
and Full modes. Full syncs all extras/groups and executes the native full-suite route;
it is not identical to candidate-check. Use WSL or a Linux container for the POSIX delivery
gate and Linux portability. See [Local Development](../docs/LOCAL-DEVELOPMENT.md).

## Test ownership

| Directory | Purpose |
| --- | --- |
| unit | Isolated logic and adapter tests |
| contract | Import, config, API, and repository constraints |
| regression / characterization | Preserved behavior and known failure cases |
| integration / smoke | No-service component scenarios and separately marked live checks |
| e2e | End-to-end scenarios; helpers have unit tests in unit/e2e_adapters |
| chaos / load | Controlled faults and capacity behavior |
| fixtures / data | Shared test inputs |

Every integration/smoke file carries exactly one file-level no_services or requires_services
marker. Keep credentialed/provider checks out of deterministic lanes. Use fixtures, not a
developer's private .env or data. Do not run live tests merely because credentials are present.

## Hosted and local evidence

GitHub Candidate Gate runs MyPy, core tests, and the no-service lane, alongside hosted
static/security checks. The full contract suite and full local delivery gate are not currently
part of that job. Exact required check names and merge rules live in
[branch protection](../docs/runbooks/BRANCH-PROTECTION.md).

Before claiming success, record the command, exit status, relevant result/skip counts, and
tested commit. Diagnose baseline/environment failures separately; do not ignore them or
change assertions solely to produce a green result.
