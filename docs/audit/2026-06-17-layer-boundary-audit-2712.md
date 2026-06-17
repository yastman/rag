# Layer Boundary Audit — Issue #2712

**Date:** 2026-06-17
**Auditor:** w-2712 (automated)
**Scope:** Modularity and layer-boundary violations across `src/`, `telegram_bot/`, `archive/`, and `services/`

---

## Intended Layer Map

| Layer | Path | Role |
|---|---|---|
| `src/core` | `src/core/` | Stable assistant entrypoint, typed contracts (`AssistantRequest`, `AssistantResult`, `CoreDependencies`). No Telegram/FastAPI/Langfuse dependencies. |
| `src/runtime` | `src/runtime/` | RAG pipeline, graph nodes, generation, grounding, retrieval orchestration. May depend on `src/adapters`, `src/services`, `src/config`. |
| `src/adapters` | `src/adapters/` | Adapter interfaces and provider implementations (LLM, embeddings). Low-level; must not import `src/runtime`. |
| `src/services` | `src/services/` | Low-level service clients (BGE-M3, retry, vectorizers, handoff state). Must not import `src/runtime`. |
| `src/retrieval` | `src/retrieval/` | Vector search engines, reranker, topic classifier. May depend on `src/services`, `src/config`. |
| `src/ingestion` | `src/ingestion/` | Ingestion pipeline (CocoIndex, Docling, chunker, indexer). |
| `src/config` | `src/config/` | Shared configuration, constants, settings. No application imports. |
| `src/observability` | `src/observability/` | Langfuse client, score writing, safe payloads. Optional; must not block core path. |
| `telegram_bot` | `telegram_bot/` | Telegram adapter only. May import from `src.*`. Must not be imported by `src.*`. |
| `services/*` | `services/bge-m3-api/`, `services/docling/` | Separate containerized service processes. Isolated `pyproject.toml`; no cross-imports. |
| `archive/*` | `archive/` | Historical code. Must not be imported by live code (`src/`, `telegram_bot/`, `scripts/`). |

---

## Cross-Layer Edge Table

