# AGENTS.override.md

## Scope
- Applies to `src/ingestion/unified/**`.
- Extends root `AGENTS.md` with ingestion-specific rules.

## Local Rules
- Keep ingestion deterministic and idempotent (manifest identity + Qdrant content-hash dedup must stay stable).
- Preserve sync-safe behavior in the writer path used by ingestion runtime.
- Maintain compatibility between:
  - `flow.py`
  - `qdrant_writer.py`

## Required Validation
- Base checks:
  - `make check`
  - `make test-ingest-extra`
- Ingestion functional checks when behavior changes:
  - `python -m src.ingestion.unified.cli preflight`
- If flow semantics changed, run one controlled ingestion pass in dev:
  - `python -m src.ingestion.unified.cli run`

## Guardrails
- Do not silently alter collection names, manifest hashing, or file identity semantics.
- Prefer additive config changes over breaking defaults.

## References
- `docs/INGESTION.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/PIPELINE_OVERVIEW.md`
- `src/ingestion/unified/cli.py`
