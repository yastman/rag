# Pipeline Routing

> Routing rules and conditional edges of the LangGraph `StateGraph` built by `build_graph()` in [`telegram_bot/graph/graph.py`](../telegram_bot/graph/graph.py). This graph drives the **voice path** end-to-end and is reused by the **text path** through the `rag_search` tool's internal retrieve→grade→rerank loop. The dual-path split itself is documented in [`CLIENT_PIPELINE.md`](CLIENT_PIPELINE.md); the operational overview of ingestion / query / voice flows lives in [`PIPELINE_OVERVIEW.md`](PIPELINE_OVERVIEW.md). Voice migration plan: [`docs/adr/0010-voice-path-create-agent-migration-plan.md`](adr/0010-voice-path-create-agent-migration-plan.md), tracked under #1535 and the SDK-native audit issue [#1538](https://github.com/yastman/rag/issues/1538).

Query routing logic through the LangGraph pipeline.

## Routing Flow

```
START
  ↓
route_start
  ↓
transcribe (voice only) → classify
  ↓
classify (QueryClassifier)
  ↓
┌───────────────────────────────────────┐
│ Route by query_type:                  │
│                                       │
│ CHITCHAT → respond → END              │
│ OFF_TOPIC → respond → END            │
│ STRUCTURED/FAQ/ENTITY/GENERAL → guard │
└───────────────────────────────────────┘
  ↓
guard (ContentFilter)
  ↓ (pass)
┌───────────────────────────────────────┐
│ cache_check (SemanticCache)           │
│   hit → respond → END                 │
│   miss → retrieve → ...               │
└───────────────────────────────────────┘
  ↓
retrieve (QdrantHybridSearch)
  ↓
grade (DocumentGrader)
  ↓
┌───────────────────────────────────────┐
│ Grade result:                        │
│   relevant + rerank needed → rerank   │
│   relevant + skip rerank → generate   │
│   not relevant + retries → rewrite    │
│   otherwise → generate                │
└───────────────────────────────────────┘
  ↓
rerank (optional post-retrieval stage)
  ↓
generate (LLM)
  ↓
cache_store (if enabled)
  ↓
respond (Telegram sender)
  ↓
summarize — only if checkpointer enabled
  ↓
END
```

## Query Type Classification

| Query Type | Handler | Cacheable |
|------------|---------|-----------|
| `STRUCTURED` | RAG retrieval with structured catalog criteria | Yes |
| `FAQ` | RAG retrieval for procedural/knowledge questions | Yes |
| `ENTITY` | RAG retrieval for named locations/complexes | Yes |
| `GENERAL` | Default RAG retrieval path | Yes |
| `CHITCHAT` | Direct response | No |
| `OFF_TOPIC` | Direct response | No |

`telegram_bot/graph/nodes/classify.py` is the source of truth for query type constants and regex priority:

```bash
rg -n "CHITCHAT|OFF_TOPIC|STRUCTURED|FAQ|ENTITY|GENERAL|def classify_query" telegram_bot/graph/nodes/classify.py
```

## Route Functions

| Function | Location | Returns |
|----------|----------|---------|
| `route_start` | `telegram_bot/graph/edges.py` | `transcribe` or `classify` |
| `route_by_query_type` | `telegram_bot/graph/edges.py` | `respond` or `guard` |
| `_route_by_query_type_no_guard` | `telegram_bot/graph/graph.py` | `respond` or `cache_check` |
| `route_after_guard` | `telegram_bot/graph/edges.py` | `respond` or `cache_check` |
| `route_cache` | `telegram_bot/graph/edges.py` | `respond` or `retrieve` |
| `route_grade` | `telegram_bot/graph/edges.py` | `rerank`, `rewrite`, or `generate` |

## Rewrite Loop

Queries that fail grade checks enter a rewrite loop:

```
retrieve → grade → fail → rewrite → retrieve (up to max_rewrite_attempts)
```

- `max_rewrite_attempts`: configurable (default: 1)
- Prevents infinite loops with recursion limit

## Conditional Edges

Edges are defined via conditional functions in `build_graph()`:

```python
graph.add_conditional_edges(
    "grade",
    route_grade,
    {
        "rerank": "rerank",
        "rewrite": "rewrite",
        "generate": "generate",
    }
)
```

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/graph/graph.py` | Graph building + route functions |
| `telegram_bot/graph/nodes/classify.py` | Query classification |
| `telegram_bot/graph/nodes/guard.py` | Content filtering |
| `telegram_bot/graph/nodes/cache.py` | Cache lookup/store |
| `telegram_bot/graph/nodes/retrieve.py` | Retrieval |
| `telegram_bot/graph/nodes/grade.py` | Document grading |
| `telegram_bot/graph/nodes/rerank.py` | ColBERT rerank |
| `telegram_bot/graph/nodes/rewrite.py` | Query rewrite |
| `telegram_bot/graph/nodes/generate.py` | LLM generation |
| `telegram_bot/graph/nodes/respond.py` | Response delivery |
