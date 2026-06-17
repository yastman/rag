# ADR-0020: Orchestration Monolith — BGE-M3 and Docling Stay as Separate Services

**Status:** Accepted
**Date:** 2026-06-17
**Issue:** #2609 (gate for ARCH-13+ block, epic #2596)
**Supersedes:** The "in-process embeddings + in-process Docling" language in
`product-simplification-e2e-plan.md` and `product-simplification-stage-0-decisions.md`.

## Context

Earlier plan documents (Stage 0 decisions, e2e plan) described BGE-M3 embeddings
and Docling as running **inside the monolith process** without a required separate
service. Repo validation (see issue #2609) established that:

1. The SDK boundary already exists: `src/adapters/embeddings/service_bge_m3.py`
   is an HTTP client; `src/ingestion/docling_client.py` is an HTTP client.
2. The BGE-M3 service uses ONNX (not torch/FlagEmbedding) — keeping it
   in-process would pull a large ML runtime into the bot/core process.
3. `docling-serve run` is the documented production HTTP-service mode;
   in-process use is the library/dev path.
4. For a ≤3-engineer system, orchestration monolith + embedding/parse as
   separate services (resource isolation, independent restart, no lockfile
   bloat) is the established best practice.

## Decision

The target is an **orchestration monolith**, NOT an ML monolith:

```
telegram_bot + src/core + src/runtime pipeline + business logic + SDK clients
  → BGE-M3  : separate service  (services/bge-m3-api, ONNX)
               thin client in monolith: src/adapters/embeddings/service_bge_m3.py
  → Docling : separate service  (services/docling, docling-serve HTTP)
               thin client in monolith: src/ingestion/docling_client.py
  → Qdrant / Redis / Postgres : infra services (unchanged)
```

Heavy ML runtimes and document-parsing runtimes stay **outside** the bot/core
process. The monolith holds only thin SDK clients for those services.

### Embeddings provider default

`EMBEDDINGS_PROVIDER=service_bge_m3` is the production default.
`local_bge_m3` is valid for test/offline/dev fallback only and must be
annotated as such in `.env.example`.

### Docling backend default

`DOCLING_BACKEND=docling_http` is the production default.
`docling_native` (in-process library) is the dev/offline fallback only.

### Hybrid endpoint preference

Prefer `/encode/hybrid` on the BGE-M3 service (single forward pass, ~3× faster)
over separate dense + sparse + ColBERT calls in ingestion and query paths.

## Consequences

- In-process embedding and in-process Docling parsing are **not** the production
  path; they are fallbacks for offline/dev scenarios.
- `.env.example` must reflect `service_bge_m3` as the default (or clearly
  annotate `local_bge_m3` as test/legacy-only).
- Plan documents that describe "эмбеддинги внутри процесса" (embeddings
  in-process) as the production target are superseded by this ADR.
- No lockfile or dependency changes required — the SDK clients already exist.
- BGE-M3 and Docling services are required for production and VPS runs; they
  remain optional for minimal core E2E tests that use a local fallback path.

## Current Implementation Notes

| Component | File | Role |
|---|---|---|
| BGE-M3 HTTP client | `src/adapters/embeddings/service_bge_m3.py` | Production embedding path |
| BGE-M3 local fallback | `src/adapters/embeddings/bge_m3.py` | Dev/offline only |
| Docling HTTP client | `src/ingestion/docling_client.py` | Production parse path |
| Docling native fallback | `src/ingestion/docling_native.py` | Dev/offline only |
| BGE-M3 service | `services/bge-m3-api/` | Separate ONNX service |
| Docling service | `services/docling/` | Separate docling-serve service |
| Client unit tests | `tests/unit/services/test_bge_m3_client.py` | Validates HTTP client |
