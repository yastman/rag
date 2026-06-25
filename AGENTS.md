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

**Heads-up — Langfuse is half-removed (split-brain).** Probe/ingestion paths are no-op'd, but
live `src/` consumers and a legacy `telegram_bot/agents/rag_pipeline.py` (a duplicate of the
spine `rag_pipeline`, still carrying `@observe`) remain. Don't assume Langfuse is gone — confirm
the live path with `find_callers` before editing. Finishing removal + consolidating the
duplicate is tracked in codeindexer cards (epic-2983).

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
- Don't start non-trivial edits in a dirty checkout — use an isolated git worktree. See
  [`docs/engineering/repo-hygiene-runbook.md`](docs/engineering/repo-hygiene-runbook.md).
- Use additional skills only when the task matches their trigger; don't cascade into unrelated
  skills on your own.

## Canonical docs

- Overview / navigation: [`README.md`](README.md) · [`docs/README.md`](docs/README.md) · [`docs/indexes/`](docs/indexes/)
- Runtime, Compose, ports, env, deploy: [`DOCKER.md`](DOCKER.md)
- Local setup & validation: [`docs/LOCAL-DEVELOPMENT.md`](docs/LOCAL-DEVELOPMENT.md)
- Operational investigations: [`docs/runbooks/README.md`](docs/runbooks/README.md)
- Tests: [`docs/engineering/test-writing-guide.md`](docs/engineering/test-writing-guide.md) · Triage: [`docs/engineering/issue-triage.md`](docs/engineering/issue-triage.md)
- SDK lookup: [`docs/engineering/sdk-registry.md`](docs/engineering/sdk-registry.md)
- Swarm/PR process: [`docs/engineering/orchestrator-playbook.md`](docs/engineering/orchestrator-playbook.md) · [`docs/engineering/gh-pr-review.md`](docs/engineering/gh-pr-review.md)

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
