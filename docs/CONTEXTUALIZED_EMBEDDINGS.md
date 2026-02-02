***REMOVED*** Contextualized Embeddings (voyage-context-3)

> Voyage AI contextualized embeddings for improved document retrieval quality.

**Feature flag:** `use_contextualized_embeddings=true`
**Model:** `voyage-context-3`
**Dimensions:** 2048, 1024, 512, 256 (Matryoshka)

---

***REMOVED******REMOVED*** Overview

Contextualized embeddings process document chunks together, allowing each chunk's embedding to incorporate context from surrounding chunks in the same document. This improves retrieval quality for complex queries that depend on document structure.

```
Standard Embeddings:     Contextualized Embeddings:
┌─────────┐              ┌─────────────────────┐
│ Chunk 1 │──►[vec1]     │ Document            │
├─────────┤              │ ┌─────┬─────┬─────┐ │
│ Chunk 2 │──►[vec2]     │ │ C1  │ C2  │ C3  │ │──►[vec1, vec2, vec3]
├─────────┤              │ └─────┴─────┴─────┘ │   (context-aware)
│ Chunk 3 │──►[vec3]     └─────────────────────┘
└─────────┘
(independent)            (joint processing)
```

---

***REMOVED******REMOVED*** When to Use

| Use Case | Contextualized? | Rationale |
|----------|-----------------|-----------|
| Legal documents | Yes | Structure and cross-references matter |
| Technical documentation | Yes | Section context improves results |
| Property listings | Maybe | Short, independent chunks may not benefit |
| FAQ/Q&A pairs | No | Each pair is self-contained |

---

***REMOVED******REMOVED*** API Constraints (2026)

| Parameter | Limit |
|-----------|-------|
| Max documents per request | 1,000 |
| Max chunks per request | 16,000 |
| Max tokens per document | 32,000 |
| Max total tokens | 120,000 |

**Important:** Chunks should NOT overlap (unlike standard RAG chunking with overlap).

---

***REMOVED******REMOVED*** Usage

***REMOVED******REMOVED******REMOVED*** Basic Usage

```python
from src.models.contextualized_embedding import ContextualizedEmbeddingService

service = ContextualizedEmbeddingService(
    api_key="your-voyage-api-key",
    output_dimension=1024,  ***REMOVED*** 2048, 1024, 512, or 256
    output_dtype="float",   ***REMOVED*** float, int8, uint8, binary, ubinary
)

***REMOVED*** Embed document chunks (process together for context)
doc_chunks = [
    ["Introduction to topic...", "Main content...", "Conclusion..."],  ***REMOVED*** Doc 1
    ["Chapter 1...", "Chapter 2..."],  ***REMOVED*** Doc 2
]
result = await service.embed_documents(doc_chunks)
***REMOVED*** result.embeddings: list of vectors (one per chunk, flattened)
***REMOVED*** result.chunks_per_document: [3, 2] (chunks per doc)

***REMOVED*** Embed query
query_vec = await service.embed_query("search query")
```

***REMOVED******REMOVED******REMOVED*** Configuration

Add to `.env`:

```bash
***REMOVED*** Enable contextualized embeddings (default: false)
USE_CONTEXTUALIZED_EMBEDDINGS=true

***REMOVED*** Optional: output dimension (default: 1024)
CONTEXTUALIZED_EMBEDDING_DIM=1024
```

Or in `src/config/settings.py`:

```python
settings = Settings(
    use_contextualized_embeddings=True,
    contextualized_embedding_dim=1024,
)
```

---

***REMOVED******REMOVED*** A/B Testing

Run the A/B test to compare baseline vs contextualized embeddings:

```bash
***REMOVED*** Basic test
python scripts/test_contextualized_ab.py

***REMOVED*** With ground truth evaluation
python scripts/test_contextualized_ab.py \
    --ground-truth tests/eval/ground_truth.json \
    --k 5 \
    --runs 3

***REMOVED*** Different dimension
python scripts/test_contextualized_ab.py --dim 2048
```

***REMOVED******REMOVED******REMOVED*** Metrics Evaluated

| Metric | Description |
|--------|-------------|
| Latency | Embedding + search time |
| Precision@k | % of relevant docs in top-k |
| Recall@k | % of relevant docs retrieved |
| Overlap | % same results as baseline |

***REMOVED******REMOVED******REMOVED*** Pass Criteria

- Latency overhead <= 50%
- Overlap with baseline >= 60%
- Precision delta >= -10%
- Recall delta >= -10%

