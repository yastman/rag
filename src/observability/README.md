# src/observability/

Observability helpers for the `src/` layer. **Langfuse and OpenTelemetry were fully removed**
(#2844, #2969, `card_81add5ba4a66`). Canonical observability is structured product logs
([`../utils/product_events.py`](../utils/product_events.py)).

## Files

| File | Purpose |
|------|---------|
| [`__init__.py`](./__init__.py) | `mask_pii` — the single retained helper |

## What's real vs. shim

- **Real utility:** `mask_pii` (PII masking for safe payloads).
- **No shims remain.** The former no-op tracing shims (`observe`, `traced_pipeline`,
  `get_client`, `propagate_attributes`) and the no-op scoring stubs (`score`, `write_scores`,
  `write_history_scores`; #3331) were removed once they had no production callers. Do not
  reintroduce compatibility no-ops here; if telemetry returns it belongs at a real backend
  boundary.

## Boundaries

- Do not reintroduce a tracing SDK here; the removal is enforced by
  [`../../tests/contract/test_no_langfuse_sdk_import_contract.py`](../../tests/contract/test_no_langfuse_sdk_import_contract.py).
- PII masking delegates to [`../security/`](../security/) (`PIIRedactor`).

## See Also

- [`../utils/README.md`](../utils/README.md) — product-event logging (the canonical path)
- [`../../telegram_bot/observability/README.md`](../../telegram_bot/observability/README.md) — bot-side shims re-exported from here
