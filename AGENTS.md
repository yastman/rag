# AGENTS.md

Repo gateway for agents. First thing to read in a session. Keep it short — link to
canonical docs, don't copy them here.

## What this is

A self-hostable RAG question-answer chatbot. User asks in natural language → retrieve
grounded context from documents in Qdrant → an LLM returns a cited answer. Telegram is
the live adapter; the live domain is real-estate/apartments, and the domain layer
(prompts, tools, constants) is replaceable. One Python process — in-process function
calls, not microservices.

The live bot is a RAG Q&A core (💬 Ask a question) plus a feature menu (apartment search,
viewing booking, manager handoff/HITL, bookmarks, services, demo). Direction: harden to
senior-grade while keeping every feature — epic **#2983** (remove cruft, decompose
`bot.py` into per-feature handlers, freeze entry contracts; no over-engineering).

## The spine (the one flow worth memorising)

```
run_assistant_request        src/core/assistant.py
  → run_assistant_pipeline   src/runtime/pipeline/assistant_pipeline.py
    → classify_query
    → rag_pipeline           src/runtime/pipeline/rag.py   (cache → hybrid search → grade → rerank → optional rewrite loop)
    → generate_answer        src/runtime/generation/service.py
```

Layering: `telegram_bot/` = adapter · `src/core/` = public boundary (Protocol-based DI via
`contracts.py`) · `src/runtime/` = engine.

**Langfuse SDK fully removed** (#2844, #2969) — no `langfuse` dependency, no `from langfuse` imports anywhere. The `@observe` decorators that remain across `src/` and `telegram_bot/` are now local **no-op shims** (`src.observability` / `telegram_bot.observability`), not tracing. Observability is stdlib logging only.

## Navigate code (index-first)

This repo is indexed by the **codeindexer** + **codegraph** MCP servers. Use them instead of
`grep`/`find`/`cat`/`sed` — start with `search_code` / `find_*`, resolve names via
`projects(action="list", query=...)`, widen a hit with `read_chunk` / `read_file_range`.
Depth, tool map, cost limits and footguns live in the global skill
**`using-codeindex-codegraph`** (loaded on demand). A standalone `grep`/`rg`/`find` on an
indexed path is blocked by a hook — append `# nogrep` to bypass.

## Planning & state (in codeindexer, not GitHub)

Roadmap, phases, and todo/decision cards for this project live in the **codeindexer** memory
store — not GitHub issues. Start a session with `briefing(project="rag-fresh")` for open cards +
active phases + gotchas; use `roadmap` (phases) and `memory_cards` (todos/decisions) for what's
next (currently ~13 phases / 115 cards). Epic labels like **#2983** are card tags there. Record
non-obvious fixes with `solutions(add)`.

## Verify before claiming done

CI runs hygiene/static only (Secret Scan, Semgrep, Lint, Lockfile, Compose Config). Python
tests are local/manual — run the right gate yourself:

| Gate | Scope | When |
|---|---|---|
| `make test-core` | monolith core (91 tests, ~8s) | core changes — run first |
| `make test` | unit + graph paths | adapter/service changes |
| `make test-contract` | static contract tests | contract changes |
| `make test-full` | all tiers (heavy) | manual pre-merge only |

Core changes → `make test-core` first. Adapter/service changes → `make test-core` + `make test`.
Subsystem overrides may pin tighter commands — see the nearest `AGENTS.override.md`.

## Safety & hygiene

- Prefer local/test environments. Do **not** touch production, VPS, secrets, SSH, cloud
  credentials, or real CRM write paths unless the task explicitly requires it. Redact secrets.
- Don't start non-trivial edits in a dirty checkout — use an isolated git worktree.
- Use additional skills only when the task matches their trigger; don't cascade into unrelated
  skills on your own.

## Canonical docs

- Overview / navigation: [`README.md`](README.md)
- Runtime, Compose, ports, env, deploy: [`DOCKER.md`](DOCKER.md)
- Local setup & validation: [`README.md`](README.md) (Quick Start section)
- Tests: [`tests/README.md`](tests/README.md)
- Swarm/PR/triage process lives in the Kiro skills (`roadmap-orchestrator`, `gh-pr-review`), not in-repo docs.

## Local overrides

Scoped rules live next to the code — read the nearest one before editing that area:

- [`telegram_bot/AGENTS.override.md`](telegram_bot/AGENTS.override.md)
- [`src/ingestion/unified/AGENTS.override.md`](src/ingestion/unified/AGENTS.override.md)
- [`scripts/AGENTS.override.md`](scripts/AGENTS.override.md)
- [`services/AGENTS.override.md`](services/AGENTS.override.md)
- [`services/bge-m3-api/AGENTS.override.md`](services/bge-m3-api/AGENTS.override.md)
- [`services/docling/AGENTS.override.md`](services/docling/AGENTS.override.md)

## Priority

Nearest `AGENTS.override.md` > this file > linked canonical docs.
