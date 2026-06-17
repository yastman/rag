# ADR-0017: OpenTelemetry Trace Sampling Roadmap

**Status:** Accepted

**Date:** 2026-05-29

**Closes:** [#2228](https://github.com/yastman/rag/issues/2228) (roadmap ADRs)

**Related:** [#2215](https://github.com/yastman/rag/issues/2215) (observability audit), [#2218](https://github.com/yastman/rag/issues/2218) (Sentry↔Langfuse cross-link), [#2244](https://github.com/yastman/rag/issues/2244) (single-trace gate)

## Context

Every `@observe` and every auto-instrumented HTTP call currently produces a span; no sampler is configured, so the implicit behaviour is **AlwaysOn** (100% of root traces are kept). At current volume this is desirable — full traces aid debugging and the single-trace gate (#2244). As volume grows, AlwaysOn scales Langfuse ingestion/storage cost linearly and risks silent span drops under `BatchSpanProcessor` backpressure.

## Decision

**Record AlwaysOn as today's intentional default** and declare the trigger and mechanism for switching, without changing code now.

- **Today:** no sampler env set ⇒ AlwaysOn. Keep it.
- **Trigger to switch:** when monthly Langfuse trace volume or ingestion/storage cost crosses the team's review threshold (tracked alongside the cost reconciliation work, #2223), switch root-trace sampling on.
- **Mechanism (declarative, no code):**

  ```yaml
  OTEL_TRACES_SAMPLER: parentbased_traceidratio
  OTEL_TRACES_SAMPLER_ARG: "0.1"   # keep 10% of root traces; children follow the parent decision
  ```

  `parentbased_*` ensures a sampled root keeps its whole tree intact — essential for the single-trace goal (#2244).
- **Error-aware sampling is not required now:** Sentry already captures errors and cross-links to the Langfuse trace (#2218), so "always trace failures" can be deferred. If needed later, add a custom `Sampler` that forces-keep `Status.ERROR` spans.

## Consequences

- Cost grows linearly with volume until the trigger fires; the trigger is now explicit rather than discovered via a surprise bill or dropped spans.
- Switching is an env change on traced services, not a code change.
- Sampling interacts with the single-trace gate: only `parentbased` ratio sampling is acceptable, so a kept trace remains complete end-to-end.

## Implementation notes

- No code today. When triggered, set `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` on the OTEL-SDK services (the same set that declares `OTEL_PROPAGATORS`, #2254).
