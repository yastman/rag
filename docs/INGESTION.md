# Ingestion

How documents get from a source file into the Qdrant store the RAG spine retrieves from.
The deterministic, idempotent, production path lives in `src/ingestion/unified/` — see
[`../src/ingestion/README.md`](../src/ingestion/README.md) and
[`../src/ingestion/unified/AGENTS.override.md`](../src/ingestion/unified/AGENTS.override.md).

## Pipeline

```
source file → Docling (in-process, native SDK) → chunk + embed (BGE-M3: dense + sparse + ColBERT) → Qdrant upsert
```

- **Docling** runs in-process inside the ingestion container (native SDK, no HTTP sidecar or
  `DOCLING_URL`). PDF and other format parsing happens directly without a separate service.
- The **unified pipeline** owns chunking and the embedding writes; **BGE-M3** serves
  embeddings — see [`../services/bge-m3-api/README.md`](../services/bge-m3-api/README.md).

## Guarantees

- **SHA256 file identity** — re-ingesting an unchanged file is a no-op.
- **Idempotent upsert** — a changed file replaces its prior chunks by source path.
- **Error handling** — failed documents are logged and skipped; `run_watch` retries on the next polling cycle (60 s). No DLQ, no exponential backoff.

**Known limitation:** deleting a source file does **not** remove its chunks from Qdrant;
they remain until manual cleanup.

## Run it

```bash
make core-up          # BGE-M3 + Qdrant must be up (see ../docs/LOCAL-DEVELOPMENT.md)
```

Ingestion entry points and scripts live under `scripts/` (see
[`../scripts/README.md`](../scripts/README.md)) and `src/ingestion/`. Qdrant collection
setup/audit: `make qdrant-audit-indexes`.
