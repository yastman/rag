---
paths: "src/retrieval/**, **/qdrant*.py, **/retriever*.py, **/graph/nodes/retrieve.py, **/graph/nodes/rerank.py"
---

***REMOVED*** Search & Retrieval

Hybrid search with RRF fusion, Qdrant vector database, and reranking.

***REMOVED******REMOVED*** Purpose

Retrieve relevant documents using combination of dense (semantic) and sparse (keyword) vectors with intelligent fusion and reranking.

***REMOVED******REMOVED*** Architecture

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

***REMOVED******REMOVED*** Key Files

| File | Description |
|------|-------------|
| `src/retrieval/search_engines.py` | BaseSearchEngine ABC + variants |
| `telegram_bot/services/qdrant.py` | QdrantService (async, gRPC, batch, group_by) |
| `telegram_bot/graph/nodes/retrieve.py` | LangGraph retrieve_node (hybrid RRF + cache) |
| `telegram_bot/graph/nodes/grade.py` | Score-based relevance grading (RRF threshold 0.005) |
| `telegram_bot/graph/nodes/rerank.py` | Optional ColBERT + score-sort fallback, top-5 |
| `telegram_bot/graph/nodes/rewrite.py` | LLM query reformulation, max 2 retries |

***REMOVED******REMOVED*** LangGraph retrieve_node

```python
from telegram_bot.graph.nodes.retrieve import retrieve_node

***REMOVED*** Flow: search cache → sparse cache → qdrant.hybrid_search_rrf() → cache results
result = await retrieve_node(state, cache=cache, sparse_embeddings=sparse, qdrant=qdrant)
***REMOVED*** Returns: {documents, search_results_count, sparse_embedding, latency_stages}
```

Dense embedding comes from `state["query_embedding"]` (set by cache_check_node).

**Parallel re-embed path:** After rewrite (`query_embedding=None`), dense and sparse embeddings are computed simultaneously via `asyncio.gather`, saving ~0.5-1s.

***REMOVED******REMOVED*** LangGraph Agentic Nodes

***REMOVED******REMOVED******REMOVED*** grade_node

Score-based heuristic: `top_score > relevance_threshold_rrf` (default 0.005, env `RELEVANCE_THRESHOLD_RRF`) → documents relevant. RRF scores use scale `1/(k+rank)` where k=60, so typical scores are 0.001–0.016. Also sets `grade_confidence` (= top_score) and `skip_rerank` (true when `top_score >= skip_rerank_threshold`).

***REMOVED******REMOVED******REMOVED*** rerank_node

ColBERT reranking if reranker provided, else score-sort fallback (top-5).

***REMOVED******REMOVED******REMOVED*** rewrite_node

LLM reformulation via OpenAI SDK (`GraphConfig.create_llm()`). Increments `rewrite_count`, resets embeddings for re-retrieval. Max `max_rewrite_attempts` (default 1) retries before fallback to generate.

***REMOVED******REMOVED*** Search Engine Variants

| Engine | Recall@1 | Latency | Description |
|--------|----------|---------|-------------|
| HybridRRFColBERT | 94% | ~1.0s | Dense + Sparse + ColBERT (default) |
| DBSFColBERT | 91% | ~0.7s | 7% faster variant |
| HybridRRF | 92% | ~0.8s | Without ColBERT |
| Baseline | 91.3% | ~0.65s | Dense only |

***REMOVED******REMOVED*** Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dense_weight` | 0.6 | RRF weight for dense vectors |
| `sparse_weight` | 0.4 | RRF weight for sparse vectors |
| `rrf_k` | 60 | RRF constant, scores = 1/(k+rank) |
| `relevance_threshold_rrf` | 0.005 | Grade threshold for RRF scores (env `RELEVANCE_THRESHOLD_RRF`) |
| `prefetch_multiplier` | 3 | Overfetch ratio for RRF |
| `quantization_mode` | binary | off/scalar/binary (32x compression) |
| `quantization_rescore` | true | Rescore with full vectors |
| `quantization_oversampling` | 2.0 | Fetch 2x more candidates |
| `small_to_big_mode` | off | off/on/auto (context expansion) |
| `acorn_mode` | off | off/on/auto (filtered search optimization) |
| `skip_rerank_threshold` | 0.85 | Skip ColBERT rerank when grade confidence >= threshold |
| `generate_max_tokens` | 2048 | Token cap for LLM generation (env: `GENERATE_MAX_TOKENS`) |

***REMOVED******REMOVED*** RRF Weights by Query Type

| Query Type | Dense | Sparse | Example |
|------------|-------|--------|---------|
| Semantic | 0.6 | 0.4 | "уютная квартира с видом" |
| Exact | 0.2 | 0.8 | "корпус 5", "ID 12345" |

***REMOVED******REMOVED*** Common Patterns

***REMOVED******REMOVED******REMOVED*** Hybrid search with RRF

```python
from telegram_bot.services.qdrant import QdrantService

