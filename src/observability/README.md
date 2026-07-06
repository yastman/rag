# src/observability/

Observability helpers for the `src/` layer. **Langfuse and OpenTelemetry were fully removed**
(#2844, #2969, `card_81add5ba4a66`). Canonical observability is structured product logs
([`../utils/product_events.py`](../utils/product_events.py)).

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | Public helpers + no-op tracing shims |
| [`scores.py`](./scores.py) | `score`, `write_scores`, `write_history_scores`, `compute_checkpointer_overhead_proxy_ms` |

## What's real vs. shim

- **Real utilities:** `mask_pii` (PII masking for safe payloads), `propagate_attributes`
  (context-propagation seam), and everything in `scores.py`.
- **No-op shims kept for import compatibility only:** `observe` (both `@observe` and
  `@observe(name=...)` forms), `traced_pipeline`, `get_client` (returns `None`). They exist so
  callers that still wrap code in these constructs keep working — they do **not** trace.

## Boundaries

- Do not reintroduce a tracing SDK here; the removal is enforced by
  [`../../tests/contract/test_no_langfuse_sdk_import_contract.py`](../../tests/contract/test_no_langfuse_sdk_import_contract.py).
- PII masking delegates to [`../security/`](../security/) (`PIIRedactor`).

## See Also

- [`../utils/README.md`](../utils/README.md) — product-event logging (the canonical path)
- [`../../telegram_bot/observability/README.md`](../../telegram_bot/observability/README.md) — bot-side shims re-exported from here
