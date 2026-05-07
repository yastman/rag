# Qdrant Stack

Current Qdrant setup used by bot and ingestion flows.

## Version And Endpoints

- Compose image: `qdrant/qdrant:v1.17.0` (pinned by digest in compose files)
- Python SDK: `qdrant-client>=1.17.0` (v1.17+ adds weighted RRF, relevance feedback)
- HTTP: `http://localhost:6333`
- gRPC: `localhost:6334`

## Primary Collections

- Default runtime collection: `gdrive_documents_bge`
- Alias: `gdrive_documents_bge_active` → `gdrive_documents_bge` (blue/green cutover ready)
- Additional collections may exist for evaluation or legacy flows.

## Collection Naming Policy

Defined in `src/config/qdrant_policy.py` (`resolve_collection_name`):

| Mode | Suffix | Example |
|------|--------|---------|
| `off` (default) | none | `gdrive_documents_bge` |
| `scalar` | `_scalar` | `gdrive_documents_bge_scalar` |
| `binary` | `_binary` | `gdrive_documents_bge_binary` |

Rules:
- Any existing `_binary` or `_scalar` suffix is stripped from the base name before applying the new mode suffix.
- This prevents double suffixes like `gdrive_documents_bge_scalar_binary`.

## Vector Schema (Unified Bootstrap)

Collection bootstrap (`src/ingestion/unified/cli.py bootstrap`) creates:

- Dense vector: name `dense`, size `1024`, cosine distance
- Multivector rerank field: name `colbert`, size `1024`, MaxSim comparator
- Sparse vector: name `bm42`, IDF modifier

## Payload-Index Contract Matrix

The table below shows which payload indexes each origin creates, their Qdrant schema type, and where they are used in filters or queries.

### Legend

- **Origin:**
  - `unified` — `src/ingestion/unified/cli.py bootstrap`
  - `legacy` — `scripts/setup_qdrant_collection.py`
  - `ensure` — `scripts/qdrant_ensure_indexes.py` (idempotent fallback/ensure)
  - `scalar` — `scripts/setup_scalar_collection.py`
  - `binary` — `scripts/setup_binary_collection.py`
  - `apartment` — `telegram_bot/setup_qdrant_indexes.py` and `src/ingestion/indexer.py`
- **Type:** Qdrant `PayloadSchemaType` (`keyword`, `integer`, `float`, `bool`)
- **Runtime use:** Where the field is actively referenced in filters, `group_by`, or `order_by`

### Unified / Legacy / Ensure (document chunking)

| Field | Type | unified | legacy | ensure | Runtime use |
|-------|------|:-------:|:------:|:------:|-------------|
| `file_id` (flat) | `keyword` | ✓ | ✓ | ✓ | `qdrant_writer.delete_file` — count + delete filter |
| `metadata.file_id` | `keyword` | ✓ | ✓ | ✓ | `qdrant_writer.delete_file` — count + delete filter |
| `metadata.doc_id` | `keyword` | ✓ | ✓ | ✓ | `small_to_big` grouping; `retrieve.py` `group_by` |
| `metadata.source` | `keyword` | ✓ | ✓ | ✓ | Citation source resolution |
| `metadata.file_name` | `keyword` | ✓ | ✓ | ✓ | — |
| `metadata.mime_type` | `keyword` | ✓ | ✓ | ✓ | — |
| `metadata.topic` | `keyword` | ✓ | ✓ | ✓ | `qdrant_writer` sets via `classify_chunk_topic` |
| `metadata.doc_type` | `keyword` | ✓ | ✓ | ✓ | `qdrant_writer` sets via `classify_doc_type` |
| `metadata.source_type` | `keyword` | ✓ | — | — | `qdrant_writer` infers from path/extension |
| `metadata.jurisdiction` | `keyword` | ✓ | — | — | `qdrant_writer` infers from file metadata |
| `metadata.audience` | `keyword` | ✓ | — | — | `qdrant_writer` infers from path + text |
| `metadata.language` | `keyword` | ✓ | — | — | `qdrant_writer` infers from path |
| `metadata.order` | `integer` | ✓ | ✓ | ✓ | `small_to_big` `order_by` for neighbor chunks |
| `metadata.chunk_id` | `integer` | ✓ | ✓ | ✓ | — |

