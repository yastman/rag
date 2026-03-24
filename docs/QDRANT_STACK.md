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

## Vector Schema (Unified Bootstrap)

Collection bootstrap (`src/ingestion/unified/cli.py bootstrap`) creates:

- Dense vector: name `dense`, size `1024`, cosine distance
- Multivector rerank field: name `colbert`, size `1024`, MaxSim comparator
- Sparse vector: name `bm42`, IDF modifier

Payload indexes created by bootstrap include:
- `file_id`
- `metadata.file_id`
- `metadata.doc_id`
- `metadata.source`
- `metadata.file_name`
- `metadata.mime_type`
- `metadata.order`
- `metadata.chunk_id`

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