***REMOVED*** Uses prefer_grpc=True for faster gRPC connections
qdrant = QdrantService(url="http://localhost:6333", collection_name="gdrive_documents_bge")

results = await qdrant.hybrid_search_rrf(
    dense_vector=query_embedding,
    sparse_vector=sparse_embedding,
    filters={"city": "Несебр"},
    top_k=20,
)
```

***REMOVED******REMOVED******REMOVED*** Batch search (multi-query, single round-trip)

```python
***REMOVED*** batch_search_rrf — sends multiple queries via query_batch_points()
results = await qdrant.batch_search_rrf(
    queries=[
        {"dense_vector": emb1, "sparse_vector": sp1},
        {"dense_vector": emb2, "sparse_vector": sp2},
    ],
    top_k=20,
)
***REMOVED*** Deduplicates results by point ID
```

***REMOVED******REMOVED******REMOVED*** Group-by for diverse results

```python
***REMOVED*** Uses query_points_groups() for diversity within search results
results = await qdrant.hybrid_search_rrf(
    dense_vector=emb, sparse_vector=sparse,
    group_by="doc_id", group_size=2,
    top_k=20,
)
```

***REMOVED******REMOVED******REMOVED*** Qdrant SDK nested prefetch (sync)

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

***REMOVED******REMOVED*** Filter Building

```python
filters = {"city": "Бургас", "rooms": 2, "price": {"lt": 80000}}
```

***REMOVED******REMOVED*** Binary Quantization

Enabled by default for 40x faster search, 75% less RAM.

**Collection selection:** `BotConfig.get_collection_name()` appends `_binary` or `_scalar` suffix.

***REMOVED******REMOVED*** ACORN (Filtered Search Optimization)

**Status (Feb 2026):** Code ready, waiting for `qdrant-client` to export `AcornSearchParams`.

***REMOVED******REMOVED*** LangGraph Graph Assembly

9-node StateGraph with conditional routing:

```
START → classify → [CHITCHAT/OFF_TOPIC] → respond → END
                 → [other] → cache_check → [HIT] → respond → END
                                         → [MISS] → retrieve → grade
                                                      → [relevant + high confidence] → generate → cache_store → respond → END
                                                      → [relevant] → rerank → generate → cache_store → respond → END
                                                      → [count < max_rewrite_attempts AND effective] → rewrite → retrieve (loop)
                                                      → [count >= max_rewrite_attempts] → generate → cache_store → respond → END
```

***REMOVED******REMOVED******REMOVED*** Edges

| Function | From → To |
|----------|-----------|
| `route_by_query_type` | classify → respond (CHITCHAT/OFF_TOPIC) or cache_check |
| `route_cache` | cache_check → respond (hit) or retrieve (miss) |
| `route_grade` | grade → generate (skip_rerank), rerank (relevant), rewrite (count < max_rewrite_attempts AND effective), generate (fallback) |

***REMOVED******REMOVED******REMOVED*** Usage

```python
from telegram_bot.graph.graph import build_graph

graph = build_graph(
    cache=cache_mgr, embeddings=bge_emb,
    sparse_embeddings=bge_sparse, qdrant=qdrant_svc,
    reranker=colbert_svc, message=aiogram_message,
)
result = await graph.ainvoke(initial_state, config={"callbacks": [langfuse_handler]})
```

***REMOVED******REMOVED*** Dependencies

- Container: `dev-qdrant` / `vps-qdrant` (6333, 6334 gRPC)
- Client: `AsyncQdrantClient(prefer_grpc=True)` — uses gRPC for faster queries
- Dep: `grpcio` (required for gRPC transport)
- Collections: `gdrive_documents_bge` (VPS), `contextual_bulgaria_voyage` (dev), `legal_documents` (dev)

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/test_qdrant_service.py -v
pytest tests/unit/test_search_engines.py -v
pytest tests/unit/graph/test_retrieve_node.py -v    ***REMOVED*** 6 tests
pytest tests/unit/graph/test_agentic_nodes.py -v    ***REMOVED*** 12 tests (grade/rerank/rewrite)
pytest tests/unit/graph/test_edges.py -v             ***REMOVED*** 13 tests (routing)
pytest tests/unit/graph/test_graph.py -v             ***REMOVED*** 3 tests (assembly)
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| `Qdrant timeout` | Enable `use_quantization=True` |
| Low recall | Check embedding model matches collection |
| Empty results | Verify collection name, check filters |

***REMOVED******REMOVED*** Development Guide

***REMOVED******REMOVED******REMOVED*** Adding new search engine

1. Create class in `src/retrieval/search_engines.py`
2. Inherit from `BaseSearchEngine`
3. Implement `search()` and `get_name()` methods
4. Add to `SearchEngine` enum in `src/config/settings.py`
5. Write benchmark in `src/evaluation/`
