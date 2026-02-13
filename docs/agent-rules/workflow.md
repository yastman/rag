# Workflow Guide

## Default Development Loop
1. Read current context (`README.md`, `CLAUDE.md`, nearest AGENTS file).
2. Implement focused change in smallest useful scope.
3. Run validation commands for affected area.
4. Update docs/tests with behavior changes.

## Core Commands
- Setup: `uv sync`
- Quick gate: `make check`
- Unit tests: `make test-unit`
- Full tests: `make test`

## Service Stack Commands
- Start core stack: `make docker-up`
- Start core + bot: `make docker-bot-up`
- Start full stack: `make docker-full-up`
- Monitoring stack: `make monitoring-up`

## Ingestion Commands
- One-shot ingestion: `make ingest-unified`
- Watch mode: `make ingest-unified-watch`
- Status: `make ingest-unified-status`
- CLI: `python -m src.ingestion.unified.cli preflight|bootstrap|run|status|reprocess`

## Retrieval/Quality Commands
- Graph path tests: `uv run pytest tests/integration/test_graph_paths.py -v`
- Trace validation: `make validate-traces-fast`
- RAG eval: `make eval-rag`

## When To Use Scoped Overrides
- `telegram_bot/AGENTS.override.md`: graph/service logic and observability in bot runtime.
- `src/ingestion/unified/AGENTS.override.md`: ingestion flow/state/writer stability.
- `k8s/AGENTS.override.md`: manifests, overlays, deployment policies.
- `docs/AGENTS.override.md`: documentation hygiene and canonical doc strategy.
