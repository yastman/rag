# Qdrant Configuration

**Version:** v1.15.4
**Location:** `src/ingestion/indexer.py:101-167`

## Collection: `legal_documents`

- Points: 1,294
- Vectors: 3,882 (dense + colbert + bm42)
- Status: Green

## Vector Configuration

```python
from qdrant_client.models import (
    VectorParams, Distance, HnswConfigDiff,
    ScalarQuantization, ScalarQuantizationConfig, ScalarType,
    MultiVectorConfig, MultiVectorComparator,
    SparseVectorParams, Modifier
)

vectors_config = {
    "dense": VectorParams(
        size=1024,
        distance=Distance.COSINE,
        hnsw_config=HnswConfigDiff(m=16, ef_construct=200, on_disk=False),
        quantization_config=ScalarQuantization(
            scalar=ScalarQuantizationConfig(
                type=ScalarType.INT8,
                quantile=0.99,
                always_ram=True
            )
        ),
        on_disk=True  # Original vectors on disk
    ),
    "colbert": VectorParams(
        size=1024,
        distance=Distance.COSINE,
        multivector_config=MultiVectorConfig(
            comparator=MultiVectorComparator.MAX_SIM
        ),
        hnsw_config=HnswConfigDiff(m=0),
        on_disk=True
    )
}

sparse_vectors_config = {
    "bm42": SparseVectorParams(modifier=Modifier.IDF)
}
```

## Quantization

- **Type:** Scalar Int8
- **Compression:** 4x (1024 floats → 256 bytes)
- **Accuracy:** 0.99 (quantile=0.99)
- **RAM savings:** ~75% (quantized in RAM, originals on disk)
- **Search:** 2x faster (SIMD on int8)

## HNSW Parameters

| Parameter | Value | Purpose |
|-----------|-------|---------|
| m | 16 | Edges per node |
| ef_construct | 200 | Build quality |
| on_disk | False | Graph in RAM |

**Complexity:** O(log N)

## Payload Indexes

**Location:** `src/ingestion/indexer.py:148-167`

```python
# Fast filtering
client.create_payload_index(
    collection_name="legal_documents",
    field_name="article_number",
    field_schema=PayloadSchemaType.KEYWORD
)
```

**Indexed fields:**
- `article_number`
- `document_name`

## Point Structure

```python
PointStruct(
    id=uuid.uuid4(),
    vector={
        "dense": [1024],
        "colbert": [[N, 1024]],
    },
    payload={
        "page_content": str,
        "metadata": {
            "document_name": str,
            "article_number": str,
            "chapter": str,
            "section": str,
            "chunk_id": str,
            "order": int
        }
    }
)
```

## Search Queries

### Dense-Only

```python
results = client.search(
    collection_name="legal_documents",
    query_vector=embedding,
    using="dense",
    limit=10,
    search_params={
        "quantization": {"rescore": True, "oversampling": 3.0}
    }
)
```

### Hybrid RRF

```python
results = client.query_points(
    collection_name="legal_documents",
    prefetch=[
        Prefetch(query=dense_emb, using="dense", limit=100),
        Prefetch(query=SparseVector(...), using="bm42", limit=100),
    ],
    query=FusionQuery(fusion="rrf"),
    limit=10
)
```

**RRF formula:** `score = Σ 1/(60 + rank_i)`

### Hybrid RRF + ColBERT

```python
results = client.query_points(
    collection_name="legal_documents",
    prefetch=[
        {
            "prefetch": [
                {"query": dense_emb, "using": "dense", "limit": 100},
                {"query": sparse_vec, "using": "bm42", "limit": 100},
            ],
            "query": {"fusion": "rrf"}
        }
    ],
    query=colbert_vecs,
    using="colbert",
    limit=10
)
```

**MaxSim:** `score = Σ max_similarity(q_token, all_d_tokens)`

## Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Indexing | ~3.6s/doc | Parse + chunk + embed + upsert |
| Dense search | ~0.65s | With quantization rescoring |
| Hybrid RRF | ~0.72s | Dense + sparse + fusion |
| RRF + ColBERT | ~0.8s | + token-level rerank |

**Quality:**
- Recall@1: 95% (RRF+ColBERT)
- NDCG@10: 0.98

## Memory

### Before
- Dense + ColBERT in RAM: ~2.7 GB

### After (quantized)
- Quantized dense in RAM: ~1.3 MB
- Originals on disk: ~2.7 GB
- **Savings:** ~75%

## API

```python
client = QdrantClient(
    url="http://localhost:6333",
    api_key=os.getenv("QDRANT_API_KEY")
)
```

**Endpoints:**
- Health: `GET /health`
- Collections: `GET /collections`
- Points: `PUT /collections/{name}/points`
- Search: `POST /collections/{name}/points/search`
- Query: `POST /collections/{name}/points/query`

## Backup

```bash
# Create snapshot
curl -X POST "http://localhost:6333/collections/{name}/snapshots" \
  -H "api-key: $QDRANT_API_KEY"

# Scripts
./scripts/qdrant_backup.sh
./scripts/qdrant_restore.sh
```

## References

- Docs: https://qdrant.tech/documentation/
- Quantization: https://qdrant.tech/documentation/guides/quantization/
- Hybrid Search: https://qdrant.tech/articles/hybrid-search/
- BM42: https://qdrant.tech/articles/bm42/