| # | Source layer | Target layer | Import/call | Why suspicious | Decision | Action |
|---|---|---|---|---|---|---|
| 1 | `telegram_bot/agents/rag_tool.py` | `src.runtime.graph.nodes.classify` | `classify_query` | Agent tool bypasses `src.core` API; imports runtime graph node internals directly | **Violation** | Child issue: route via `src.core` or expose via `src.runtime.pipeline` public API |
| 2 | `telegram_bot/agents/rag_tool.py` | `src.runtime.graph.nodes.guard` | `guard_node` | Same as #1 — imports runtime graph node internals | **Violation** | Same child issue as #1 |
| 3 | `telegram_bot/agents/history_graph/nodes.py` | `src.runtime.graph.nodes.guard` | `detect_injection` | Agent history graph node reaches into runtime graph node internals | **Violation** | Child issue: expose `detect_injection` via `src.runtime.services` public API |
| 4 | `telegram_bot/bot.py` (line 2151) | `src.runtime.graph.nodes.guard` | `_BLOCKED_RESPONSE` (private symbol) | Bot directly imports a private symbol from a runtime graph node | **Violation** | Child issue: expose a public constant or drop the reference |
| 5 | `telegram_bot/bot.py` (line 2152) | `src.runtime.services.rag_core` | `CACHEABLE_QUERY_TYPES` | Bot imports a service-layer constant directly; should be accessible via `src.core` contracts or `src.runtime.pipeline` result | **Transitional** | Remove in next bot.py decomp pass; expose via pipeline contract if needed |
| 6 | `telegram_bot/agents/rag_tool.py`, `telegram_bot/agents/rag_pipeline.py`, `telegram_bot/pipelines/client.py`, `telegram_bot/bot.py` (line 831) | `src.runtime.pipeline.rag` | `rag_pipeline` | Telegram calls runtime pipeline directly, bypassing `src.core.assistant.run_assistant_request` entrypoint | **Transitional** | Already tracked by monolith-core migration plan; `telegram_bot/assistant_core_adapter.py` is the target shim. Keep until `bot.py` decomp lands. |
| 7 | `telegram_bot/graph/nodes/classify.py`, `telegram_bot/graph/nodes/guard.py`, `telegram_bot/graph/nodes/rewrite.py`, `telegram_bot/graph/nodes/transcribe.py`, `telegram_bot/graph/edges.py`, `telegram_bot/graph/config.py`, `telegram_bot/graph/state.py`, `telegram_bot/graph/context.py`, `telegram_bot/graph/graph.py` | `src.runtime.graph.*` | Various graph-compat re-exports | `telegram_bot/graph/` is a compatibility facade shim over `src.runtime.graph`; thin re-exports are intentional | **Valid** | No action; documented in `src/runtime/__init__.py`. Shims tracked for removal in #1265. |
| 8 | `telegram_bot/integrations/cache.py`, `telegram_bot/integrations/embeddings.py`, `telegram_bot/integrations/polling_lock.py`, `telegram_bot/integrations/prompt_manager.py`, `telegram_bot/integrations/prompt_templates.py` | `src.runtime.integrations.*` | Thin re-export shims | Same shim pattern as #7 | **Valid** | No action; documented in migration plan. |
| 9 | `telegram_bot/services/` (many files) | `src.runtime.services.*`, `src.services.*` | Thin re-export shims | `telegram_bot/services/` modules such as `rag_core.py`, `colbert_reranker.py`, `query_filter_signal.py`, etc. are thin re-exports pointing to canonical `src.runtime.services.*` home | **Valid** | No action; documented migration pattern. |
| 10 | `src/services/content_loader.py` | `telegram_bot/config/` (filesystem path) | `Path(...) / "telegram_bot" / "config"` | A shared `src/` module hard-codes a path into the Telegram-layer config directory | **Violation** | Child issue: move `services.yaml` / `mini_app.yaml` out of `telegram_bot/config/` into `src/config/` or a domain-neutral location |
| 11 | `archive/voice/voice_agent.py` | `telegram_bot.agents.agent`, `telegram_bot.agents.rag_tool` | Import of live `telegram_bot` code from archive | Archive code importing live code; creates a hidden dependency chain | **Violation** (low risk — archive not imported by live code) | Child issue: update `archive/voice/voice_agent.py` to import from `src.core` or document as intentionally broken |
| 12 | `archive/voice/agent.py`, `archive/voice/transcript_store.py` | `src.voice.*` | Import of `src.voice` namespace that no longer exists | Stale imports referencing a deleted `src/voice/` module | **Violation** (import-time error if archive is ever imported) | Child issue: update archive imports or mark file as non-importable |
| 13 | `archive/scripts/benchmark/contextualized_ab.py`, `archive/scripts/benchmark/quantization_ab.py`, `archive/scripts/index_test_properties.py` | `telegram_bot.services.*`, `telegram_bot.config` | Archive scripts import live `telegram_bot` code | Archive importing live code; acceptable if scripts are truly dead | **Transitional** | Audit these scripts; remove or isolate from CI |
| 14 | `telegram_bot/pipelines/client.py` | `telegram_bot.services.generate_response`, `telegram_bot.services.history_service`, `telegram_bot.services.telegram_formatting`, `telegram_bot.services.types` | `telegram_bot/pipelines/` imports deep `telegram_bot/services/` business logic | `telegram_bot/pipelines/` is nominally a pipeline orchestrator layer but holds substantial business logic via imports from domain services | **Transitional** | This will be resolved by the bot.py decomposition; `client.py` is an intermediate step |
| 15 | `src/services/handoff_state.py` | _(none)_ | Owns manager handoff state machine and lead ID | A state machine with business concepts (`mode: bot/human_waiting/human`, `lead_id`) lives in a shared `src/services/` layer rather than a domain layer | **Transitional** | Move to `telegram_bot/` domain layer or `src/runtime/services/` when HITL is stabilised |
| 16 | `src/models/apartment.py` | _(none)_ | Domain-specific apartment data model (views, tags, room types) in shared `src/models/` | Domain model tightly coupled to real-estate domain sits in shared layer | **Transitional** | Acceptable for current domain; move to `telegram_bot/models/` if `src/` is made domain-agnostic |
| 17 | `src/scoring.py` (root-level) | _(none)_ | Langfuse score-writing utilities at repo root of `src/` | Module lives at `src/` root instead of under `src/observability/` | **Transitional** | Move to `src/observability/scoring.py` in a future cleanup; `telegram_bot/scoring.py` is already a shim |
| 18 | `src/observability_payloads.py`, `src/observability_bootstrap.py`, `src/phone_utils.py` (root-level) | _(none)_ | Shared utilities placed at `src/` root instead of in a sub-package | Minor structural drift; modules are shims pointing to their canonical homes | **Transitional** | Shims are backward-compat bridges; track removal after `telegram_bot/` shims are cleaned up |

