# ADR-0003: LangGraph for Voice, Deterministic Pipeline for Text

**Status:** Accepted

**Date:** 2026-02-01

## Context

The system serves two input modes:
- **Voice queries** — Via LiveKit/SIP, transcribed via Whisper
- **Text queries** — Via Telegram, typed by users

Both use the same underlying RAG retrieval but have different orchestration needs.

## Decision

| Mode | Orchestration | File |
|------|---------------|------|
| Voice | LangGraph (11-node graph) | `telegram_bot/graph/graph.py` |
| Text | Deterministic async pipeline | `telegram_bot/pipelines/client.py` |

### Why This Split

**Voice uses LangGraph because:**
1. **Voice-specific nodes** — `transcribe` node for Whisper STT
2. **State persistence** — Checkpointer for conversation continuity across voice turns
3. **Complex routing** — Voice queries benefit from full agent capabilities
4. **Streaming** — Voice benefits from streaming TTS generation

**Text uses deterministic pipeline because:**
1. **Speed** — Client role queries don't need full agent overhead
2. **Simplicity** — Text queries are typically simpler
3. **Cost** — Fewer LLM calls per query
4. **Cache efficiency** — Deterministic path enables better cache hit rates

## Consequences

### Positive
- Voice gets full LangGraph capabilities (interrupts, checkpointer, complex routing)
- Text is fast and cost-efficient
- Clear separation of concerns

### Negative
- Code duplication risk — changes must be applied to both paths
- Dual observability paths (different span names)
- Testing complexity — two different flows to verify

## Unification Opportunity

Future consideration: Unify both paths under LangGraph if:
- Client pipeline also needs interrupts (HITL)
- Client queries become more complex
- Cache hit rates drop significantly

## References

- Voice graph: `telegram_bot/graph/graph.py`
- Client pipeline: `telegram_bot/pipelines/client.py`
