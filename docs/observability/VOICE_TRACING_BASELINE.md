# Voice / LiveKit W3C TraceContext baseline (#2257)

SDK baseline for how the voice path participates in the single distributed trace
(#2244). Research-only decision record: it documents the supported approach and
the current state, and defers the behavioural change (deprecating the manual
`langfuse_trace_id`) to a follow-up implementation issue. Enforced by
`tests/contract/test_voice_tracing_baseline_contract.py`.

## Question

Can voice lifecycle spans and the voice -> RAG hop join the same W3C trace as
the bot/RAG path, using SDK-native mechanisms rather than a handwritten
`langfuse_trace_id`?

## SDK evidence

- **LiveKit Agents exposes an OTel hook.** `livekit.agents.telemetry` provides
  `set_tracer_provider(provider)`: register a `TracerProvider` and LiveKit
  emits its spans (LLM calls auto-trace as nested spans, alongside your own
  manual root spans) on that provider's exporter. Evidence: the LiveKit JS API
  reference documents the equivalent `setTracerProvider` in
  `@livekit/agents/telemetry`
  ([reference](https://docs.livekit.io/reference/agents-js/functions/agents.telemetry.setTracerProvider.html)),
  and the OpenObserve LiveKit integration documents registering a
  `TracerProvider` via `telemetry.set_tracer_provider()`
  ([docs](https://openobserve.ai/docs/integration/ai/frameworks/livekit/)).
  *Content was rephrased for compliance with licensing restrictions.*
- **OpenTelemetry context propagates over HTTP via `httpx`.** The voice -> RAG
  hop uses `httpx.AsyncClient`, so the process-wide `HTTPXClientInstrumentor`
  (#2225/#2256) injects W3C `traceparent` + `baggage` automatically.

## Current state in the repo

- `src/voice/agent.py::_setup_langfuse()` forwards the Langfuse-registered
  global OTel `TracerProvider` to LiveKit via
  `livekit.agents.telemetry.set_tracer_provider(provider)` (guarded by
  try/except for older LiveKit installs). So LiveKit spans already land on the
  same exporter as the rest of the runtime.
- The `entrypoint` opens a `voice-session` root observation (#2160) so child
  `@observe` spans (`voice-tool-search-knowledge-base`, downstream
  `rag-api-query`) nest into one Langfuse trace per call.
- `src/voice/rag_api_client.py` uses `httpx` (covered by `HTTPXClientInstrumentor`)
  **but also** passes a manual `langfuse_trace_id` in the `/query` payload, and
  the trace id is threaded through LiveKit job metadata. This is a legacy
  belt-and-suspenders workaround — the voice analogue of the BGE-M3 manual
  headers tracked in #2253.

## Decision (baseline)

1. **Voice lifecycle spans:** SDK-native via
   `livekit.agents.telemetry.set_tracer_provider` (already wired). This is the
   supported approach; keep it.
2. **Voice -> RAG hop:** SDK-native W3C TraceContext via `HTTPXClientInstrumentor`
   (already active). The RAG API spans nest under the `voice-session` trace as
   long as that span's context is active during the `httpx` call.
3. **Manual `langfuse_trace_id`:** keep as a documented fallback **for now**.
   It is redundant with W3C TraceContext once runtime continuity is proven, and
   should then be deprecated — mirroring #2253 for the BGE-M3 boundary. This is
   the implementation follow-up; it is intentionally out of scope here.

No new dependency is required; no OTLP gRPC exporter is introduced (the export
path is the existing Langfuse OTel ingestion).

## Follow-up implementation issue

Because SDK-native support exists, the behavioural change is tracked separately:
prove voice -> RAG same-trace continuity at runtime (via `make
validate-traces-fast` + the #2252 continuity check), then deprecate the manual
`langfuse_trace_id` payload/metadata path. See the issue linked from #2257.

## References

- Single-trace gate: #2244 · Audit: #2246 · Cross-service contract: #2256
- Manual-propagation cleanup pattern: #2253 · Voice-session root span: #2160
- Cross-service tracing contract doc: [`CROSS_SERVICE_TRACING.md`](CROSS_SERVICE_TRACING.md)
