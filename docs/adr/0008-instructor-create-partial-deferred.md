***REMOVED*** ADR-0008: Defer `instructor.create_partial` Streaming Until Voice Path Adopts It

**Status:** Accepted (defer)

**Date:** 2026-05-20

**Closes:** [***REMOVED***1672](https://github.com/yastman/rag/issues/1672)

***REMOVED******REMOVED*** Context

`instructor` 1.x exposes two SDK-native streaming primitives for structured Pydantic outputs:

- `client.create_partial(response_model=Model, stream=True, ...)` — yields a generator of progressively-filled `Model` instances.
- `client.create_iterable(response_model=Model, stream=True, ...)` — yields a generator of fully-validated `Model` instances when the LLM emits a list.

These are stable in `instructor>=1.0` (we are pinned to `>=1.7.0`).

The repo uses `instructor` for structured extraction in three places, all **non-streaming** today:

- `telegram_bot/services/apartment_llm_extractor.py` — `instructor.from_openai(llm)` → `chat.completions.create(response_model=ApartmentFilters, ...)` (apartment filter extraction).
- `telegram_bot/services/query_analyzer.py` — `instructor.from_openai(self.client)` → query intent / language classification.
- `telegram_bot/services/llm.py` — `instructor.from_openai(self.client)` → confidence scoring.

A repo-wide grep confirms zero `create_partial` / `create_iterable` usage:

```bash
$ grep -rn "create_partial\|create_iterable" telegram_bot/ src/ mini_app/
***REMOVED*** (no matches)
```

***REMOVED******REMOVED*** Decision

**Defer adoption of `create_partial` / `create_iterable`.** Do not introduce streaming structured outputs in the current scope. Revisit as part of the voice-path migration ([***REMOVED***1535](https://github.com/yastman/rag/issues/1535)) or any future Mini App live-chat surface.

When/if adopted, the SDK shape **must** preserve Langfuse auto-tracing:

```python
***REMOVED*** REQUIRED:
client = instructor.from_openai(langfuse.openai.AsyncOpenAI(...))
stream = client.create_partial(response_model=Model, stream=True, messages=[...])
async for partial in stream:
    ...
```

```python
***REMOVED*** FORBIDDEN: breaks langfuse.openai auto-trace by constructing its own client.
client = instructor.from_provider("openai/gpt-...", async_client=True)
```

***REMOVED******REMOVED*** Why defer

| Surface | UX gain from `create_partial` | Adopt now? |
|---|---|---|
| Telegram text | None — Telegram has no token-level message UX. Drafts are edited at message granularity, not field granularity. | No |
| Voice agent (post-***REMOVED***1535 migration) | Real — TTS can announce "looking in `<city>`…" as `city` field fills, before `bedrooms` resolves. | When voice path lands |
| Mini App (future live chat) | Real — incremental field-level rendering. | When/if live chat surface ships |
| Apartment filter extraction (current) | None — extraction completes in <2s for typical queries; merged with regex before consumption. | No |
| Query analyzer (current) | None — single-call classification feeds graph routing; partial state has no consumer. | No |
| Confidence scoring (current) | None — scalar output, no incremental UX. | No |

The cost of premature adoption is non-trivial:

1. **Langfuse trace shape risk.** `instructor.from_provider("openai/...", async_client=True)` builds a fresh OpenAI client and bypasses our `langfuse.openai.AsyncOpenAI` wrapper. This silently destroys auto-tracing for the affected call site, and the failure mode is invisible in tests that don't assert on trace shape.
2. **No working consumer.** None of the three current `instructor` call sites have an upstream consumer that benefits from progressive field availability. Streaming would just cost extra event-loop wakeups for no UX win.
3. **Validator gap.** Pydantic validators are not enforced on partial models (per `instructor` docs — partial fields can be `None` while the model is still incomplete). Adopting partial streaming would require revisiting validation behavior in extractors that today rely on full-model validation (e.g., `ApartmentFilters`).

***REMOVED******REMOVED*** Constraints when this is revisited

If a future PR introduces `create_partial` / `create_iterable`:

1. Construction shape must remain `instructor.from_openai(langfuse.openai.AsyncOpenAI(...))`. The regression test in `tests/unit/services/test_instructor_sdk_contract.py` enforces this and must not be relaxed.
2. The PR must include a focused trace-shape test that asserts a single Langfuse generation observation per streamed call (not N orphan observations per chunk). Reference: `TestQueryAnalyzerInstructorLangfuseCompat` in `tests/unit/services/test_query_analyzer.py` — same preflight pattern.
3. Validator semantics must be documented in the consumer (e.g., "this consumer tolerates `field=None` until completion").
4. If the consumer is the voice agent, integrate at the `voice_agent.say(...)` boundary, not inside the LangGraph node. Graph nodes should remain unaware of streaming chunk granularity; `stream_mode="custom"` (per [***REMOVED***1671](https://github.com/yastman/rag/issues/1671)) is the appropriate fan-out shape if cross-node streaming is needed.

***REMOVED******REMOVED*** Consequences

***REMOVED******REMOVED******REMOVED*** Positive
- Zero risk to current Langfuse trace coverage.
- No new validator semantics to debug.
- Frees the streaming decision to land alongside a real UX consumer.

***REMOVED******REMOVED******REMOVED*** Negative
- Voice path migration ([***REMOVED***1535](https://github.com/yastman/rag/issues/1535)) carries one extra item when it ships.
- If perceived voice latency becomes a P1 concern before ***REMOVED***1535, this ADR has to be revisited out of band.

***REMOVED******REMOVED*** References

- Issue [***REMOVED***1672](https://github.com/yastman/rag/issues/1672) — research request.
- Issue [***REMOVED***1535](https://github.com/yastman/rag/issues/1535) — voice path migration to `create_agent`.
- Issue [***REMOVED***1671](https://github.com/yastman/rag/issues/1671) — LangGraph `stream_mode="custom"` for cross-node streaming.
- Issue [***REMOVED***1659](https://github.com/yastman/rag/issues/1659) — `QueryAnalyzer` orphan generation; preflight pattern reused here.
- `instructor` partial streaming docs: <https://github.com/567-labs/instructor/blob/main/docs/concepts/partial.md>.
- Regression test: `tests/unit/services/test_instructor_sdk_contract.py`.
- SDK registry entry: `docs/engineering/sdk-registry.md` → `instructor` section.
