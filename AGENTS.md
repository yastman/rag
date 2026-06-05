# AGENTS.md

## Purpose

This file is the repo gateway for agents. Keep it short. Do not duplicate
runbooks, Docker contracts, test policy, subsystem ownership, docs maintenance
rules, or worker-specific workflows here.

## Priority

1. Nearest `AGENTS.override.md`
2. This file
3. Linked canonical docs

If a rule belongs to a canonical doc or skill, link it instead of copying it
here.

## Skill Use

Use additional skills only when the user explicitly names them, the task clearly
matches their trigger, or an accepted artifact requires that next step. Do not
cascade into unrelated skills or workflows on your own.

## Start Here

1. Read [`README.md`](README.md) for the project overview.
2. Read [`docs/README.md`](docs/README.md) for documentation navigation.
3. Use [`docs/indexes/`](docs/indexes/) for task-oriented lookup.
4. Use [`docs/runbooks/README.md`](docs/runbooks/README.md) for operational
   investigations.
5. Read the nearest folder `README.md` and `AGENTS.override.md` before scoped
   edits.

## Canonical Docs

- Runtime, Compose, services, ports, env, and deploy surfaces:
  [`DOCKER.md`](DOCKER.md)
- Local setup and validation:
  [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md)
- Issue triage:
  [`docs/engineering/issue-triage.md`](docs/engineering/issue-triage.md)
- Test writing:
  [`docs/engineering/test-writing-guide.md`](docs/engineering/test-writing-guide.md)
- SDK/framework lookup:
  [`docs/engineering/sdk-registry.md`](docs/engineering/sdk-registry.md)
- Docs navigation:
  [`docs/README.md`](docs/README.md), [`docs/indexes/`](docs/indexes/)
- Operational runbooks:
  [`docs/runbooks/README.md`](docs/runbooks/README.md)

## Active Product Simplification

For product simplification, core E2E, Langfuse optionalization, or related
refactor work, treat these as the source of truth:

- [`docs/designs/product-simplification-e2e-plan.md`](docs/designs/product-simplification-e2e-plan.md)
- [`docs/designs/yaroslav-simplification-workflow.md`](docs/designs/yaroslav-simplification-workflow.md)
- [`docs/designs/product-simplification-stage-0-decisions.md`](docs/designs/product-simplification-stage-0-decisions.md)
- [`docs/designs/product-simplification-weekly-acceptance-2026-06-04.md`](docs/designs/product-simplification-weekly-acceptance-2026-06-04.md)

Do not duplicate the plan here. The current protected proof is
`make local-up` followed by `make e2e-core-live`. After the 2026-06-04
acceptance package, simplification/refactor work should preserve that proof and
continue around Stage 4: keep optional surfaces out of required runtime and
validation paths unless a GitHub issue, pull request, or Artem decision says
otherwise.

Do not merge simplification work directly into `dev`. Per
[`docs/designs/yaroslav-simplification-workflow.md`](docs/designs/yaroslav-simplification-workflow.md),
`dev` receives the weekly package only after explicit Artem approval. Work may
move through task branches and `simplification/core` according to the workflow,
but `dev` remains a protected acceptance boundary.

Use one task branch per task:
`simplification/<issue-or-task-number>-<short-name>`. Pull requests for
simplification work target `simplification/core`, not `dev`.

`simplification/core` is the staging/integration branch for monolith migration
work. A task may merge into `simplification/core` without waiting for Artem only
when the PR is opt-in or spike-scoped, preserves the default runtime path,
keeps `make local-up && make e2e-core-live` green, has a GitHub issue/Project
item, and records any Artem decisions as TODOs for the weekly package. This is
allowed for staging evidence only; it does not approve the change for `dev`.

Tasks still require explicit Artem approval before merge into `dev`, before
making a change default behavior, or before applying an irreversible migration
when they change CRM/HITL write behavior, make optional runtime surfaces
required, remove or demote service/container boundaries, change Langfuse/OTel
requirements, change the approved core entrypoint API, make new dependencies
required for default runtime, or change CI/release gate semantics. `dev`
receives only the weekly package after Artem approval.

When a task raises an architectural, product, runtime-surface, approval, or
priority question that requires Artem, do not resolve it ad hoc in code or chat.
Record it as a GitHub issue or Project TODO, mark that it requires Artem's
decision, and include it in the next weekly planning or acceptance checkpoint
from the workflow.

## Local Overrides

- [`telegram_bot/AGENTS.override.md`](telegram_bot/AGENTS.override.md)
- [`k8s/AGENTS.override.md`](k8s/AGENTS.override.md)
- [`src/ingestion/unified/AGENTS.override.md`](src/ingestion/unified/AGENTS.override.md)
- [`scripts/AGENTS.override.md`](scripts/AGENTS.override.md)
- [`services/AGENTS.override.md`](services/AGENTS.override.md)
- [`services/bge-m3-api/AGENTS.override.md`](services/bge-m3-api/AGENTS.override.md)
- [`services/docling/AGENTS.override.md`](services/docling/AGENTS.override.md)
- [`services/user-base/AGENTS.override.md`](services/user-base/AGENTS.override.md)
- [`mini_app/frontend/src/AGENTS.override.md`](mini_app/frontend/src/AGENTS.override.md)

## Safety

Prefer local/test environments. Do not access production, VPS, secrets, SSH,
cloud credentials, or real CRM write paths unless explicitly required. Redact
secrets in outputs.

## Workspace Hygiene

Do not start non-trivial edits in a dirty checkout. Use an isolated git worktree
for feature work or when unrelated local changes exist; see
[`docs/engineering/repo-hygiene-runbook.md`](docs/engineering/repo-hygiene-runbook.md).

Git hooks and push gates run lint/static guardrails only. Run tests explicitly as local validation; see
[`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md).

## Validation

Use [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) and the nearest
override for verification. Run focused checks for touched areas. State skipped
checks.
