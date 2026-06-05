# Core Product Path Index

Fast lookup for the product simplification core path. Canonical command details
live in [`../LOCAL-DEVELOPMENT.md`](../LOCAL-DEVELOPMENT.md); design decisions
live in [`../designs/product-simplification-stage-0-decisions.md`](../designs/product-simplification-stage-0-decisions.md).

## Primary Proof

```bash
make core-up
make e2e-core-live
make core-down
```

`make e2e-core-live` runs the simplification core live golden set against local
Qdrant + BGE-M3. It uses deterministic synthetic fixtures and a fake LLM by
default so the product gate is stable and does not depend on provider budget.
`make core-up` starts only Qdrant and BGE-M3; use `make local-up` for the
broader native bot development runtime.

## Optional Real LLM Check

```bash
make e2e-core-live-real-llm
```

This target is opt-in and requires `LLM_BASE_URL`, `LLM_MODEL`, and either
`LLM_API_KEY` or `OPENAI_API_KEY`. Use it for manual confidence when real
provider credentials and budget are available.

## What The Core Gate Covers

| Area | Evidence |
|---|---|
| Fixture corpus and golden cases | [`../../tests/e2e_core/`](../../tests/e2e_core/) |
| Live local services | `Qdrant + BGE-M3` via `make core-up` |
| Assistant classification and retrieval | [`../../tests/e2e/test_core_live_ingest_answer.py`](../../tests/e2e/test_core_live_ingest_answer.py) |
| CRM/HITL safety | mock CRM in the core live E2E, no real CRM writes |
| Dependency failure behavior | core live E2E fallback case |

## Optional Surfaces

The simplified product gate intentionally does not require:

- Telegram or Telethon transport;
- Langfuse, OTel, or trace validation;
- voice/LiveKit;
- Mini App;
- k8s manifests;
- real CRM writes.

Use [`local-runtime.md`](local-runtime.md) for Telegram/native bot tasks and
[`observability-and-storage.md`](observability-and-storage.md) for Langfuse,
trace, Qdrant, Redis, and storage investigations.
