***REMOVED*** AGENTS.override.md

***REMOVED******REMOVED*** Scope
- Applies to `telegram_bot/**`.
- Extends root `AGENTS.md` with bot-specific constraints.

***REMOVED******REMOVED*** Local Rules
- Preserve LangGraph node contract shapes (`state` fields, routing assumptions).
- Keep service boundaries intact:
  - `telegram_bot/services/` for business logic.
  - `telegram_bot/integrations/` for wrappers/adapters.
  - `telegram_bot/graph/nodes/` for pipeline steps.
- Avoid mixing transport-layer Telegram handling with retrieval/domain logic.

***REMOVED******REMOVED*** Required Validation
- Always run fast checks:
  - `make check`
  - `make test-unit`
- For graph flow edits, run:
  - `uv run pytest tests/integration/test_graph_paths.py -v`
- For cache/search/rerank behavior edits, run targeted suites from `tests/unit/` and affected integration tests.

***REMOVED******REMOVED*** Observability
- Keep existing tracing patterns consistent (`telegram_bot/observability.py`).
- Do not remove score/trace instrumentation without explicit reason and replacement.

***REMOVED******REMOVED*** References
- `telegram_bot/README.md`
- `.claude/rules/features/telegram-bot.md`
- `.claude/rules/features/search-retrieval.md`
- `.claude/rules/features/caching.md`
- `.claude/rules/features/query-processing.md`
- `.claude/rules/services.md`
- `.claude/rules/observability.md`
