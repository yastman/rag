# Docling Document Parsing Service

Standalone container running `docling-serve` for converting PDFs and other documents into structured markdown/HTML.

## Purpose

Feeds the unified ingestion pipeline with structured text extracted from uploaded or synced documents.

## Entrypoint

- **Application**: `docling-serve` (Docling CLI serve mode, configured via environment)
- **Dockerfile**: [`Dockerfile`](Dockerfile)

## Docker

- **Service name**: `docling`
- **Profile**: — (default, unprofiled)
- **Compose project**: `dev` (see [`../../DOCKER.md`](../../DOCKER.md) for contract details)
- **Local port**: `5001` (mapped in `compose.dev.yml`)
- **Health**: `GET http://localhost:5001/health`

## Quick Start

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose up -d docling
curl -fsS http://localhost:5001/health
```

## Tests & Checks

```bash
# Unit tests
uv run pytest tests/unit/test_docling*.py -v

# Dockerfile sync validation
uv run pytest tests/unit/test_dockerfile_docling_sync.py -v
```

## Owner Boundaries

- Document conversion backend (`dlparse_v2` PDF backend, accurate table mode)
- No persistent application state; relies on `./data/docling` volume mount and `docling_cache` volume

Do not change `UVICORN_PORT`, `DOCLING_BACKEND`, or volume mounts without updating `compose.yml` and ingestion pipeline tests.
