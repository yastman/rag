# telegram_bot/graph/

> **Legacy compatibility façade — not an active public API surface** (ARCH-16 decision, #2697).

Retained so the voice path (`telegram_bot/bot.py`) and the `PYTEST_LEGACY_GRAPH_PATHS` test
lane keep working. The **canonical text-RAG path** is `src/core/assistant.py` +
`src/runtime/pipeline/assistant_pipeline.py`. **Do not add new callers of these exports** —
route new work through the assistant-core path.

## Files

| Path | Role |
|------|------|
| [`__init__.py`](./__init__.py) | Re-exports `build_graph`, `GraphConfig`, `RAGState`, `make_initial_state` from `src.runtime.graph.*` + `pipelines.graph_compat` |
| [`state.py`](./state.py) | Thin state shim |
| [`middleware/`](./middleware/) | SDK-native middleware for the `create_agent` migration (umbrella #1535): `ClassifyMiddleware`, `GuardMiddleware`, `SemanticCacheMiddleware` |
| [`nodes/`](./nodes/) · [`tools/`](./tools/) | Legacy StateGraph nodes/tools (kept in place; not extended) |

## Boundaries

- Graph nodes/config themselves now live in [`../../src/runtime/graph/`](../../src/runtime/graph/);
  this package only re-exports them for backward compatibility.
- New pipeline behaviour belongs in `src/runtime/`, not here.

## See Also

- [`../../src/runtime/README.md`](../../src/runtime/README.md) — the real engine
- [`../pipelines/README.md`](../pipelines/README.md) — the `graph_compat` façade
