# Architecture Law

This document defines the dependency rules for the Python monolith.
Every code PR must respect these rules. Contract tests enforce them in CI.

---

## Layer Diagram

```text
External adapters (telegram_bot, archive/api, archive/voice, archive/mini_app)
        │
        ▼
    src.core (public contract + entrypoint)
        │
        ▼
    src.runtime (shared runtime kernel)
        │
        ▼
    Providers / Clients / Services
    (src/services, src/retrieval, src/ingestion, external SDKs)
```

---

## Dependency Rules

### Allowed

```text
telegram_bot  → src.core
archive/api   → src.core (archived optional surface)
archive/voice → src.core (or optional API adapter; archived)
archive/mini_app → src.core (or optional API adapter; archived)
src.core      → src.runtime
src.runtime   → src/services, src/retrieval, external SDKs
```

### Forbidden (final target)

```text
src.core      ✗ telegram_bot
src.runtime   ✗ telegram_bot
src.retrieval ✗ telegram_bot
providers     ✗ src.runtime
```

### Current migration debt

`tests/data/known_runtime_telegram_bot_couplings.json` is now the target state
`{}`: `src.core` and `src.runtime` must not contain dynamic `telegram_bot.*`
string coupling. Existing adapter-to-runtime imports are tracked separately as
incremental migration debt; new adapter behavior should enter through
`src.core`.
Track: #2478, #2486, #2489.

---

## Layer Responsibilities

### External Adapters

```text
telegram_bot/  — Telegram UI, handlers, dialogs, keyboards, middlewares (active)
archive/api/   — Optional HTTP API surface (archived)
archive/voice/ — Optional voice adapter (archived)
archive/mini_app/ — Optional Mini App surface (archived)
```

Adapters **must not** own product RAG/generation logic.
Adapters call `src.core.run_assistant_request()` and render the result.

### src.core

```text
Public contract: AssistantRequest, AssistantResult, UserContext, CrmAction
Entrypoint: run_assistant_request()
```

`src.core` is the only public seam. It owns nothing except the contract and
the entrypoint shell that delegates to `src.runtime`.

### src.runtime

```text
pipeline/     — assistant_pipeline (procedural core, ADR-0019)
generation/   — core LLM generation (no Telegram send)
grounding/    — safety policy, fallback, no-data handling
services/     — Qdrant, cache, metrics, query preprocessing
integrations/ — cache layers, embeddings wrappers
llm/          — LiteLLM Router (canonical LLM path)
```

`src.runtime` owns the shared runtime kernel. It **must not** import from
`telegram_bot.*`.

### Providers / Clients / Services

```text
src/services/     — BGE-M3 client, Kommo CRM client
src/retrieval/    — Search strategies, topic classifier
src/ingestion/    — Batch/offline ingestion (Docling, CocoIndex, Qdrant writer)
```

These are implementation details. They must not call back into `src.runtime`.

---

## Specific Rules

1. **CRM writes require HITL.** No direct CRM writes without human confirmation.
2. **Core generation does not accept Telegram `message`.** Generation returns
   data; the adapter sends messages.
3. **Observability is optional.** Product JSON logs are required. Langfuse,
   OTel, Sentry, Prometheus are optional diagnostic layers. Core/runtime code
   emits telemetry through an injected `CoreDependencies.telemetry` listener or
   standard Python logging fallback, not through adapter-global loggers.
4. **`create_agent` is adapter-only.** Per ADR-0019, `create_agent` is not the
   owner of the core text RAG path. It remains useful for Telegram/voice
   adapter conversational shell behavior.
5. **No dynamic `telegram_bot.*` imports in `src.core` or `src.runtime`.**
   Track: `tests/data/known_runtime_telegram_bot_couplings.json`.
6. **Runtime graph defaults stay runtime-owned.** Adapter-specific graph assembly
   must be selected explicitly with `RAG_GRAPH_FACTORY=module:attribute`;
   `src.runtime.graph.builder.DEFAULT_FACTORY_SPEC` must not point at
   `telegram_bot`.
7. **Core dependencies are protocol typed.** `CoreDependencies` fields describe
   cache, embedding, Qdrant, reranker, LLM, CRM, and telemetry contracts via
   structural protocols so adapters do not leak concrete client ownership into
   the SDK boundary.

---

## Enforcement

### Contract tests

```text
tests/contract/test_runtime_no_telegram_bot_coupling_contract.py
tests/contract/test_layering_no_telegram_bot_imports_contract.py
tests/contract/test_langfuse_optional_core_contract.py
tests/contract/test_service_dependency_markers_contract.py
tests/contract/test_architecture_layer_law_contract.py
```

### Target

```text
tests/data/known_runtime_telegram_bot_couplings.json == {}
```

When that file is empty and the core E2E path still passes, the monolith
ownership boundary is clean.

---

## References

- ADR-0019: `docs/adr/0019-core-text-path-procedural-runtime.md`
- ADR-0015: `docs/adr/0015-sdk-native-baseline.md`
- Monolith plan: `docs/designs/monolith-core-plan.md`
- Runtime coupling: `tests/data/known_runtime_telegram_bot_couplings.json`
- Issue: #2477
