# AGENTS.override.md

## Scope
- Applies to `telegram_bot/**`.
- Extends root `AGENTS.md` with bot-specific constraints.

## Local Rules
- Preserve LangGraph node contract shapes (`state` fields, routing assumptions).
- Keep service boundaries intact:
  - `telegram_bot/services/` for business logic.
  - `telegram_bot/integrations/` for wrappers/adapters.
  - `telegram_bot/graph/nodes/` for pipeline steps.
- Avoid mixing transport-layer Telegram handling with retrieval/domain logic.

## Required Validation
- Always run fast checks:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- For graph flow edits, run:
  - `uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q`
- For cache/search/rerank behavior edits, run targeted suites from `tests/unit/` and affected integration tests.

## Observability
- Keep existing tracing patterns consistent (`telegram_bot/observability.py`).
- Do not remove score/trace instrumentation without explicit reason and replacement.

## References
- `telegram_bot/README.md`
- `docs/PIPELINE_OVERVIEW.md`
- `docs/agent-rules/workflow.md`
- `docs/agent-rules/testing-and-validation.md`
- `docs/agent-rules/architecture-map.md`
