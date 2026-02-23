# Qdrant Stack

Current Qdrant setup used by bot and ingestion flows.

## Version And Endpoints

- Compose image: `qdrant/qdrant:v1.16.2` (pinned by digest in compose files)
- HTTP: `http://localhost:6333`
- gRPC: `localhost:6334`

## Primary Collections

- Default runtime collection: `gdrive_documents_bge`
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

## Setup And Validation

```bash
# Create ingestion-ready collection if missing
uv run python -m src.ingestion.unified.cli bootstrap

# Validate vector schema (fail if colbert missing)
uv run python -m src.ingestion.unified.cli schema-check --require-colbert

# Check point-level ColBERT coverage (>=99.5% recommended, 100% target)
uv run python -m src.ingestion.unified.cli coverage-check --min-ratio 0.995

# Backfill missing point-level ColBERT vectors
uv run python -m src.ingestion.unified.cli backfill-colbert --batch-size 32 --resume

# Dry-run sample before writes
uv run python -m src.ingestion.unified.cli backfill-colbert --dry-run --limit 1000

# Check collection
curl -fsS http://localhost:6333/collections/gdrive_documents_bge | python -m json.tool

# Check service readiness
curl -fsS http://localhost:6333/readyz
```

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
- ColBERT schema drift: run `src.ingestion.unified.cli schema-check --require-colbert`.
- Low ColBERT coverage: run `src.ingestion.unified.cli coverage-check --min-ratio 0.995`.
- Interrupted backfill: rerun `src.ingestion.unified.cli backfill-colbert --resume` to continue from `.colbert_backfill_checkpoint.json`.
- Slow queries: verify collection contains expected `dense`/`bm42` vectors and payload indexes.