### Scalar / Binary (quantized evaluation collections)

| Field | Type | scalar | binary | Runtime use |
|-------|------|:------:|:------:|-------------|
| `file_id` (flat) | `keyword` | ✓ | ✓ | Same as above |
| `metadata.file_id` | `keyword` | ✓ | ✓ | Same as above |
| `metadata.doc_id` | `keyword` | ✓ | ✓ | Same as above |
| `metadata.source` | `keyword` | ✓ | ✓ | Same as above |
| `metadata.chunk_order` | `integer` | ✓ | ✓ | Alias for `metadata.order` |
| `metadata.document_name` | `keyword` | ✓ | ✓ | — |
| `metadata.article_number` | `keyword` | ✓ | ✓ | — |
| `metadata.city` | `keyword` | ✓ | ✓ | Apartment search keyword match |
| `metadata.source_type` | `keyword` | ✓ | ✓ | — |
| `metadata.topic` | `keyword` | ✓ | ✓ | Same as above |
| `metadata.doc_type` | `keyword` | ✓ | ✓ | Same as above |
| `metadata.jurisdiction` | `keyword` | ✓ | ✓ | — |
| `metadata.audience` | `keyword` | ✓ | ✓ | — |
| `metadata.language` | `keyword` | ✓ | ✓ | — |
| `metadata.price` | `integer` | ✓ | ✓ | Apartment search range filter |
| `metadata.rooms` | `integer` | ✓ | ✓ | Apartment search range/exact filter |
| `metadata.area` | `integer` | ✓ | ✓ | Apartment search range filter |
| `metadata.floor` | `integer` | ✓ | ✓ | Apartment search range/exact filter |
| `metadata.floors` | `integer` | ✓ | ✓ | — |
| `metadata.distance_to_sea` | `integer` | ✓ | ✓ | Apartment search range filter |
| `metadata.bathrooms` | `integer` | ✓ | ✓ | Apartment search exact filter |
| `metadata.chunk_id` | `integer` | ✓ | ✓ | — |
| `metadata.order` | `integer` | ✓ | ✓ | Same as above |
| `metadata.furnished` | `bool` | — | ✓ | Apartment search exact match (bool) |
| `metadata.year_round` | `bool` | — | ✓ | Apartment search exact match (bool) |

### Apartment / CSV-only indexes

Created by `telegram_bot/setup_qdrant_indexes.py` and `src/ingestion/indexer.py`. These fields are populated by CSV apartment ingestion and used by the apartment search pipeline.

| Field | Type | setup_qdrant_indexes | indexer | Runtime use |
|-------|------|:--------------------:|:-------:|-------------|
| `metadata.source_type` | `keyword` | ✓ | ✓ | Source type discrimination |
| `metadata.jurisdiction` | `keyword` | ✓ | ✓ | — |
| `metadata.audience` | `keyword` | ✓ | ✓ | — |
| `metadata.language` | `keyword` | ✓ | ✓ | — |
| `metadata.city` | `keyword` | ✓ | ✓ | `filter_extractor._extract_city`; `query_analyzer` |
| `metadata.price` | `integer` | ✓ | ✓ | `filter_extractor._extract_price`; `query_analyzer` |
| `metadata.rooms` | `integer` | ✓ | ✓ | `filter_extractor._extract_rooms`; `query_analyzer` |
| `metadata.area` | `float` | ✓ | `integer` | `filter_extractor._extract_area`; `query_analyzer` |
| `metadata.floor` | `integer` | ✓ | ✓ | `filter_extractor._extract_floor`; `query_analyzer` |
| `metadata.distance_to_sea` | `integer` | ✓ | ✓ | `filter_extractor._extract_distance_to_sea`; `query_analyzer` |
| `metadata.maintenance` | `float` | ✓ | — | `filter_extractor._extract_maintenance`; `query_analyzer` |
| `metadata.bathrooms` | `integer` | ✓ | ✓ | `filter_extractor._extract_bathrooms`; `query_analyzer` |
| `metadata.furniture` | `keyword` | ✓ | — | `filter_extractor._extract_furniture`; `query_analyzer` |
| `metadata.year_round` | `keyword` | ✓ | `bool` | `filter_extractor._extract_year_round`; `query_analyzer` |

