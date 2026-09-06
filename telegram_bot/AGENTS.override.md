# Telegram work

Applies to telegram_bot/**; extends [root AGENTS](../AGENTS.md).

- Keep Telegram transport/lifecycle separate from retrieval and product service behavior.
- Enter shared assistant behavior through src/core; classify/guard/GraphConfig live in
  src/runtime, not a Telegram graph package.
- Preserve PreAgentStateContract in pipelines/state_contract.py while its callers remain.
  When changing a boundary, update consumers and behavior tests together.
- Trace compatibility facades to their shared owner before fixing a bug in two places.
- Preserve supported capability checks, user-visible error behavior, and score/trace fields.
  Observability shims are not proof of an external tracing backend.

## Checks

Run `make check` and `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`.
Run the focused Telegram owner tests as well: the broad unit lane excludes adapter groups.
For pipeline/supervisor changes run `make test-core` and `make test-no-service-lane`.
Cache/search/rerank changes need affected unit and integration behavior tests.

Use [Tests](../tests/README.md) for dependency selections and root delivery gates.
[Telegram README](README.md) and [Structure](../docs/architecture/STRUCTURE.md) locate owners.
