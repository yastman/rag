# Mini App browser W3C TraceContext origin — decision (#2273)

Research-only decision record (same shape as
[`VOICE_TRACING_BASELINE.md`](VOICE_TRACING_BASELINE.md)). It records the
browser-tracing scope decision and the SDK-native path **if** it is ever
adopted. No behavioural change ships with this document. Enforced by
`tests/contract/test_miniapp_browser_tracing_decision_contract.py`.

## Question

Should a Telegram Mini App click/session in
`mini_app/frontend/src/api.ts` become the **root** of the same distributed
trace as `mini_app/api.py` and the downstream CRM/RAG work — i.e. should the
browser generate or propagate a W3C `traceparent` / `tracestate`?

## Decision

**Deferred — out of scope for now.** Browser-originated traces are **not**
adopted at this time. The backend one-trace gate (#2244) is server-side and
does not require browser-originated spans.

Rationale:

- **No product need yet.** The Mini App is a thin WebView surface (config
  fetch, `start-expert`, remote log). The distributed trace that matters for
  observability begins at `mini_app/api.py` and flows into CRM/RAG. A browser
  root span would add a hop above that boundary without a current consumer.
- **The backend boundary is already correct and SDK-native.**
  `mini_app/api.py` calls `instrument_fastapi_app(app)` (FastAPI OTEL
  auto-instrumentation, #2225), which **auto-extracts** `traceparent` /
  W3C Baggage from incoming requests. So if the frontend ever *does* send a
  `traceparent`, the backend will honour it with **zero backend changes** —
  the browser decision can be made later without re-touching the server.
- **Cost/constraint.** Shipping an OTel JS web bundle into a Telegram WebView
  (bundle size, an exposed browser-reachable OTLP collector endpoint, CORS,
  init-data auth interplay) is real work that is not justified by current
  needs.

This decision is revisited if a concrete product requirement appears (e.g.
"a Mini App tap must be the visible root of the lead's trace in Langfuse").

## SDK evidence (for the in-scope path, if adopted)

Gathered via Context7. *Content was rephrased for compliance with licensing
restrictions.*

- **OpenTelemetry JS web is the right tool, not Langfuse browser.** Langfuse
  ships a JS/TS SDK (`/langfuse/langfuse-js`) but it targets server/Node LLM-app
  instrumentation, not first-class browser/frontend span emission. For a
  browser surface the OpenTelemetry JS web packages are the SDK-native choice:
  - `@opentelemetry/sdk-trace-web` — `WebTracerProvider` registered with a
    `BatchSpanProcessor` and an OTLP HTTP exporter.
  - `@opentelemetry/instrumentation-fetch` — `FetchInstrumentation`
    auto-creates a client span per `fetch(...)` and injects the W3C
    `traceparent` header. `propagateTraceHeaderCorsUrls` scopes header
    injection to the Mini App API origin so the token is never leaked to
    third-party hosts.
  - `@opentelemetry/core` `W3CTraceContextPropagator` is the default
    propagator — the same `tracecontext` format the backend already extracts.
- **Telegram Mini App / WebView compatibility.** The Mini App runs in a
  standard browser WebView, so the web tracer + `FetchInstrumentation` apply
  unchanged. The frontend's `fetch` calls target a same-origin `/api` base
  (nginx-proxied), so `traceparent` injection works without extra CORS config;
  `propagateTraceHeaderCorsUrls` would only be needed if the API moved
  cross-origin.

## In-scope path (only if the decision is reversed)

1. Decide whether the browser **generates a root** `traceparent` (Mini App tap
   is the trace root) or only **propagates a backend-issued** context. Default
   recommendation: generate a root in the browser for true
   click-to-CRM traces.
2. Add the OTel JS web packages above to `mini_app/frontend`.
3. Register a `WebTracerProvider` + `FetchInstrumentation` (scoped via
   `propagateTraceHeaderCorsUrls` to the Mini App API origin) so the existing
   `fetch(...)` calls in `mini_app/frontend/src/api.ts` carry `traceparent`.
4. Keep `mini_app/api.py` extraction **SDK-native** via `instrument_fastapi_app`
   (already wired) — no manual header parsing.
5. Open a dedicated implementation issue and define the header contract
   (`traceparent` / `tracestate`) on the `api.ts` calls.

## Out of scope

- Any frontend SDK install or `api.ts` header change (this is research-only).
- A browser-reachable OTLP collector endpoint.
- Replacing the backend `instrument_fastapi_app` extraction.

## References

- #2244 (one-trace gate, server-side), #2246, #2256 (cross-service W3C).
- `mini_app/frontend/src/api.ts`, `mini_app/api.py`.
- OpenTelemetry JS: `@opentelemetry/sdk-trace-web`,
  `@opentelemetry/instrumentation-fetch`, `@opentelemetry/core`
  (`W3CTraceContextPropagator`) — via Context7
  (`/open-telemetry/opentelemetry-js`).
