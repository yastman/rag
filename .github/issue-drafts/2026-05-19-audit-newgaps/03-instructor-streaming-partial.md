# research: evaluate `instructor.create_partial` for live filter / structured-output streaming

## Source

2026-05-19 cross-domain SDK audit (`.github/issue-drafts/2026-05-19-langfuse-trace-coverage/AUDIT_REPORT.md`, Finding 7).

## Problem

`instructor` 1.x ships `client.create_partial(response_model=..., stream=True)` and `client.create_iterable(response_model=..., stream=True)` for token-by-token streaming of structured Pydantic models. The repo uses `instructor` for structured extraction (apartment filters, query analysis, confidence scoring) but **only in non-streaming mode**.

Repo grep:

```bash
$ grep -rn "create_partial\|create_iterable" telegram_bot/ src/
# (no matches)
```

## Evidence — what's in the repo today

- `telegram_bot/services/apartment_llm_extractor.py:121` — single non-streaming call.
- `telegram_bot/services/query_analyzer.py:97` — single non-streaming call.
- `telegram_bot/services/llm.py:140-141` — confidence path, single non-streaming call.

The user-facing impact varies by surface:

- **Telegram text path** — Telegram does not have token-level UX. `create_partial` is **not useful** here.
- **Voice path** — STT → query understanding → response. If the voice agent surfaces "extracting filters: bedrooms=2…" while the LLM still streams, that's a perceived-latency win. **Useful here**.
- **Future Mini App live UI** — if the Mini App grows a live chat surface, `create_partial` enables incremental rendering.

## Context7 SDK baseline — `/567-labs/instructor`

```python
import instructor
from pydantic import BaseModel

class ApartmentFilters(BaseModel):
    city: str | None
    bedrooms: int | None
    price_max: int | None

# Existing client construction stays the same — preserves langfuse.openai auto-trace.
client = instructor.from_openai(langfuse.openai.AsyncOpenAI(...))

stream = client.create_partial(
    response_model=ApartmentFilters,
    stream=True,
    messages=[...],
)
async for partial in stream:
    # partial is ApartmentFilters with progressively-more-filled fields
    if partial.city:
        await voice_agent.say(f"Looking in {partial.city}...")
    if partial.bedrooms:
        await voice_agent.say(f"{partial.bedrooms}-bedroom...")
```

Or for multiple objects:

```python
stream = client.create_iterable(
    response_model=Apartment,
    messages=[...],
)
async for apt in stream:
    await voice_agent.preview_apartment(apt)
```

## Implementation plan — RESEARCH ONLY

This is a research issue; the outcome is one of:

1. **Pilot in voice path** — a focused PR that streams apartment filter extraction in the voice agent and surfaces partials via TTS.
2. **Defer** — document why streaming partials don't help current surfaces (e.g., latency budget already low, voice agent uses different framework).
3. **Reject** — confirm `langfuse.openai` + `instructor.from_openai` + `create_partial` either does or does not preserve auto-trace in streaming mode.

### Required research steps

1. **Verify Langfuse trace shape** — `langfuse.openai` wraps `chat.completions.create`. Test that `instructor.create_partial(stream=True)` on top of a langfuse-wrapped client produces a single generation observation (not N orphan observations per chunk).
2. **Latency profile** — measure first-partial-emitted latency vs total-completion latency for current voice queries. If < 200ms gap, the UX win is marginal.
3. **Voice agent integration point** — identify where `apartment_llm_extractor` is called in voice path and whether the agent can accept incremental filter updates.

## Forbidden

- Do **not** switch to `instructor.from_provider("openai/gpt-...", async_client=True)` — that builds its own client and breaks the `langfuse.openai` auto-trace integration. The current `from_openai(langfuse.openai.AsyncOpenAI(...))` is the correct shape.
- No new instructor-replacement abstraction.

## SDK / Local Baseline

- `instructor>=1.7.0` per `telegram_bot/pyproject.toml:10`.
- `instructor.create_partial` is stable; `Partial[Model]` import lives at `instructor.dsl.partial`.

## Verification

```bash
uv run pytest tests/unit/services/test_apartment_llm_extractor.py -q
uv run pytest tests/unit/services/test_query_analyzer.py -q
# Add: tests/unit/services/test_create_partial_langfuse_trace_shape.py
```

## Related

- #1659 (`QueryAnalyzer` orphan generation) — orthogonal. Wraps a single non-streaming call.
- #1660 (`LLMService` orphan generation) — orthogonal. The streaming paths in `LLMService` use OpenAI SDK streaming, not `instructor`.
- `_validation_comments/02-1659-query-analyzer.md` — already flags the `instructor` + `langfuse.openai` compatibility risk that this issue would also need to validate.

## Priority

**P3-research** — outcome should be either a pilot issue or a documented decision in `docs/engineering/sdk-registry.md` saying why partial streaming is intentionally not used.
