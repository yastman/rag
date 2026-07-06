# telegram_bot/observability/

Bot-side observability helpers (`card_265772dd6bd4`), consolidating previously scattered
stubs. **Langfuse removed** (#2844, #2969) — tracing entrypoints here are no-op shims kept
for import compatibility; observability is through structured logs.

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Re-exports `src.observability` shims (`observe`, `traced_pipeline`, `get_client`, `mask_pii`, `propagate_attributes`) + `create_callback_handler` (no-op) |
| [`context.py`](./context.py) | `make_session_id`, `classify_action` |
| [`trace.py`](./trace.py) | `_build_trace_metadata` |
| [`bot_observability.py`](./bot_observability.py) | Bot-scoped observability helpers |
| [`state_helpers.py`](./state_helpers.py) | State/observability helpers |

## Boundaries

- Tracing shims delegate to [`../../src/observability/`](../../src/observability/); do not add a
  real tracing SDK.
- Old import paths (`telegram_bot/observability.py`, `_bot_observability.py`,
  `tracing_context.py`) remain valid via backward-compat shims in those modules.

## See Also

- [`../../src/observability/README.md`](../../src/observability/README.md) — source of the shims
- [`../README.md`](../README.md) — Telegram transport overview
