# AGENTS.override.md

## Scope
- Applies to `telegram_bot/**`.
- Extends root `AGENTS.md` with bot-specific constraints.

## Local Rules
- Preserve pipeline contract shapes (`PreAgentStateContract` fields in
  `telegram_bot/pipelines/state_contract.py`, routing assumptions).
- Keep service boundaries intact:
  - `telegram_bot/services/` for business logic.
  - `telegram_bot/integrations/` for wrappers/adapters.
  - `src/runtime/graph/nodes/` for classify/guard/transcribe steps.
- Avoid mixing transport-layer Telegram handling with retrieval/domain logic.
- There is no `telegram_bot/graph/` tree: it was removed in #3220 along with
  the graph-compat facade; route new work through assistant-core
  (`src.core.assistant`) and `src/runtime/pipeline/`.

## Required Validation
- Always run fast checks:
  - `make check`
  - `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- For pipeline/supervisor flow edits, run `make test-core` plus the
  no-service integration/smoke lane (`make test-no-service-lane`).
- For cache/search/rerank behavior edits, run targeted suites from `tests/unit/` and affected integration tests.

## Observability
- Keep existing tracing patterns consistent (`telegram_bot/observability/` package, no-op shims — Langfuse removed #2844).
- Do not remove score/trace instrumentation without explicit reason and replacement.

## References
- `telegram_bot/README.md`
- `docs/README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `DOCKER.md`
