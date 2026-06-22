# AGENTS.md

## Purpose

This file is the repo gateway for agents. Keep it short. Do not duplicate
runbooks, Docker contracts, test policy, subsystem ownership, docs maintenance
rules, or worker-specific workflows here.

## What This Project Is

A self-hostable RAG question-answer chatbot. Users ask in natural language →
the system retrieves grounded context from documents in Qdrant → an LLM
produces a cited answer. Telegram is the live adapter. The current live domain
is real-estate/apartments; the domain layer (prompts, tools, constants) is
replaceable.

Single logical entrypoint and spine:
`run_assistant_request` (`src/core/assistant.py`) →
`run_assistant_pipeline` (`src/runtime/pipeline/assistant_pipeline.py`) →
`classify_query` → `rag_pipeline` (`src/runtime/pipeline/rag.py`, retrieval
engine: cache → hybrid Qdrant search → grade → rerank → optional
query-rewrite loop) → `generate_answer` (`src/runtime/generation/service.py`).

Layering: `telegram_bot/` = adapter; `src/core/` = public boundary
(Protocol-based DI via `contracts.py`); `src/runtime/` = engine.
One Python process — in-process function calls, not microservices.

The live bot is a real-estate assistant: a RAG Q&A core (💬 Ask a question) plus a
feature menu (apartment search, viewing booking, manager handoff/HITL, bookmarks,
services, demo). The domain layer is replaceable. **Direction:** harden to
senior-grade while keeping every feature — see epic #2983 (remove cruft, decompose
`bot.py` into per-feature handlers, freeze entry contracts; no over-engineering).

Note: the Mini App deeplink handler is an archived/reference surface still present in the file tree and being trimmed. Do not assume it is an active production capability. Voice input is active via `telegram_bot/dialogs/` (catalog and demo dialogs).

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

## Code Search

This repo is indexed by the **codeindexer MCP** (GPU-served in WSL). Prefer it
over `grep` / `rg` / `find` / `cat` / `sed`: start lookups with `search_code` or a
`find_*` tool, resolve the name via `projects(action="list", query=...)`, and widen
a hit with `read_chunk` / `read_file_range` (not shell). Full reflexes live in the
always-on steering rule `codeindexer.md` and the
[`using-codeindex-codegraph`](.kiro/skills/using-codeindex-codegraph/SKILL.md) skill.

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

## Product Simplification (Completed Sprint 2026-06-22)

Langfuse was fully removed (no shims, no `@observe` decorators, no residue).
Module splits completed: `generate_response.py`, `funnel.py`, `filter_dialog.py`,
`catalog.py`, `preflight.py` — all split into packages. New runtime sub-packages:
`src/runtime/qdrant/`, `src/runtime/cache/`, `src/runtime/generation/` (expanded).
Observability is through structured logs and Loki/Promtail.

For ongoing hardening work, see epic #2983.

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
