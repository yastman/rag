# AGENTS.md

## Project At A Glance
- Production contextual RAG system for real-estate workflows.
- Main surfaces: `telegram_bot/`, `mini_app/`, apartment search, CRM automation, voice agent, unified ingestion, local services, and k3s deployment.
- Treat this repo as a multi-system product, not a single bot package.

## First Pass For New Sessions
- Read `README.md` for system overview and entry points.
- Read the nearest `AGENTS.override.md` before editing scoped subtrees.
- Start code discovery with `grepai` MCP tools; use `rg` only for exact text or path matching.
- Use `context-mode` MCP tools for large-output exploration, external docs, and large-file summarization.

## Instruction Priority
- The nearest `AGENTS.override.md` takes precedence for files in its scope.
- Root `Critical Invariants` and `Validation` rules still apply repo-wide unless a local override adds stricter requirements.
- `Engineering Heuristics` are defaults for ambiguous design choices; they do not justify violating explicit repo rules.

## Workflow Reality
- Do not assume `main` is the everyday integration branch.
- Before giving PR, merge, release, or cleanup advice, verify the current workflow using:
  - `git branch --show-current`
  - `gh pr list --state merged --limit 8 --json number,baseRefName,headRefName,mergedAt`
  - `.github/workflows/ci.yml`
  - `Makefile`
  - `scripts/git_hygiene.py`
  - `scripts/repo_cleanup.sh`
- Treat drift between merged PR history, docs, CI, and cleanup scripts as a real repo issue.

## MCP Priority And Fallbacks
- `grepai` is the default entry point for code discovery, semantic search, and call-graph tracing.
- In this repo, prefer `grepai` project-local mode by default: call `grepai_search` and `grepai_trace_*` without `workspace` unless a named workspace has been explicitly configured.
- Use `rg` instead of `grepai` only for exact strings, imports, symbols, or file path patterns.
- `context-mode` is the default entry point for high-output command exploration, external docs, and large-file analysis.
- Use direct shell or file reads when you need exact file contents for editing, the output is small, or MCP adds no value.
- If `grepai` is unavailable or returns weak results, fall back to `rg` plus direct file reads.
- If `context-mode` is unavailable, fall back to short shell commands and targeted file reads.

## SDK And Docs Lookup Order
- For SDK and framework decisions, use this order:
  - `docs/engineering/sdk-registry.md`
  - current code usage
  - official docs / Context7 for version-sensitive behavior
  - broad web search only as fallback
- Do not block work on missing MCP tools; use shell and direct file reads when MCP is unavailable.

## Issue Triage Workflow
- Before starting new work, classify it as `Quick execution`, `Plan needed`, or `Design first`.
- Use `docs/engineering/issue-triage.md` as the detailed operator playbook.
- Keep small local fixes in `Quick execution`.
- Route multi-file or runtime-sensitive work through `Plan needed`.
- Route structurally ambiguous or contract-changing work through `Design first`.
- `Plan needed` work routes through `@writing-plans`; `Design first` work routes through `@brainstorming` first.

## Task Routing
- `telegram_bot/`: handlers, dialogs, middlewares, agents, business services, orchestration.
- `telegram_bot/services/` and `src/retrieval/`: search, RAG, cache, reranking, retrieval behavior.
- `src/ingestion/unified/`: ingestion pipeline, chunking, manifests, Qdrant writes, resumability.
- `src/voice/` and `telegram_bot/graph/`: voice agent and LangGraph runtime flow.
- `mini_app/`: Telegram mini app backend and frontend.
- `services/`: supporting local service containers and helper APIs.
- `k8s/`, `compose*.yml`, `DOCKER.md`: deploy and environment orchestration.

## Runtime And Compose Contract
- Treat `compose*.yml`, `docker/**`, `services/**`, `mini_app/**`, `src/api/**`, `src/voice/**`, and ingestion runtime paths as runtime-impacting surfaces.
- For those changes, validate effective Compose config and service set, not only Python tests.
- Prefer:
  - `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services`
  - `COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services`
  - `make verify-compose-images`

## Working Rules
- Use `mcp__grepai__grepai_search` first for "where does this live?" and `mcp__grepai__grepai_trace_*` before non-trivial refactors.
- Use `mcp__context-mode__ctx_batch_execute` for multi-command repo exploration.
- Use `mcp__context-mode__ctx_fetch_and_index` plus `mcp__context-mode__ctx_search` for web docs and external pages.
- Before adding a new SDK, API client, or dependency, check `docs/engineering/sdk-registry.md`.

## Engineering Heuristics
- Prefer the simplest change that solves the current task and keeps the local blast radius small.
- Do not add abstractions, extension points, wrappers, or interfaces before a real second use case exists.
- Apply DRY to shared knowledge, rules, validations, and contracts; do not merge code paths that change for different reasons.
- Extract reuse only after repetition is proven and the shared shape is stable.
- Prefer composition and focused modules over inheritance-heavy designs.
- Use SOLID ideas only when they improve testability, replaceability, or change safety for the current code.
- Favor small, reviewable PRs and incremental code-health improvements.
- Refactor when it makes the current change simpler, safer, or easier to test.

## Critical Invariants
- Preserve service boundaries: transport-layer Telegram code should not absorb retrieval or domain logic.
- Keep apartment search cheap-first: prefer deterministic parsing and filters before adding LLM work.
- Preserve LangGraph state contracts, checkpoint assumptions, and routing shapes.
- Preserve ingestion determinism and resumability; do not casually change manifest identity, hashing, or collection semantics.
- Do not remove tracing, scoring, or observability hooks without a clear replacement.
- Treat mini app parity as part of the release surface, not as an optional frontend.

## Validation
- Run fresh verification before claiming completion.
- Base checks for most code changes:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- Use stricter checks from local overrides when working in their scope.
- If you skip a relevant check, state that explicitly.

## Fast Start Commands
- `uv sync`
- `make local-up`
- `make run-bot`
- `make check`
- `make test-unit`
- `make ingest-unified-status`

## Local Overrides
- `telegram_bot/AGENTS.override.md`
- `k8s/AGENTS.override.md`
- `src/ingestion/unified/AGENTS.override.md`

## References
- `README.md`
- `docs/engineering/sdk-registry.md`
- `DOCKER.md`
