---
paths: "src/retrieval/**, **/qdrant*.py, **/retriever*.py, **/graph/nodes/retrieve.py, **/graph/nodes/rerank.py"
---

# Search & Retrieval

Hybrid search with RRF fusion, Qdrant vector database, and reranking.

## Purpose

Retrieve relevant documents using combination of dense (semantic) and sparse (keyword) vectors with intelligent fusion and reranking.

## Architecture

```
LangGraph retrieve_node:
  Query → Dense Embedding (BGE-M3, from cache_check) + Sparse Embedding (BGE-M3)
       → Qdrant Prefetch (dense + sparse)
       → RRF Fusion
       → grade_node → rerank_node (ColBERT or score-sort)
       → Results

VPS:  BGE-M3 for dense + sparse + ColBERT rerank (local CPU)
Dev:  Voyage dense + BM42 sparse + Voyage rerank (API)
```

## Key Files

| File | Description |
|------|-------------|
| `src/retrieval/search_engines.py` | BaseSearchEngine ABC + variants |
| `telegram_bot/services/qdrant.py` | QdrantService (async, Qdrant SDK) |
| `telegram_bot/graph/nodes/retrieve.py` | LangGraph retrieve_node (hybrid RRF + cache) |
| `telegram_bot/graph/nodes/grade.py` | Score-based relevance grading (threshold 0.3) |
| `telegram_bot/graph/nodes/rerank.py` | Optional ColBERT + score-sort fallback, top-5 |
| `telegram_bot/graph/nodes/rewrite.py` | LLM query reformulation, max 2 retries |
| `telegram_bot/services/retriever.py` | RetrieverService (sync, legacy) |

## LangGraph retrieve_node

```python
from telegram_bot.graph.nodes.retrieve import retrieve_node

# Flow: search cache → sparse cache → qdrant.hybrid_search_rrf() → cache results
result = await retrieve_node(state, cache=cache, sparse_embeddings=sparse, qdrant=qdrant)
# Returns: {documents, search_results_count, sparse_embedding, latency_stages}
```

Dense embedding comes from `state["query_embedding"]` (set by cache_check_node).

## LangGraph Agentic Nodes

### grade_node

Score-based heuristic: `top_score > 0.3` → documents relevant.

### rerank_node

ColBERT reranking if reranker provided, else score-sort fallback (top-5).

### rewrite_node

LLM reformulation via ChatLiteLLM. Increments `rewrite_count`, resets embeddings for re-retrieval. Max 2 retries before fallback to generate.

## Search Engine Variants

| Engine | Recall@1 | Latency | Description |
|--------|----------|---------|-------------|
| HybridRRFColBERT | 94% | ~1.0s | Dense + Sparse + ColBERT (default) |
| DBSFColBERT | 91% | ~0.7s | 7% faster variant |
| HybridRRF | 92% | ~0.8s | Without ColBERT |
| Baseline | 91.3% | ~0.65s | Dense only |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dense_weight` | 0.6 | RRF weight for dense vectors |
| `sparse_weight` | 0.4 | RRF weight for sparse vectors |
| `prefetch_multiplier` | 3 | Overfetch ratio for RRF |
| `quantization_mode` | binary | off/scalar/binary (32x compression) |
| `quantization_rescore` | true | Rescore with full vectors |
| `quantization_oversampling` | 2.0 | Fetch 2x more candidates |
| `small_to_big_mode` | off | off/on/auto (context expansion) |
| `acorn_mode` | off | off/on/auto (filtered search optimization) |

## RRF Weights by Query Type

| Query Type | Dense | Sparse | Example |
|------------|-------|--------|---------|
| Semantic | 0.6 | 0.4 | "уютная квартира с видом" |
| Exact | 0.2 | 0.8 | "корпус 5", "ID 12345" |

## Common Patterns

### Hybrid search with RRF

```python
from telegram_bot.services.qdrant import QdrantService

qdrant = QdrantService(url="http://localhost:6333", collection_name="gdrive_documents_bge")

results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    sparse_vector=sparse_embedding,
    filters={"city": "Несебр"},
    top_k=20,
)
```

### Qdrant SDK nested prefetch (sync)

```python
from qdrant_client import models

response = client.query_points(
    collection_name="documents",
    prefetch=[
        models.Prefetch(query=dense_vector, using="dense", limit=100),
        models.Prefetch(query=sparse_vector, using="bm42", limit=100),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=top_k,
)
```

## Filter Building

```python
filters = {"city": "Бургас", "rooms": 2, "price": {"lt": 80000}}
```

## Binary Quantization

Enabled by default for 40x faster search, 75% less RAM.

**Collection selection:** `BotConfig.get_collection_name()` appends `_binary` or `_scalar` suffix.

## ACORN (Filtered Search Optimization)

**Status (Feb 2026):** Code ready, waiting for `qdrant-client` to export `AcornSearchParams`.

## LangGraph Graph Assembly

9-node StateGraph with conditional routing:

```
START → classify → [CHITCHAT/OFF_TOPIC] → respond → END
                 → [other] → cache_check → [HIT] → respond → END
                                         → [MISS] → retrieve → grade
                                                      → [relevant] → rerank → generate → cache_store → respond → END
                                                      → [retries < 2] → rewrite → retrieve (loop)
                                                      → [retries >= 2] → generate → cache_store → respond → END
```

### Edges

| Function | From → To |
|----------|-----------|
| `route_by_query_type` | classify → respond (CHITCHAT/OFF_TOPIC) or cache_check |
| `route_cache` | cache_check → respond (hit) or retrieve (miss) |
| `route_grade` | grade → rerank (relevant), rewrite (retry < 2), generate (fallback) |

### Usage

```python
from telegram_bot.graph.graph import build_graph

graph = build_graph(
    cache=cache_mgr, embeddings=bge_emb,
    sparse_embeddings=bge_sparse, qdrant=qdrant_svc,
    reranker=colbert_svc, message=aiogram_message,
)
result = await graph.ainvoke(initial_state, config={"callbacks": [langfuse_handler]})
```

## Dependencies

- Container: `dev-qdrant` / `vps-qdrant` (6333, 6334 gRPC)
- Collections: `gdrive_documents_bge` (VPS), `contextual_bulgaria_voyage` (dev), `legal_documents` (dev)

## Testing

```bash
pytest tests/unit/test_qdrant_service.py -v
pytest tests/unit/test_search_engines.py -v
pytest tests/unit/graph/test_retrieve_node.py -v    # 5 tests
pytest tests/unit/graph/test_agentic_nodes.py -v    # 12 tests (grade/rerank/rewrite)
pytest tests/unit/graph/test_edges.py -v             # 13 tests (routing)
pytest tests/unit/graph/test_graph.py -v             # 3 tests (assembly)
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Qdrant timeout` | Enable `use_quantization=True` |
| Low recall | Check embedding model matches collection |
| Empty results | Verify collection name, check filters |

## Development Guide

### Adding new search engine

1. Create class in `src/retrieval/search_engines.py`
2. Inherit from `BaseSearchEngine`
3. Implement `search()` and `get_name()` methods
4. Add to `SearchEngine` enum in `src/config/settings.py`
5. Write benchmark in `src/evaluation/`