---

## Summary: Violations Requiring Child Issues

| Priority | Issue | Violation (#) |
|---|---|---|
| High | `telegram_bot/agents/rag_tool.py` bypasses `src.core`, imports runtime graph node internals (`classify_query`, `guard_node`) | #1, #2 |
| High | `telegram_bot/agents/history_graph/nodes.py` imports `detect_injection` from runtime graph node internals | #3 |
| High | `telegram_bot/bot.py` imports private `_BLOCKED_RESPONSE` symbol from `src.runtime.graph.nodes.guard` | #4 |
| Medium | `src/services/content_loader.py` hard-codes path into `telegram_bot/config/` directory | #10 |
| Low | `archive/voice/voice_agent.py` imports live `telegram_bot` code | #11 |
| Low | `archive/voice/agent.py` and `archive/voice/transcript_store.py` import deleted `src.voice.*` namespace | #12 |

## Summary: Transitional Edges (Documented, Planned for Removal)

| # | Edge | Removal plan |
|---|---|---|
| 5 | `telegram_bot/bot.py` → `CACHEABLE_QUERY_TYPES` | Next `bot.py` decomposition pass |
| 6 | `telegram_bot/*` → `src.runtime.pipeline.rag` directly | `bot.py` → `assistant_core_adapter.py` migration (ongoing) |
| 13 | Archive benchmark scripts → live `telegram_bot` code | Audit and remove from active paths |
| 14 | `telegram_bot/pipelines/client.py` → deep service business logic | `bot.py` decomposition |
| 15 | `src/services/handoff_state.py` owns HITL business logic | Move after HITL stabilises |
| 16 | `src/models/apartment.py` in shared layer | Move to domain layer when `src/` is made domain-agnostic |
| 17, 18 | Root-level shims in `src/` | Clean up after `telegram_bot/` shims removed |

## Summary: Valid / Intentional Edges

| # | Edge | Rationale |
|---|---|---|
| 7 | `telegram_bot/graph/*` → `src.runtime.graph.*` | Documented compat shims; tracked in #1265 |
| 8 | `telegram_bot/integrations/*` → `src.runtime.integrations.*` | Documented compat shims |
| 9 | `telegram_bot/services/*` → `src.runtime.services.*` | Documented compat shims (migration in progress) |

---

## Existing Contract Enforcement

These violations are already protected by ratchet tests:

- `tests/contract/test_layering_no_telegram_bot_imports_contract.py` — blocks new `src/` files importing `telegram_bot`; ratchet is currently empty (`{}`)
- `tests/contract/test_runtime_no_telegram_bot_coupling_contract.py` — blocks new `telegram_bot.*` string literals in `src/core` and `src/runtime`; ratchet is currently empty (`{}`)
- `tests/contract/test_architecture_layer_law_contract.py` — blocks `src/services` and `src/providers` from importing `src.runtime`; enforces `DEFAULT_FACTORY_SPEC` is runtime-owned

---

*Generated by audit worker w-2712 for issue #2712.*
