# AGENTS.override.md

## Scope
- Applies to `src/ingestion/unified/**`.
- Extends root `AGENTS.md` with ingestion-specific rules.

## Local Rules
- Keep pipeline deterministic and resumable (state tracking and manifest identity must stay stable).
- Preserve sync-safe behavior in writer/state paths used by ingestion runtime.
- Maintain compatibility between:
  - `flow.py`
  - `qdrant_writer.py`
  - `state_manager.py`
  - `targets/qdrant_hybrid_target.py`

## Required Validation
- Base checks:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- Ingestion functional checks when behavior changes:
  - `make ingest-unified-status`
  - `python -m src.ingestion.unified.cli preflight`
- If flow semantics changed, run one controlled ingestion pass in dev:
  - `make ingest-unified`

## Guardrails
- Do not silently alter collection names, manifest hashing, or file identity semantics.
- Prefer additive config changes over breaking defaults.

## References
- `docs/INGESTION.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/PIPELINE_OVERVIEW.md`
- `src/ingestion/unified/cli.py`
