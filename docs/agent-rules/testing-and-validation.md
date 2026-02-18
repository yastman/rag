# Testing And Validation

## Baseline Required Checks
Run these for most code changes:
- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

Run full test suite when touching cross-cutting logic:
- `make test-full`

## Docs-Only Changes
- If change scope is only documentation/plans (no runtime/test/infra code changes), full test gates are not required.
- Required checks for docs-only changes:
  - Ensure commands in docs match `Makefile` or real CLI modules.
  - Ensure referenced files/paths exist.
  - Ensure date/version-sensitive SDK/API claims are verified against primary sources.

## Bot And Graph Changes
- Always run:
  - `uv run pytest tests/integration/test_graph_paths.py -v`
- Add targeted unit/integration tests for changed nodes/services.

## Ingestion Changes
- Minimum checks:
  - `python -m src.ingestion.unified.cli preflight`
  - `make ingest-unified-status`
- For behavior changes in flow/writer/state, run one dev ingestion pass:
  - `make ingest-unified`

## Retrieval And Ranking Changes
- Run affected retrieval tests in `tests/`.
- Re-run graph path tests.
- If quality expectations changed, execute:
  - `make eval-rag`

## Infra/Deployment Changes
- Local compose changes: bring up affected profile and confirm health.
- k3s changes: deploy affected overlay and check pod state.

## Observability Validation
- For tracing changes, run:
  - `make validate-traces-fast`
- Verify that critical spans/scores remain present in Langfuse-driven outputs.

## Documentation Validation
- Ensure commands in docs match `Makefile` or real CLI modules.
- Ensure references in AGENTS docs point to existing files.
