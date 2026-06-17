# graph/

## Status — ARCH-16 decision (#2697)

**Kept as a compatibility façade; not an active competing text runtime.**

The Telegram text path converged on the assistant core
(`src/core/` + `src/runtime/pipeline/`) in ARCH-16. This folder is retained
for two explicit purposes only:

1. **Voice path**: `telegram_bot/bot.py` calls `build_graph()` to build the
   voice-capable graph object. All graph logic ultimately delegates to
   `run_assistant_pipeline()` in `src/runtime/pipeline/`.
2. **Optional test lane**: `PYTEST_LEGACY_GRAPH_PATHS` covers
   `tests/unit/graph/` for tests that exercise these shims. These tests are
   excluded from the default `make test-unit` / `make test-core` gates.

Do **not** add new callers of the exports here. New text-RAG or tool work
belongs in `src/core/` or `src/runtime/`.

- `graph.py` / `build_graph` — façade used by the **voice path** only; wraps `run_assistant_pipeline()`
- `state.py` / `config.py` / `edges.py` / `context.py` — thin re-export shims
- `nodes/`, `tools/`, `middleware/` — legacy; used only by `PYTEST_LEGACY_GRAPH_PATHS`

## Previous Entrypoints

| File | Role |
|------|------|
| [`graph.py`](./graph.py) `build_graph()` | Voice-path compatibility façade over the imperative pipeline |
| [`state.py`](./state.py) `RAGState` | Re-export shim pointing to `src.runtime.graph.state` |
| [`config.py`](./config.py) `GraphConfig` | Re-export shim pointing to `src.runtime.graph.config` |

## See Also

- [`src/core/assistant.py`](../../src/core/assistant.py) — text-path entrypoint
- [`../assistant_core_adapter.py`](../assistant_core_adapter.py) — Telegram transport adapter
- [`../../docs/PIPELINE_OVERVIEW.md`](../../docs/PIPELINE_OVERVIEW.md) — current pipeline flows
