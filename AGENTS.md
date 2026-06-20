# AGENTS.md

## Purpose

This file is the repo gateway for agents. Keep it short. Do not duplicate
runbooks, Docker contracts, test policy, subsystem ownership, docs maintenance
rules, or worker-specific workflows here.

## What This Is

A single-process **Python monolith**: one entry point (a Telegram bot,
`telegram_bot/`), one RAG pipeline (`src/runtime/pipeline/`). It answers from a
private corpus (Qdrant + BGE-M3 hybrid retrieval) and prepares CRM actions
behind human confirmation. It is **not** a multi-surface "AI platform" — voice /
Mini App / HTTP-API / the `telegram_bot/graph/` LangGraph layer are removed or
inert legacy under active cleanup. Don't reintroduce platform/adapter
abstractions that have no live caller.

**Direction (where this is going):** converge ON exactly this shape — one
process, one Telegram entry point, one RAG pipeline. Every change should move
toward fewer surfaces, not more: delete leftover platform/adapter/duplicate
layers rather than grow new ones (legacy `telegram_bot/graph/`, the parallel
`src/` ↔ `telegram_bot/` trees, dead provider abstractions). When a change adds
a new entry point, adapter, or abstraction layer, that is the signal to stop and
question it.

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

## Engineering Principle

Default to the laziest correct change: before writing code, stop at the first
rung that holds — does it need to exist (YAGNI) → stdlib → native platform
feature → installed dependency → one line → only then minimal new code.
Deletion over addition, fewest files, no unrequested abstractions. Never cut
validation, error handling, security, or accessibility. Mark deliberate
shortcuts with a `ponytail:` comment naming the ceiling and upgrade path.
Source: [`ponytail`](https://github.com/DietrichGebert/ponytail).

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
- Codex Web worker prompt:
  [`docs/engineering/codex-web-prompt.md`](docs/engineering/codex-web-prompt.md)
- PR review / gatekeeper:
  [`docs/engineering/gh-pr-review.md`](docs/engineering/gh-pr-review.md)
- Orchestrator playbook:
  [`docs/engineering/orchestrator-playbook.md`](docs/engineering/orchestrator-playbook.md)
- Orchestrator finish, merge, and cleanup protocol:
  [`docs/engineering/orchestrator-finish-protocol.md`](docs/engineering/orchestrator-finish-protocol.md)
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

Do not duplicate the plan here. Follow the plan order: Stage 0 docs first, then
test/logging infrastructure, then one golden live E2E, then runtime
simplification.

## Local Overrides

- [`telegram_bot/AGENTS.override.md`](telegram_bot/AGENTS.override.md)
- [`src/ingestion/unified/AGENTS.override.md`](src/ingestion/unified/AGENTS.override.md)
- [`scripts/AGENTS.override.md`](scripts/AGENTS.override.md)
- [`services/AGENTS.override.md`](services/AGENTS.override.md)
- [`services/bge-m3-api/AGENTS.override.md`](services/bge-m3-api/AGENTS.override.md)
- [`services/docling/AGENTS.override.md`](services/docling/AGENTS.override.md)

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

## Test Policy

GitHub required CI = hygiene/static only (Secret Scan, Semgrep, Lint, Lockfile Check, Compose Config).
Python tests = local/manual or workflow_dispatch-only.

| Gate | Scope | When |
|---|---|---|
| `make test-core` | monolith core only (91 tests, ~8s) | core changes, preferred first |
| `make test` | broad fast gate (unit + graph paths) | adapter/service changes |
| `make test-contract` | static contract tests | contract changes |
| `make test-full` | heavy full gate | manual pre-merge only |

Core changes should prefer `make test-core` first.
Adapter/service changes should run `make test-core` + `make test`.

Git hooks and push gates run lint/static guardrails only. Run tests explicitly
as local validation; see [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md).
