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

## Local Overrides

- [`telegram_bot/AGENTS.override.md`](telegram_bot/AGENTS.override.md)
- [`k8s/AGENTS.override.md`](k8s/AGENTS.override.md)
- [`src/ingestion/unified/AGENTS.override.md`](src/ingestion/unified/AGENTS.override.md)

## Safety

Prefer local/test environments. Do not access production, VPS, secrets, SSH,
cloud credentials, or real CRM write paths unless explicitly required. Redact
secrets in outputs.

## Validation

Use [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md) and the nearest
override for verification. Run focused checks for touched areas. State skipped
checks.
