# Qdrant Stack

Vector store for the RAG pipeline. Serves hybrid search: dense + sparse (BM42) + ColBERT reranking.

## Service

- **Image**: `qdrant/qdrant:v1.18.1` (pinned in `compose.yml`)
- **Ports** (dev, via `compose.dev.yml`): `6333` (HTTP/REST), `6334` (gRPC)
- **Health**: `GET /readyz` → `200 OK`
- **Volume**: `qdrant_data`
- **Config**: `docker/qdrant/config.yaml` → mounted as `/qdrant/config/production.yaml`
- **Memory limit**: 1G (compose default)

```bash
make core-min-up        # start Qdrant + Redis only
make core-up            # full sidecar stack
```

## Collection Schema

Default collection name: `gdrive_documents_bge` (set via `QDRANT_COLLECTION` / `GDRIVE_COLLECTION_NAME`).

### Vectors

| Name | Type | Dimensions | Distance | Storage | Purpose |
|---|---|---|---|---|---|
| `dense` | Dense | 1024 | Cosine | On disk (quantized in RAM) | Semantic search (BGE-M3) |
| `bm42` | Sparse | variable | — | — | Term frequency (BGE-M3 BM42) |
| `colbert` | Multivector (MAX_SIM) | 1024 × tokens | Cosine | On disk | Late-interaction reranking |

`bm42` is named for backward compatibility with existing collections (not renamed to `sparse`).

### Dense Vector Config

```
size:           1024
distance:       Cosine
HNSW:           m=16, ef_construct=200, on_disk=false (graph in RAM)
quantization:   Scalar INT8, quantile=0.99, always_ram=true
on_disk:        true (original vectors on disk for rescoring)
```

Scalar INT8 quantization gives ~4× compression at 0.99 accuracy. Originals stay on disk for rescoring with `QDRANT_QUANTIZATION_RESCORE=true`.

### ColBERT Vector Config

```
size:           1024
distance:       Cosine
multivector:    MAX_SIM comparator
HNSW:           m=0 (disabled — ColBERT is rerank-only, not for ANN search)
on_disk:        true
```

### Optimizer Config

```
indexing_threshold: 20000   # build HNSW index every 20k vectors
```

## Point Payload Contract

```json
{
  "page_content": "<chunk text>",
  "metadata": {
    "doc_id":   "<file_id>",
    "order":    0,
    "source":   "<relative source path>",
    "file_id":  "<sha256-derived UUID>"
  },
  "file_id": "<sha256-derived UUID>"
}
```

`file_id` is duplicated at the top level for fast `must: [{key: file_id, match: {value: ...}}]` delete filters.

## Bootstrap

Create the collection schema before first ingestion:

```bash
make ingest-unified-bootstrap    # python -m src.ingestion.unified.cli bootstrap --require-colbert
```

This is idempotent: safe to run on an existing collection.

## Operations

### Backup (snapshot)

```bash
make qdrant-backup    # creates snapshots for all collections via REST API
```

Or manually:
```bash
curl -X POST http://localhost:6333/collections/gdrive_documents_bge/snapshots
```

Snapshots are stored inside the `qdrant_data` volume at `/qdrant/storage/snapshots/`.

### Storage Cleanup

```bash
make qdrant-cleanup   # snapshot → trigger optimiser merge → restore threshold
```

This is the fix for unbounded storage growth (issue #1545). It temporarily sets `indexing_threshold=0` to force segment merging, then restores it.

### Collection Status

```bash
curl http://localhost:6333/collections/gdrive_documents_bge | python3 -m json.tool
```

### ColBERT Backfill

If existing points are missing `colbert` vectors (e.g. after migrating from an older pipeline):

```bash
python -m src.ingestion.unified.cli bootstrap --require-colbert
# or directly:
python -m src.ingestion.unified.colbert_backfill
```

## Retrieval Profile

Active profile: `RETRIEVAL_PROFILE=bge_m3_full` (dense + BM42 sparse + ColBERT).

The query path in `src/runtime/retrieval/service.py`:
1. Embed query → dense (1024-dim) + sparse (BM42) + ColBERT multivector via BGE-M3 API
2. `hybrid_search_rrf_colbert`: prefetch dense + sparse candidates, fuse with RRF, rerank with ColBERT MAX_SIM
3. Fall back to `hybrid_search_rrf` (dense + sparse) if ColBERT not available
4. Fall back to dense-only if provider has no sparse support

### Key Tuning Variables

| Variable | Default | Description |
|---|---|---|
| `SEARCH_TOP_K` | 40 | Qdrant prefetch top-k |
| `RERANK_TOP_K` | 7 | ColBERT rerank final top-k |
| `RERANK_CANDIDATES_MAX` | 10 | Max candidates passed to reranker |
| `RELEVANCE_THRESHOLD_RRF` | 0.005 | Min RRF score to keep a document |
| `SKIP_RERANK_THRESHOLD` | 0.018 | Skip reranking if top RRF score ≥ this |
| `HYBRID_DENSE_WEIGHT` | 0.6 | RRF dense weight |
| `HYBRID_SPARSE_WEIGHT` | 0.4 | RRF sparse weight |
| `QDRANT_QUANTIZATION_MODE` | `off` | Quantization mode at query time |
| `QDRANT_QUANTIZATION_RESCORE` | `true` | Rescore with originals after quantized ANN |
| `QDRANT_QUANTIZATION_OVERSAMPLING` | 2.0 | Oversample multiplier for rescoring |

## Conversation History Collection

A separate collection `conversation_history` (default name, set via `QDRANT_HISTORY_COLLECTION`) stores conversation embeddings for context-aware retrieval.
