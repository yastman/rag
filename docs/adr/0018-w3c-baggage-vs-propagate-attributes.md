# ADR-0018: W3C Baggage vs `propagate_attributes`

**Status:** Accepted

**Date:** 2026-05-29

**Closes:** [#2228](https://github.com/yastman/rag/issues/2228) (roadmap ADRs)

**Related:** [#2226](https://github.com/yastman/rag/issues/2226) / [#2235](https://github.com/yastman/rag/issues/2235) (baggage propagation), [#2254](https://github.com/yastman/rag/issues/2254) (declare `OTEL_PROPAGATORS`), [#2256](https://github.com/yastman/rag/issues/2256) (cross-service instrumentation), [#2253](https://github.com/yastman/rag/issues/2253) / [#2266](https://github.com/yastman/rag/issues/2266) (manual trace-id cleanup), [#2244](https://github.com/yastman/rag/issues/2244) (single-trace gate)

## Context

Two mechanisms carry user/session/tag context:

- **`propagate_attributes(session_id=..., user_id=..., tags=[...])`** — a Langfuse contextvars wrapper. It works **in-process** and is the established way the bot/voice transports attach Langfuse trace attributes.
- **W3C Baggage** — the OTel-standard cross-cutting context that auto-propagates over any instrumented transport (HTTP/gRPC) as a `baggage` header. With the propagators declared (`tracecontext,baggage`, #2254) and FastAPI/httpx auto-instrumentation active (#2256), Baggage now flows across service boundaries. `propagate_attributes(as_baggage=True)` bridges Langfuse attrs into Baggage at the transport edge.

Historically, cross-service trace context was carried by hand-written `langfuse_trace_id` / `x-langfuse-*` headers (BGE-M3 path, voice→RAG payload) — a workaround that predates the SDK-native layer.

## Decision

1. **In-process:** `propagate_attributes(...)` remains canonical for setting `user_id` / `session_id` / `tags`.
2. **Cross-service:** rely on **W3C TraceContext + Baggage** (auto-injected by `HTTPXClientInstrumentor`, auto-extracted by `FastAPIInstrumentor`); bridge Langfuse attrs with `propagate_attributes(as_baggage=True)` at the transport boundary.
3. **No hand-rolled trace-context headers.** The legacy `langfuse_trace_id` / `x-langfuse-*` workarounds are deprecated and tracked for removal once runtime continuity is proven (BGE-M3 #2253, voice→RAG #2266).
4. **Full migration deferred:** moving *every* cross-service attribute from `propagate_attributes` to raw `set_baggage(...)` is deferred until a concrete cross-service field beyond `user_id`/`session_id`/`tags` needs auto-propagation. Today's split (in-process wrapper + Baggage at the edge) is correct.

## Consequences

- One clear boundary: in-process wrapper, cross-service Baggage. New cross-service work uses Baggage, not custom headers.
- The contract test in #2256 plus the propagator declaration in #2254 keep this enforceable; the cleanup issues (#2253/#2266) remove the legacy duplication.

## Implementation notes

- Propagators: `OTEL_PROPAGATORS=tracecontext,baggage` per OTEL-SDK service (#2254).
- Bridge: bot middleware and voice entrypoint call `propagate_attributes(..., as_baggage=True)`.
- Cross-service inbound/outbound instrumentation locked by the #2256 contract.
