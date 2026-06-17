# graph/

## Status

**Legacy compatibility layer.** The Telegram text path is converged on the
assistant core (`src/core/` + `src/runtime/pipeline/`). This folder is kept
only as a compatibility façade for the voice path and for the optional
`test-legacy-graph-extra` test lane.

- `graph.py` / `build_graph` — façade used by the **voice path** only
- `state.py` / `config.py` / `edges.py` / `context.py` — thin re-export shims
- `nodes/`, `tools/`, `middleware/` — legacy; used only by `test-legacy-graph-extra`

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