**Important discrepancies:**
- `metadata.area` is `float` in `setup_qdrant_indexes.py` but `integer` in `indexer.py`, `setup_scalar_collection.py`, and `setup_binary_collection.py`.
- `metadata.furniture` (keyword, "Есть") is created by `setup_qdrant_indexes.py`, while `indexer.py` and `setup_binary_collection.py` create `metadata.furnished` (bool). The runtime apartment pipeline uses `is_furnished` (bool) in dialog filters and `furniture` (string) in the heuristic extractor.
- `metadata.maintenance` (float) is only created by `setup_qdrant_indexes.py`; none of the scalar/binary/indexer scripts index it.

## Runtime-Required vs Legacy-Only Fields

**Runtime-required** (bot and unified ingestion depend on these):
- `file_id` (flat) — fast delete
- `metadata.file_id` — delete/count filter
- `metadata.doc_id` — small-to-big grouping
- `metadata.order` — small-to-big neighbor sorting
- `metadata.source` — citation resolution

**Legacy / CSV / apartment-only** (not used by unified document ingestion):
- `metadata.city`, `metadata.price`, `metadata.rooms`, `metadata.area`, `metadata.floor`, `metadata.distance_to_sea`, `metadata.bathrooms`, `metadata.furniture`/`furnished`, `metadata.year_round`, `metadata.maintenance`
- `metadata.article_number`, `metadata.document_name`

**Best-effort / classifier-populated** (unified ingestion writes these, but bot does not filter on them today):
- `metadata.topic`, `metadata.doc_type`, `metadata.jurisdiction`, `metadata.audience`, `metadata.language`, `metadata.source_type`

## Bot Fallback Behavior

`telegram_bot/services/qdrant.py` (`QdrantService.ensure_collection()`):

1. **Validation:** On first search, lists collections and checks whether the computed collection name (base + quantization suffix) exists.
2. **Fallback to base:** If the suffixed collection is missing but the base collection exists, the service logs a warning and falls back to the base name, resetting `quantization_mode` to `"off"`.
3. **Alias management:** After validation (or fallback), `_ensure_alias()` creates or updates `{collection_name}_active` → current collection name. If the alias already points to the same collection, it is skipped; otherwise it is deleted and recreated.
4. **Strict mode:** After successful collection resolution, `_apply_strict_mode()` sets server-side limits (`max_query_limit=100`, `max_timeout=30`, `search_max_hnsw_ef=512`).

All three steps are non-blocking: failures are logged as warnings and do not prevent startup.

## Strict Mode

Collection-level guardrails applied at bot startup via `QdrantService._apply_strict_mode()`:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `enabled` | `True` | Enforce limits server-side |
| `max_query_limit` | `100` | Cap result-set size |
| `max_timeout` | `30` | Prevent runaway queries (seconds) |
| `search_max_hnsw_ef` | `512` | Cap HNSW exploration factor |

Non-blocking: warns on failure, does not prevent startup.

## Aliases

`QdrantService._ensure_alias()` creates `{collection}_active` alias on startup.
Pattern enables zero-downtime blue/green cutover: atomically swap alias to new collection
via `update_collection_aliases()` without bot restart.

## ColBERT Observability (Runtime Metrics)

Structured log metrics emitted to the logger with `extra={"metric_name": ..., "value": 1}`:

