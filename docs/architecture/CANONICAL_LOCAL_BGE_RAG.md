# Canonical Local BGE-M3 RAG Architecture

> **Status:** Baseline. This document is the single source of truth for the current
> local-first BGE-M3 RAG architecture. Future refactor PRs should cite this document
> rather than re-litigating these decisions.
>
> Related: [#3009](https://github.com/yastman/rag/issues/3009) (parent),
> [#3018](https://github.com/yastman/rag/issues/3018) (env/docs anchor),
> [#3027](https://github.com/yastman/rag/issues/3027) (runtime infra audit)

---

## Decision / Baseline

Local BGE-M3 full-output retrieval is the **canonical retrieval profile** for this
project. The architecture is intentionally local-first:

- Embeddings are produced by a self-hosted BGE-M3 ONNX service, not a remote API.
- All three BGE-M3 output heads (dense, sparse/BM42, ColBERT) are used together.
- Qdrant is the only supported vector database.
- Redis is a required performance/caching layer, not optional.
- Docling + unified ingestion is the only supported indexing path.
- Telegram is the production adapter; it does not own retrieval logic.

Remote/API embeddings (OpenRouter, OpenAI embeddings, VoyageAI) are **out of scope**
for this baseline. See Non-goals below.

---

## Canonical Retrieval Profile

The retrieval profile is selected via environment variables. The canonical values are:

```env
RETRIEVAL_PROFILE=bge_m3_full
EMBEDDINGS_PROVIDER=service_bge_m3
SEARCH_ENGINE=hybrid_rrf_colbert
QDRANT_COLLECTION=gdrive_documents_bge
```

| Variable | Canonical value | Source |
|---|---|---|
| `RETRIEVAL_PROFILE` | `bge_m3_full` | `src/runtime/graph/config.py` |
| `EMBEDDINGS_PROVIDER` | `service_bge_m3` | `src/adapters/embeddings/bge_m3.py` |
| `SEARCH_ENGINE` | `hybrid_rrf_colbert` | `src/config/constants.py:SearchEngine.HYBRID_RRF_COLBERT` |
| `QDRANT_COLLECTION` | `gdrive_documents_bge` | `src/runtime/graph/config.py:GraphConfig.qdrant_collection` |
| `BGE_M3_URL` | `http://bge-m3:8000` (Compose) | `src/runtime/graph/config.py:GraphConfig.bge_m3_url` |

The `hybrid_rrf_colbert` engine uses Reciprocal Rank Fusion over dense + sparse
results, followed by ColBERT MaxSim late-interaction reranking. It is the best
performing engine in the project (`SearchEngine.HYBRID_RRF_COLBERT` — "Variant A —
BEST" per `src/config/constants.py`).

---

## Qdrant Schema Source of Truth

Collection name: `gdrive_documents_bge`

| Vector name | Type | Size | Distance / comparator |
|---|---|---|---|
| `dense` | dense | 1024 | Cosine |
| `bm42` | sparse | — | IDF modifier (BM42) |
| `colbert` | multivector | 1024 per token | MaxSim |

- Dense vectors: cosine similarity, 1024-dim float32.
- Sparse vectors (`bm42`): token-ID→weight dicts produced by the BGE-M3 sparse head,
  stored in Qdrant sparse format `{indices: [int], values: [float]}`.
- ColBERT multivectors: per-token 1024-dim float32 matrices; scored via MaxSim
  (`(query_vecs @ doc_vecs.T).max(axis=1).sum()`).

Schema setup: `scripts/setup_qdrant_collection.py`, `telegram_bot/setup_qdrant_indexes.py`.
Ingestion writer: `src/ingestion/unified/targets/qdrant_hybrid_target.py`.

---

## BGE-M3 Service Boundary

The BGE-M3 service is a separate Docker sidecar. It is **not** part of the Python
monolith process.

**Location:** `services/bge-m3-api/`

**Runtime:** FastAPI + ONNX Runtime INT8 (`philipchung/bge-m3-onnx`). The service
replaces the `FlagEmbedding.BGEM3FlagModel` Python dependency with a lightweight ONNX
inference session. PyTorch and FlagEmbedding are **not** required at runtime.

**Model:** `BAAI/bge-m3`, revision `5617a9f61b028005a4858fdac845db406aefb181`.
Model files expected at `/models/onnx/model.int8.onnx` (+ `.data` sidecar).
Tokenizer loaded from HuggingFace (config only, no weights) and cached at `/models/hf`.

**Endpoints:**

| Endpoint | Method | Output |
|---|---|---|
| `/health` | GET | `{status, model_loaded, warmed_up}` |
| `/encode/dense` | POST | `dense_vecs: [[float] * 1024]` |
| `/encode/sparse` | POST | `lexical_weights: [{indices, values}]` |
| `/encode/colbert` | POST | `colbert_vecs: [[[float] * 1024]]` |
| `/encode/hybrid` | POST | all three outputs in one call |
| `/rerank` | POST | ColBERT MaxSim reranked results |
| `/metrics` | GET | Prometheus metrics |

The `/encode/hybrid` endpoint is the most efficient path for RAG — it produces all
three vector types in a single forward pass.

**Warmup:** On startup, the service encodes a synthetic warmup query to pre-load the
ONNX session. The `/health` endpoint exposes `warmed_up: bool`.

**Performance configuration:**

| Setting | Default | Env var |
|---|---|---|
| Max token length (docs) | 2048 | `MAX_LENGTH` |
| Max token length (queries) | 256 | `QUERY_MAX_LENGTH` |
| Batch size | 12 | `BATCH_SIZE` |
| ONNX threads | 4 | `OMP_NUM_THREADS` |
| Rerank max docs | 30 | — |
| Memory limit (Compose) | 4 GB | `BGE_M3_MEMORY_LIMIT` |

**Client:** `src/services/bge_m3_client.py` — async (`BGEM3Client`) and sync
(`BGEM3SyncClient`) HTTP clients wrapping the service endpoints.

**Ingestion client:** `BGEM3SyncClient` used by `src/ingestion/unified/qdrant_writer.py`
and `src/ingestion/unified/colbert_backfill.py`.

---

## Redis Cache Role

Redis is a required sidecar. The monolith uses five independent cache layers, all
version-prefixed and with graceful degradation on miss:

| Cache | Key material | TTL |
|---|---|---|
| Semantic answer cache | Query embedding similarity | Configurable |
| Embedding cache | Text + model version | Long-lived |
| Search result cache | Query bundle hash | Medium |
| Rerank cache | Query + doc hashes | Medium |
| Extraction cache | Structured output hash | Long-lived |

Cache implementation: `src/runtime/integrations/cache.py`.
BGE-M3 query bundle cache: `src/services/bge_m3_query_bundle.py` (model `BAAI/bge-m3`,
version `v1`, max length 512).

Redis is configured with `maxmemory-policy volatile-lfu` — keys must have TTLs set to
be eligible for eviction. The monolith sets TTLs on all cache writes.

---

## Docling / Unified Ingestion Path

The canonical indexing path is `src/ingestion/unified/`.

| Property | Value |
|---|---|
| File identity | SHA256 content hash |
| Re-ingestion | Idempotent no-op if hash unchanged |
| Orphan cleanup | Vectors for deleted source files removed from Qdrant |
| Failed documents | Dead-letter queue (DLQ) with retry and backoff |
| Document parsing | Docling sidecar (`services/docling/`) |
| Chunking + embedding writes | CocoIndex (`src/ingestion/unified/targets/qdrant_hybrid_target.py`) |

The unified ingestion CLI is `src/ingestion/unified/cli.py`. It performs a preflight
check against the BGE-M3 service at `$BGE_M3_URL/encode/dense` before ingesting.

ColBERT backfill for collections missing the `colbert` vector:
`src/ingestion/unified/colbert_backfill.py`.

---

## Telegram Adapter Boundary

`telegram_bot/` is the production adapter. It:

- Converts Telegram messages to `AssistantRequest` / `AssistantResult` (defined in
  `src/core/contracts.py`).
- Calls `run_assistant_request` (`src/core/assistant.py`) — the single public
  entrypoint for the RAG core.
- Does **not** own retrieval logic, embedding calls, or Qdrant access directly.
- Hosts the domain layer (apartment search, viewing booking, CRM tools) as a
  replaceable feature set.

The adapter boundary is enforced by import-layering tests in
`tests/contract/test_layering_no_telegram_bot_imports_contract.py` and
`tests/contract/test_runtime_no_telegram_bot_coupling_contract.py`.

---

## Non-goals

The following are explicitly **out of scope** for this baseline:

- **Remote/API embeddings.** Do not migrate to OpenRouter, OpenAI embeddings, or any
  cloud embedding provider. The `LocalBgeM3Provider` and `BgeM3EmbeddingProvider`
  adapters exist for legacy evaluation paths; they do not replace the service-based
  canonical path.
- **Removing ColBERT.** The `colbert` vector and MaxSim reranking are core to the
  retrieval quality of this baseline. Do not remove them.
- **Replacing Qdrant sparse with BM25.** The `bm42` sparse vector is produced by the
  BGE-M3 sparse head (not a separate BM25 index). Do not replace it.
- **Replacing Qdrant.** Qdrant is the only supported vector store for this baseline.
- **Runtime config changes.** This document describes current behavior; no runtime
  changes are made here.
- **Refactoring Qdrant/Redis/Docling code.** Out of scope for this issue.

---

## Follow-up Guardrails

- Any PR that changes `QDRANT_COLLECTION`, `BGE_M3_URL`, or `SEARCH_ENGINE` defaults
  must update this document.
- Any PR that adds a new embeddings provider as a non-optional path must update the
  Decision section and the Canonical Retrieval Profile table.
- The golden E2E test (`make e2e-core-live`) exercises the full canonical path and
  must pass before merging retrieval changes.
- The `bge_m3_full` profile must remain the default retrieval profile. Changes to the
  default require a separate ADR.
