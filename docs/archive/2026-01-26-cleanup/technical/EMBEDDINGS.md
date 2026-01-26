# BGE-M3 Embeddings Specification

**Model:** `BAAI/bge-m3`
**Location:** `src/ingestion/indexer.py:64`

## Configuration

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True, devices=['cuda:0'])
```

**Parameters:**
- `use_fp16=True`: 2x faster, <1% accuracy loss
- `devices=['cuda:0']`: GPU inference, 4GB VRAM
- `batch_size=32`: Optimal throughput
- `max_length=8192`: Token limit (truncates if exceeded)

## Output Types

### Dense Vectors
- **Dimensions:** 1024
- **Normalized:** Yes (cosine similarity)
- **Access:** `output['dense_vecs']`

### Sparse Vectors (BM42)
- **Format:** `{token_id: weight}` dict
- **Access:** `output['lexical_weights']`
- **Performance:** +9% Precision@10 vs BM25

### ColBERT Multivectors
- **Dimensions:** N × 1024 (N = num_tokens)
- **Scoring:** MaxSim between query/doc tokens
- **Access:** `output['colbert_vecs']`

## Usage Patterns

### Generate All Three

```python
output = model.encode(
    texts,
    batch_size=32,
    max_length=8192,
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=True
)

dense = output['dense_vecs']        # (batch, 1024)
sparse = output['lexical_weights']  # [{token: weight}, ...]
colbert = output['colbert_vecs']    # (batch, N, 1024)
```

### Similarity Scoring

```python
# Dense
similarity = query_dense @ doc_dense.T

# Sparse
sparse_score = model.compute_lexical_matching_score(
    query_sparse, doc_sparse
)

# ColBERT
colbert_score = model.colbert_score(
    query_colbert[0], doc_colbert[0]
).item()
```

## Performance

| Batch | CPU Latency | GPU Latency | Throughput |
|-------|-------------|-------------|------------|
| 1     | 180ms       | 45ms        | 22/s       |
| 32    | 2.1s        | 250ms       | 128/s      |

**Memory:**
- FP32: ~8GB VRAM / ~16GB RAM
- FP16: ~4GB VRAM / ~8GB RAM

#***REMOVED*** Integration

**Location:** `src/ingestion/indexer.py:101-135`

```python
vectors_config = {
    "dense": VectorParams(size=1024, distance=Distance.COSINE),
    "colbert": VectorParams(
        size=1024,
        multivector_config=MultiVectorConfig(
            comparator=MultiVectorComparator.MAX_SIM
        )
    )
}

sparse_vectors_config = {
    "bm42": SparseVectorParams(modifier=Modifier.IDF)
}
```

## References

- Model: https://huggingface.co/BAAI/bge-m3
- Library: https://github.com/FlagOpen/FlagEmbedding
- Implementation: `src/ingestion/indexer.py:64-95`