| Metric | Location | When |
|--------|----------|------|
| `colbert_rerank_attempted` | `rag_pipeline._hybrid_retrieve()` | ColBERT path selected |
| `retrieval_zero_docs` | `rag_pipeline._hybrid_retrieve()` | Search returns empty |
| `colbert_rerank_empty` | `qdrant.hybrid_search_rrf_colbert()` | ColBERT results empty |
| `colbert_fallback_to_rrf` | `qdrant.hybrid_search_rrf_colbert()` | Falling back to plain RRF |

Preflight also logs ColBERT point-level coverage: `"Preflight Qdrant: colbert coverage %.2f%% (%d/%d)"` — warn threshold `COLBERT_COVERAGE_WARN_THRESHOLD = 0.995`.

## Setup And Validation

```bash
# Create ingestion-ready collection if missing
uv run python -m src.ingestion.unified.cli bootstrap

# Fail-fast guard: require ColBERT in existing/new runtime schema
uv run python -m src.ingestion.unified.cli bootstrap --require-colbert

# Validate vector schema (fail if colbert missing)
uv run python -m src.ingestion.unified.cli schema-check --require-colbert

# Check point-level ColBERT coverage (>=99.5% recommended, 100% target)
uv run python -m src.ingestion.unified.cli coverage-check --min-ratio 0.995

# Backfill missing point-level ColBERT vectors
uv run python -m src.ingestion.unified.cli backfill-colbert --batch-size 32 --resume

# Dry-run sample before writes
uv run python -m src.ingestion.unified.cli backfill-colbert --dry-run --limit 1000
# Check collection
curl -fsS http://localhost:6333/collections/gdrive_documents_bge | python3 -m json.tool

# Check service readiness
curl -fsS http://localhost:6333/readyz
```

## Feature Decisions (2026-02-24)

| Feature | Status | Notes |
|---------|--------|-------|
| **FormulaQuery** (exp_decay freshness boost) | Implemented, not wired | `search_with_score_boosting()` ready; wire when product needs freshness ranking. See #590. |
| **ACORN** (filtered search optimization) | SDK available, evaluation-only | In search benchmark engines; connect to production when filtered recall needs improvement. See #590. |
| **Strict Mode** | Active at startup | `QdrantService._apply_strict_mode()` — non-blocking warn on error. |
| **Aliases** | Active at startup | `QdrantService._ensure_alias()` — non-blocking warn on error. |
| **ColBERT preflight coverage** | Active | Warns if coverage < 99.5%; see `preflight.py`. |

## Backups

```bash
make qdrant-backup
```

Snapshots are created via `scripts/qdrant_snapshot.py`.

## Runtime Integration Points

- Bot retrieval: `telegram_bot/services/qdrant.py`
- Unified ingestion writes: `src/ingestion/unified/qdrant_writer.py`
- Ingestion target connector: `src/ingestion/unified/targets/qdrant_hybrid_target.py`

## Troubleshooting

- Empty retrieval results: verify `QDRANT_COLLECTION` matches existing collection.
- Ingestion writes fail: run `src.ingestion.unified.cli preflight` to confirm reachability.
- Collection exists but has `0 points`: verify the Google Drive sync directory is populated before treating this as a Qdrant issue.
- On VPS, host `localhost:6333` may be unavailable when Qdrant is only exposed inside the Docker network; inspect from a sibling container or use `docker compose exec`.
- ColBERT schema drift: run `src.ingestion.unified.cli schema-check --require-colbert`.
- Low ColBERT coverage: run `src.ingestion.unified.cli coverage-check --min-ratio 0.995`.
- Interrupted backfill: rerun `src.ingestion.unified.cli backfill-colbert --resume` to continue from `.colbert_backfill_checkpoint.json`.
- Slow queries: verify collection contains expected `dense`/`bm42` vectors and payload indexes.
- Strict mode errors: check `max_query_limit` (100) and `max_timeout` (30s) if queries are being rejected.