---

***REMOVED******REMOVED*** Implementation Details

***REMOVED******REMOVED******REMOVED*** Service Class

Located in `src/models/contextualized_embedding.py`:

```python
class ContextualizedEmbeddingService:
    MODEL_NAME = "voyage-context-3"

    ***REMOVED*** API limits
    MAX_DOCUMENTS_PER_REQUEST = 1000
    MAX_CHUNKS_PER_REQUEST = 16000
    MAX_TOKENS_PER_DOCUMENT = 32000
    MAX_TOTAL_TOKENS = 120000

    ***REMOVED*** Matryoshka dimensions
    SUPPORTED_DIMS = (2048, 1024, 512, 256)
```

***REMOVED******REMOVED******REMOVED*** Result Format

```python
@dataclass
class ContextualizedEmbeddingResult:
    embeddings: list[list[float]]  ***REMOVED*** Flat list of all chunk embeddings
    total_tokens: int              ***REMOVED*** Total tokens processed
    chunks_per_document: list[int] ***REMOVED*** Chunks per input document
```

***REMOVED******REMOVED******REMOVED*** Langfuse Tracing

All calls are automatically traced with `@observe` decorator:
- `voyage-contextualized-embed-documents`
- `voyage-contextualized-embed-query`
- `voyage-contextualized-embed-queries`

---

***REMOVED******REMOVED*** Best Practices

***REMOVED******REMOVED******REMOVED*** Chunking Strategy

For contextualized embeddings, chunks should:

1. **Not overlap** - Unlike standard chunking with 20% overlap
2. **Be semantically complete** - End at natural boundaries
3. **Stay within limits** - Keep documents under 32K tokens
4. **Group logically** - All chunks from same document together

```python
***REMOVED*** Good: Non-overlapping semantic chunks
chunks = ["Introduction...", "Section 1...", "Section 2...", "Conclusion..."]

***REMOVED*** Bad: Overlapping chunks (standard RAG style)
chunks = ["Intro + start of S1", "end of S1 + start of S2", ...]  ***REMOVED*** Don't do this
```

***REMOVED******REMOVED******REMOVED*** Batch Processing

Process multiple documents together for efficiency:

```python
***REMOVED*** Process 10 documents in one API call
all_docs = [doc1_chunks, doc2_chunks, ..., doc10_chunks]
result = await service.embed_documents(all_docs)

***REMOVED*** Map embeddings back to documents
offset = 0
for doc_idx, num_chunks in enumerate(result.chunks_per_document):
    doc_embeddings = result.embeddings[offset:offset + num_chunks]
    offset += num_chunks
```

***REMOVED******REMOVED******REMOVED*** Error Handling

The service includes automatic retry with exponential backoff:

```python
***REMOVED*** Retries on: RateLimitError, ServiceUnavailableError, Timeout
***REMOVED*** Up to 6 attempts with random exponential backoff (max 60s)
```

---

***REMOVED******REMOVED*** Comparison: Standard vs Contextualized

| Aspect | Standard (voyage-3-large) | Contextualized (voyage-context-3) |
|--------|---------------------------|-----------------------------------|
| Processing | Independent chunks | Joint document processing |
| Context | Local only | Cross-chunk awareness |
| Chunking | Overlap recommended | No overlap |
| Best for | Short, independent texts | Structured documents |
| API calls | 1 per batch of chunks | 1 per batch of documents |
| Latency | Lower | Slightly higher |

---

***REMOVED******REMOVED*** Troubleshooting

***REMOVED******REMOVED******REMOVED*** Common Issues

| Issue | Solution |
|-------|----------|
| "Too many chunks" error | Split into multiple API calls (<16K chunks) |
| "Document too large" error | Ensure each document <32K tokens |
| Low quality results | Check chunking strategy (no overlap) |
| High latency | Reduce output dimension (1024 → 512) |

***REMOVED******REMOVED******REMOVED*** Debugging

Enable debug logging:

```python
import logging
logging.getLogger("src.models.contextualized_embedding").setLevel(logging.DEBUG)
```

---

***REMOVED******REMOVED*** See Also

- `scripts/test_contextualized_ab.py` - A/B testing script
- `tests/integration/test_contextualized_pipeline.py` - Integration tests
- `docs/PIPELINE_OVERVIEW.md` - Overall architecture
- [Voyage AI Documentation](https://docs.voyageai.com/docs/contextualized-chunk-embeddings)
