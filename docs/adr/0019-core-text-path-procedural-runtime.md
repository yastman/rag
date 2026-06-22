# ADR-0019: Core Text Path Uses Procedural Runtime, Not `create_agent`

**Status:** Accepted

**Date:** 2026-06-08

**Closes:** [#2403](https://github.com/yastman/rag/issues/2403) (`CORE-018`)

**Related:** [#2386](https://github.com/yastman/rag/issues/2386) (`CORE-005`), [#2389](https://github.com/yastman/rag/issues/2389) (`CORE-008`), [ADR-0015](0015-sdk-native-baseline.md), [ADR-0010](../archive/adr/0010-voice-path-create-agent-migration-plan.md)

## Context

The core simplification work needs one architecture decision before continuing
`CORE-005` and `CORE-008`: should the product-owned text RAG path be wrapped
around LangChain `create_agent`, or should the assistant core own a procedural
runtime pipeline?

Current code has two different concerns that were historically conflated:

1. **Product core text RAG** — classify, retrieve, rerank/cache, generate,
   apply grounding/no-data policy, and return `AssistantResult` for Telegram,
   direct E2E, and any optional API adapter.
2. **Telegram conversational/agent shell** — Telegram-specific prompts,
   history trimming, tool loops, streaming/draft rendering, HITL buttons, and
   adapter-side workflow UX.

`create_agent` remains useful for the second concern, but making it the owner of
the first concern would keep the core product proof dependent on an agent shell
and would make the direct E2E path harder to reason about.

## Decision

The **assistant core text RAG path is procedural**:

```text
src.core.run_assistant_request()
  -> src.runtime.pipeline.run_assistant_pipeline()
  -> classify / retrieve / generate / grounding / CRM proposal
  -> AssistantResult
```

`create_agent` is **not** the canonical owner of the core text RAG path.

`create_agent` remains allowed for Telegram or voice adapter flows when the
adapter needs conversational agent behavior, tool loops, history trimming,
streaming, or adapter-specific HITL UX. Those flows must call or wrap the core
entrypoint for product RAG behavior instead of re-owning retrieval/generation
logic.

## Consequences

- `CORE-005` can continue moving RAG ownership into `src.runtime` without
  creating a `create_agent` wrapper around every core call.
- `CORE-008` should wire Telegram as a thin adapter over `AssistantResult`; it
  may keep a rollback/shadow branch that uses the existing agent shell during
  migration.
- The golden core E2E gate must call `run_assistant_request()` directly and must
  not require Telegram, `create_agent`, Telethon, Langfuse, voice, or Mini App.
- New core runtime modules should prefer explicit request/result contracts over
  agent-global state or Telegram message objects.
- ADR-0015's SDK-native baseline still applies to adapter/conversational agent
  surfaces, but this ADR supersedes it for the product-owned core text RAG path.

## Rejected Alternative: Wrap Core Around `create_agent`

Rejected for now because it would:

- make the direct core E2E proof depend on agent/tool-loop semantics;
- keep Telegram-era prompt/history concerns too close to product retrieval;
- make no-data/grounding/cache behavior harder to assert as deterministic
  `AssistantResult` fields;
- slow `CORE-005` and `CORE-008` by requiring an agent abstraction before the
  ownership migration is complete.

## Implementation Notes

- `telegram_bot/agents/agent.py` may continue to use `create_agent` for adapter
  and conversational shell behavior.
- `src.core` and `src.runtime` must not import `telegram_bot.agents.agent` or
  instantiate `create_agent` for the canonical text RAG path.
- If a future workflow needs an agentic planner inside the core, add a new ADR
  with a narrow scope and keep the public `AssistantResult` contract stable.
