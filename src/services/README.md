# src/services/

Low-level, shared service **clients** for the `src/` domain layer. Lazy-imported so heavy
dependencies aren't loaded at import time — import a specific client directly for best
performance (e.g. `from src.services.bge_m3_client import BGEM3SyncClient`).

## Files

| File | Purpose |
|------|---------|
| [`bge_m3_client.py`](./bge_m3_client.py) | BGE-M3 embeddings HTTP client (`BGEM3Client` / `BGEM3SyncClient`) |
| [`bge_m3_query_bundle.py`](./bge_m3_query_bundle.py) | Query-side dense+sparse+ColBERT bundle helper |
| [`vectorizers.py`](./vectorizers.py) | Vectorizer helpers over the embedding clients |
| [`kommo_client.py`](./kommo_client.py) · [`kommo_tokens.py`](./kommo_tokens.py) · [`kommo_models.py`](./kommo_models.py) | Kommo CRM REST client, token store, and models |
| [`handoff_state.py`](./handoff_state.py) | Human-handoff (HITL) state helper |
| [`content_loader.py`](./content_loader.py) | Content-loading helper |
| [`_retry.py`](./_retry.py) | Shared retry wrapper |

## Boundaries

- **Low-level SDK clients only.** The application-facing embedding layer is
  [`../adapters/embeddings/`](../adapters/embeddings/) — runtime retrieval depends on those
  providers, which in turn wrap these clients.
- Clients are I/O wrappers: no pipeline orchestration, no Qdrant collection management.

## See Also

- [`../adapters/README.md`](../adapters/README.md) — provider adapters that wrap these clients
- [`../README.md`](../README.md) — `src/` overview
