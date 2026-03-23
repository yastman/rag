# AGENTS.md

## Project At A Glance
- Production contextual RAG system for real-estate workflows.
- Main surfaces: `telegram_bot/`, apartment search, CRM automation, voice agent, unified ingestion, local services, and k3s deployment.
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

## MCP Priority And Fallbacks
- `grepai` is the default entry point for code discovery, semantic search, and call-graph tracing.
- In this repo, prefer `grepai` project-local mode by default: call `grepai_search` and `grepai_trace_*` without `workspace` unless a named workspace has been explicitly configured.
- Use `rg` instead of `grepai` only for exact strings, imports, symbols, or file path patterns.
- `context-mode` is the default entry point for high-output command exploration, external docs, and large-file analysis.
- Use direct shell or file reads when you need exact file contents for editing, the output is small, or MCP adds no value.
- If `grepai` is unavailable or returns weak results, fall back to `rg` plus direct file reads.
- If `context-mode` is unavailable, fall back to short shell commands and targeted file reads.

## Task Routing
- `telegram_bot/`: handlers, dialogs, middlewares, agents, business services, orchestration.
- `telegram_bot/services/` and `src/retrieval/`: search, RAG, cache, reranking, retrieval behavior.
- `src/ingestion/unified/`: ingestion pipeline, chunking, manifests, Qdrant writes, resumability.
- `src/voice/` and `telegram_bot/graph/`: voice agent and LangGraph runtime flow.
- `mini_app/`: Telegram mini app backend and frontend.
- `services/`: supporting local service containers and helper APIs.
- `k8s/`, `compose*.yml`, `DOCKER.md`: deploy and environment orchestration.

## Working Rules
- Use `mcp__grepai__grepai_search` first for "where does this live?" and `mcp__grepai__grepai_trace_*` before non-trivial refactors.
- Use `mcp__context-mode__ctx_batch_execute` for multi-command repo exploration.
- Use `mcp__context-mode__ctx_fetch_and_index` plus `mcp__context-mode__ctx_search` for web docs and external pages.
- Before adding a new SDK, API client, or dependency, check `.claude/rules/sdk-registry.md`.

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
- `.claude/rules/sdk-registry.md`
- `DOCKER.md`
