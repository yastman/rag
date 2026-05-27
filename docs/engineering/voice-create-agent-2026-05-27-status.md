# Voice → `create_agent` migration — 2026-05-27 status & remaining-slice plan

**Date:** 2026-05-27
**Issue:** [#2051 — sdk: rewire voice handler to create_agent (#1535 child)](https://github.com/yastman/rag/issues/2051)
**Parent:** [#1535](https://github.com/yastman/rag/issues/1535)
**Sequencing source of truth:** [`docs/engineering/voice-create-agent-migration-sequence.md`](voice-create-agent-migration-sequence.md)
**ADR:** [`docs/adr/0010-voice-path-create-agent-migration-plan.md`](../adr/0010-voice-path-create-agent-migration-plan.md)

This note is a **scoped status check** of the voice migration on `dev` @
`4ab8379` and a tractable plan for the remaining work needed before
#2051 can land. It is intentionally a planning artefact — the rewire
itself ships in subsequent PRs because Slices 2 and 3 of the ADR-0010
sequence are not yet on `dev`, and rewiring `handle_voice` without them
would silently lose the semantic-cache and CHITCHAT short-circuits the
legacy graph provides today.

## What has shipped (verified on `dev`)

| Slice | Deliverable | State |
|-------|-------------|-------|
| 0 | ADR-0010 + sequencing doc | ✅ on `dev` |
| 1a | `GuardMiddleware` (`telegram_bot/graph/middleware/guard.py`) | ✅ on `dev` (closed via #2052 — referenced from the module docstring) |
| 1b | RAG tools (`telegram_bot/graph/tools/{retrieve,rerank,rewrite}.py`) | ✅ on `dev` (closed via #2050) |

The middleware module is currently single-export (`GuardMiddleware`)
and lives under `telegram_bot/graph/middleware/` rather than the
`telegram_bot/agents/middleware/` path the ADR proposed; we keep the
existing layout for now and revisit the move when/if a second
middleware sibling justifies the cost.

## What still blocks #2051

| Slice | Deliverable | Blocking risk for the rewire |
|-------|-------------|------------------------------|
| 2 | `SemanticCacheMiddleware` (`before_model` cache_check + `after_model` cache_store) | Without this, voice loses semantic-cache HIT short-circuiting. ~270 LOC of `cache_check_node` / `cache_store_node` to reshape onto the SDK middleware contract. |
| 2.5 (new) | `ClassifyMiddleware` for CHITCHAT / OFF_TOPIC routing | Voice graph today returns canned responses for CHITCHAT without invoking the LLM. The text path bypasses this because chit-chat goes to a different handler; voice cannot. ~37 LOC `classify_node` + new `before_model` short-circuit. |
| 3 | `VoiceAgentState` + `create_voice_agent` factory | The actual voice agent constructor wiring `transcribe` → guard → cache_check → tools → cache_store → respond. Implementation only — must be rebuilt against shipped middleware. |
| 4 | Gold-set evaluation | Run `src/evaluation/` against both `graph` and `agent` backends. Promote `agent` only if regressions ≤ 2 % on every metric (per ADR-0010 §"Migration Steps"). |
| 5 | `handle_voice` rewire | The actual #2051 deliverable. Requires Slices 2, 2.5, 3 already merged and Slice 4 evaluation showing parity. |

## Code surface to read before opening Slice 2 PR

* `telegram_bot/graph/nodes/cache.py` — 317 LOC, two `@observe` nodes
  (`cache_check_node`, `cache_store_node`) that consume
  `runtime.context["cache"]` / `runtime.context["embeddings"]`. Each
  node returns a state-update dict; the middleware will instead return
  `{"jump_to": "end", "messages": [...]}` on cache HIT and a no-op
  `None` on MISS.
* `telegram_bot/services/cache_policy.py` — pure helpers
  (`is_contextual_query`, `maybe_store_semantic_response`, …) — keep as
  dependency, do not duplicate.
* `telegram_bot/services/rag_core.py` — owns `check_semantic_cache` and
  `compute_query_embedding`; the middleware should call these directly
  instead of re-implementing.
* Text-path inline cache logic in
  `telegram_bot/bot.py::_handle_query_supervisor` (lines ~2217–2495).
  This is the de-facto "cache middleware in the wrong place" — once
  Slice 2 lands, this block can be replaced by the new middleware in a
  follow-up. **Out of scope for #2051**, but the duplication note
  belongs in the Slice 2 PR description.

## TDD plan for the remaining slices

Each Slice 2/2.5/3 PR follows a small loop:

1. **Contract test first.** Add a contract under
   `tests/contract/test_voice_create_agent_*_contract.py` that pins the
   public surface (middleware class name + `before_model` /
   `after_model` signatures, factory presence, allowed module-scope
   imports). The contract test is red until the slice lands.
2. **Unit tests for behaviour.** For each middleware, capture the legacy
   node's behaviour on canonical inputs:
   * cache HIT in `CACHEABLE_QUERY_TYPES` → returns `{"jump_to": "end", "messages": [...]}`.
   * cache MISS → returns `None`.
   * non-cacheable query type → returns `None` without computing
     embedding.
3. **Cut the slice.** Implement the middleware re-using
   `telegram_bot.services.cache_policy` / `rag_core` helpers (no
   re-implementation). Run the same gold-set spot tests the graph
   already has under `tests/unit/graph/test_cache_nodes.py` against the
   middleware to assert byte-for-byte parity on a curated input set.
4. **Slice 3 only:** add an integration-style unit test that builds a
   voice agent end-to-end with `MemorySaver` and a stubbed `rag_search`
   tool, runs `agent.ainvoke(...)` with a synthetic transcript, and
   asserts the response shape matches what `handle_voice` consumes
   today.

The actual `handle_voice` rewire (Slice 5 / the body of #2051) lands
only after Slices 2, 2.5, 3 are green and Slice 4 evaluation shows
acceptable regressions. The rewire itself is then a one-PR change:
replace the `build_graph(...).ainvoke(state, config)` block with
`agent = create_voice_agent(...); result = await agent.ainvoke({"messages": [...]}, config)`,
preserving the `_CHECKPOINT_NS_VOICE` namespace and the `trace_id`
injection inside `propagate_attributes`.

## Verification command (matches issue body)

```
uv run --python 3.12 pytest \
  tests/unit/graph/ \
  tests/unit/test_bot_handlers.py \
  tests/contract/test_bot_lifecycle_extraction_contract.py \
  -q --timeout=30
```

## Recommended follow-up issue ladder

If we want one ticket per slice (smaller PRs, smaller reviews):

* **#NEW-A** — Slice 2: `SemanticCacheMiddleware` + tests.
* **#NEW-B** — Slice 2.5: `ClassifyMiddleware` + CHITCHAT/OFF_TOPIC short-circuit.
* **#NEW-C** — Slice 3: `VoiceAgentState` + `create_voice_agent` + integration test.
* **#NEW-D** — Slice 4: gold-set evaluation harness running both backends side-by-side.
* **#2051** — Slice 5: rewire `handle_voice`, add cleanup-only PR removing legacy graph nodes once #2051 ships.

Alternative (single-issue track): keep #2051 open and ship the slices
under sub-comments / sub-PRs, but flip the issue's `lane:plan-needed`
label to `lane:plan-known` once this status doc lands so the sequencing
is unambiguous for future agents.

## Decision

Do **not** attempt the `handle_voice` rewire in the current PR. Land
this status note now; open Slice 2 (`SemanticCacheMiddleware`) as the
next concrete code PR against the plan above; #2051 itself stays open
until Slices 2/2.5/3/4 are merged and the rewire passes gold-set eval.
