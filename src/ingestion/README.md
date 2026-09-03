# src/ingestion/

Document ingestion: parsing, chunking, embedding, and indexing into Qdrant.

## Purpose

Turn raw documents into searchable vector chunks. Production ingestion is
**Markdown-only** (#3235): exactly `.md` files, parsed by a stdlib parser.

1. **Current path** (`unified/`) — incremental pipeline with deterministic file identity (content-hash manifest) and replace semantics. CocoIndex was removed (#2834); Docling was removed (#3235); the pipeline now drives Markdown → BGE-M3 → Qdrant directly.
2. **Local helpers** (`chunker.py`) — the shared `Chunk` dataclass used by the writer and scripts.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| `src.ingestion.unified.cli` | Unified pipeline CLI: `run` (+`--watch`), `preflight`, `bootstrap`, `schema-check`, `coverage-check`, `backfill-colbert` |
| `src.ingestion.unified.flow` `run_once()` / `run_watch()` | Pipeline assembly and execution (reads `SYNC_DIR`) |
| `src.ingestion.unified.qdrant_writer` `QdrantHybridWriter` | Writes hybrid vectors (dense + sparse + ColBERT) to Qdrant |

## Key Files

| File | Purpose |
|------|---------|
| [`chunker.py`](./chunker.py) | Shared `Chunk` dataclass (generic ingestion contract) |
| [`markdown.py`](./markdown.py) | Markdown-only parser: UTF-8 read, heading/size splitting, Chunk conversion (#3235) |
| [`unified/config.py`](./unified/config.py) | Unified pipeline configuration |
| [`unified/flow.py`](./unified/flow.py) | Pipeline definition (`run_once` / `run_watch`) |
| [`unified/manifest.py`](./unified/manifest.py) | Content-hash-based stable file identity |
| [`unified/qdrant_writer.py`](./unified/qdrant_writer.py) | Qdrant upsert/delete with payload contract |
| [`unified/colbert_backfill.py`](./unified/colbert_backfill.py) | Backfill ColBERT vectors for existing points |

## Boundaries

- **Ingestion determinism and resumability** are critical. File identity uses content hashes (`manifest.py`); renames/moves do not create duplicates.
- **Do not change collection schema**, manifest hashing, or payload contract without updating downstream retrieval assumptions.
- `QdrantHybridWriter` enforces replace semantics: a file re-ingestion deletes old chunks before inserting new ones.

## Related Runtime Services

- **Qdrant** — target vector database (also the source of truth for idempotency via the content-hash manifest)
- **BGE-M3** — dense + sparse + ColBERT embeddings
- **Markdown-only parsing** (#3235) — stdlib `MarkdownParser`; no converter service or SDK; exactly `.md` is accepted

## Focused Checks

```bash
# Check dependencies are reachable (Qdrant, BGE-M3, sync dir)
python -m src.ingestion.unified.cli preflight

# Create the Qdrant collection if missing
python -m src.ingestion.unified.cli bootstrap

# Validate collection schema (dense / bm42 / colbert)
python -m src.ingestion.unified.cli schema-check

# Tests
pytest src/ingestion/unified/
make check
```

## See Also

- [`./unified/AGENTS.override.md`](./unified/AGENTS.override.md) — Ingestion-specific scope rules and validation
- [`./unified/README.md`](./unified/README.md) — Detailed unified pipeline docs
- [`../retrieval/`](../retrieval/) — Search engines that consume ingested data
- [`../../DOCKER.md`](../../DOCKER.md) — Docker orchestration and service dependencies
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../../docs/runbooks/README.md`](../../docs/runbooks/README.md) — Operational troubleshooting
- [`../../docs/INGESTION.md`](../../docs/INGESTION.md) — Unified ingestion guide and troubleshooting
- [`../../docs/engineering/test-writing-guide.md`](../../docs/engineering/test-writing-guide.md) — Test conventions
