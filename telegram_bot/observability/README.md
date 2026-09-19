# telegram_bot/observability/

Bot-side trace metadata, session identifiers and state helpers. Observability uses
structured logs; these modules do not initialize a tracing backend.

## Files

| File | Purpose |
|------|---------|
| [`context.py`](./context.py) | `make_session_id` |
| [`trace.py`](./trace.py) | `_build_trace_metadata` |
| [`state_helpers.py`](./state_helpers.py) | State/observability helpers |

## Boundaries

- Import helpers from their defining modules. Shared PII masking lives in
  [`../../src/observability/`](../../src/observability/).

## See Also

- [`../../src/observability/README.md`](../../src/observability/README.md) — source of the shims
- [`../README.md`](../README.md) — Telegram transport overview
