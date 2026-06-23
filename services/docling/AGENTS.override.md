# AGENTS.override.md

## Scope
- Applies to `services/docling/**`.
- Extends root `AGENTS.md` and `services/AGENTS.override.md` for the Docling document parsing service.

## Local Rules
- The container runs `docling-serve`; this directory owns the `Dockerfile` and image-level configuration only.
- Keep image base, `UVICORN_PORT`, `DOCLING_BACKEND`, and accurate-table mode aligned with what `compose.yml` and the ingestion pipeline expect.
- Preserve volume mount expectations (`./data/docling`, `docling_cache`); do not introduce hidden persistent state.

## Required Validation
- Unit tests: `uv run pytest tests/unit/test_docling*.py -q`.
- Dockerfile sync: `uv run pytest tests/unit/test_dockerfile_docling_sync.py -q`.
- After image-pin updates: `make verify-compose-images`.

## Guardrails
- Do not change `UVICORN_PORT`, healthcheck path, or volume layout without updating `compose.yml` and ingestion tests.
- Treat the container root as read-only at runtime — write paths must go to mounted volumes.

## References
- `services/docling/README.md`
- `services/AGENTS.override.md`
- `docs/INGESTION.md`
- root `AGENTS.md`
