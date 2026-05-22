# graph/

## Purpose

LangGraph runtime for the RAG pipeline: node definitions, state contracts, graph assembly, and conditional routing. Builds and executes the LangGraph pipeline used by the Telegram bot. `src/api/` reuses this pipeline until it is extracted into a shared location.

## Entrypoints

| File | Role |
|------|------|
| [`graph.py`](./graph.py) `build_graph()` | Assembles the full `StateGraph` with nodes and edges |
| [`state.py`](./state.py) `RAGState` | TypedDict state contract passed between nodes |
| [`edges.py`](./edges.py) | Conditional routing: `route_cache`, `route_grade`, `route_after_guard`, `route_by_query_type` |
| [`context.py`](./context.py) `GraphContext` | Runtime container with services and config |
| [`nodes/cache.py`](./nodes/cache.py) | Semantic cache check/store |
| [`nodes/rewrite.py`](./nodes/rewrite.py) | LLM query reformulation |
| [`nodes/retrieve.py`](./nodes/retrieve.py) | Hybrid Qdrant retrieval |
| [`nodes/grade.py`](./nodes/grade.py) | Document relevance scoring |
| [`nodes/rerank.py`](./nodes/rerank.py) | ColBERT reranking |
| [`nodes/generate.py`](./nodes/generate.py) | Answer generation |
| [`nodes/classify.py`](./nodes/classify.py) | Query classification |
| [`nodes/guard.py`](./nodes/guard.py) | Safety and policy guardrails |
| [`nodes/respond.py`](./nodes/respond.py) | Final response formatting |
| [`nodes/transcribe.py`](./nodes/transcribe.py) | Voice transcription node |

## Boundaries

- Nodes do not call Telegram transport APIs directly; they operate on `RAGState`.
- `RAGState` field changes must be backward-compatible with existing edges and node contracts.
- Ingestion and collection semantics are owned by `src/ingestion/`; nodes read only.

## Focused Checks

```bash
uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q
uv run pytest tests/unit/ -k "graph" -q
```

## See Also

- [`../README.md`](../README.md) — Telegram transport layer overview
- [`../agents/README.md`](../agents/README.md) — Agent SDK alternative pipeline
- [`../../src/ingestion/`](../../src/ingestion/) — Document ingestion
- [`../../docs/PIPELINE_OVERVIEW.md`](../../docs/PIPELINE_OVERVIEW.md) — Ingestion, query, and voice runtime flows
