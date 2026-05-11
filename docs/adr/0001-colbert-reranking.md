# ADR-0001: ColBERT Reranking over Other Approaches

**Status:** Accepted

**Date:** 2026-01-15

## Context

The RAG pipeline needed a reranking solution to improve document retrieval quality. We evaluated several approaches:

1. **Dense embedding reranking** — Use cosine similarity on dense embeddings
2. **Cross-encoder reranking** — Full cross-attention between query and document
3. **ColBERT reranking** — Late interaction with maxsim operation
4. **No reranking** — Direct RRF scores

## Decision

We chose **ColBERT reranking** (via BGE-M3 model) as the default reranker.

### Why ColBERT

1. **BGE-M3 native** — The project already uses BGE-M3 for embeddings; ColBERT vectors come from the same model
2. **Efficiency** — Pre-computed ColBERT vectors enable fast retrieval without full cross-encoder overhead
3. **Quality** — Late interaction captures fine-grained semantic matching better than bi-encoder approaches
4. **Server-side reranking** — Qdrant supports nested prefetch with ColBERT, reducing client-server round trips

### Why Not Others

| Approach | Reason Rejected |
|----------|----------------|
| Pure dense cosine | Less nuanced than ColBERT for phrase-level matching |
| Cross-encoder | Too slow for real-time queries; requires separate model |
| No reranking | RRF alone insufficient for complex queries |

## Consequences

### Positive
- Improved retrieval quality for complex queries
- Single model for embeddings + reranking (BGE-M3)
- Qdrant ColBERT prefetch support

### Negative
- Additional storage for ColBERT vectors (~2x embedding storage)
- Latency addition when reranking triggered (typically 50-200ms)
- `RERANK_PROVIDER` configuration complexity

## Implementation

- Current runtime keeps the legacy client-side reranker service deprecated; `PropertyBot` and the RAG API set the reranker hook to `None`.
- `RERANK_PROVIDER=colbert` selects the server-side Qdrant ColBERT path when ColBERT query vectors and the collection schema are available.
- `telegram_bot/graph/nodes/retrieve.py` calls `QdrantService.hybrid_search_rrf_colbert()` for the 3-stage path: dense + sparse prefetch, RRF fusion, then Qdrant ColBERT MaxSim reranking with stored multivectors.
- If ColBERT vectors are missing, empty, or erroring, `QdrantService.hybrid_search_rrf_colbert()` falls back to plain hybrid RRF and records fallback metadata.
- `telegram_bot/graph/nodes/rerank.py` remains an optional graph stage, but the active ColBERT implementation is server-side Qdrant reranking during retrieval rather than a separate client-side reranker service.

## References

- [ColBERT Paper](https://arxiv.org/abs/2004.12832)
- [BGE-M3 Model](https://huggingface.co/BAAI/bge-m3)
