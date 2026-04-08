# Pipeline Routing

Query routing logic through the LangGraph pipeline.

## Routing Flow

```
START
  ↓
classify (QueryClassifier)
  ↓
┌───────────────────────────────────────┐
│ Route by query_type:                  │
│                                       │
│ CHITCHAT → respond → END              │
│ OFF_TOPIC → respond → END            │
│ _NO_RAG_QUERY_TYPES → respond → END   │
│ otherwise → guard → ...                │
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
│   hallucination → rewrite → retrieve  │
│   irrelevant → rewrite → retrieve     │
│   relevant → rerank/rewrite/generate  │
└───────────────────────────────────────┘
  ↓
rerank (ColBERT Reranker) — optional
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
| `APARTMENT` | Apartment search | Yes |
| `KNOWLEDGE` | RAG retrieval | Yes |
| `CRM` | Agent tools | Partial |
| `CHITCHAT` | Direct response | No |
| `OFF_TOPIC` | Direct response | No |
| `VOICE` | Voice agent | Yes |

## Route Functions

| Function | Location | Returns |
|----------|----------|---------|
| `route_after_classify` | `graph/graph.py` | Next node name |
| `route_after_guard` | `graph/graph.py` | Next node name |
| `route_after_cache_check` | `graph/graph.py` | Next node name |
| `route_after_grade` | `graph/graph.py` | Next node name |
| `route_after_rerank` | `graph/graph.py` | Next node name |

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
    node,
    route_function,
    {
        "rerank": lambda s: s.get("query_type") == "APARTMENT",
        "generate": lambda s: s.get("query_type") == "KNOWLEDGE",
        ...
    }
)
```

## Code Locations

| File | Purpose |
|------|---------|
| `telegram_bot/graph/graph.py` | Graph building + route functions |
| `telegram_bot/graph/nodes/classify.py` | Query classification |
| `telegram_bot/graph/nodes/guard.py` | Content filtering |
| `telegram_bot/graph/nodes/cache_check.py` | Cache lookup |
| `telegram_bot/graph/nodes/retrieve.py` | Retrieval |
| `telegram_bot/graph/nodes/grade.py` | Document grading |
| `telegram_bot/graph/nodes/rerank.py` | ColBERT rerank |
| `telegram_bot/graph/nodes/rewrite.py` | Query rewrite |
| `telegram_bot/graph/nodes/generate.py` | LLM generation |
| `telegram_bot/graph/nodes/respond.py` | Response delivery |
