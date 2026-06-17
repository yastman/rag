# Archived Mini App browser tracing decision (#2273, #2430)

The Telegram Mini App has been archived under [`../../../archive/mini_app/`](../../../archive/mini_app/) and is no longer part of the required runtime, Compose, CI, or observability path.

## Current decision

Do **not** add browser-originated W3C TraceContext or OpenTelemetry JavaScript instrumentation to the required product path. The archived FastAPI/React code is preserved for reference only; any future Mini App unarchive must open a new product decision before reintroducing `mini-app-api`, `mini-app-frontend`, frontend tracing packages, or required tests.

## Historical context

The previous decision deferred browser tracing because the server-side trace boundary was sufficient and the browser bundle/collector/CORS work had no current product consumer. Archiving the Mini App makes that deferral explicit: Mini App taps are not a required trace root, and core proof observability relies on structured product logs plus optional server-side diagnostics.

## If the Mini App is unarchived

1. Restore the runtime surface intentionally from `archive/mini_app/`.
2. Decide whether browser spans are product-required before adding OTel JS packages.
3. Keep any trace propagation scoped to the Mini App API origin.
4. Add fresh contracts for the new runtime path rather than reusing the removed required-lane tests.
