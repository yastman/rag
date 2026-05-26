# Voice Path → `create_agent` Migration — Sequencing

Single source of truth for the per-slice ordering of the voice-path
migration epic. Pairs with [ADR-0010](../adr/0010-voice-path-create-agent-migration-plan.md)
which captures the *why*; this document captures the *what to do next*.

## Status

**In progress.**

* [ADR-0010](../adr/0010-voice-path-create-agent-migration-plan.md) — design plan, **Proposed**.
* [#1535](https://github.com/yastman/rag/issues/1535) — parent epic, open, `lane:design-first`.
* [#2050](https://github.com/yastman/rag/issues/2050) — convert voice graph nodes into `create_agent` tools, **closed (done)** on 2026-05-26.
* [#2051](https://github.com/yastman/rag/issues/2051) — rewire voice handler to `create_agent`, open, `lane:plan-needed`.
* [#2048](https://github.com/yastman/rag/issues/2048) — extract `PropertyBot` lifecycle method slices, open, `lane:architecture-heavy`. **Was blocked on #1948; unblocked by [PR #2135](https://github.com/yastman/rag/pull/2135).**
* [#1948](https://github.com/yastman/rag/issues/1948) — reverse-layering closure, **closed by PR #2135**.

The sequencing doc flips its `Status` line from `In progress` to `Done`
in the same PR that flips ADR-0010 from `Proposed` to `Accepted` — i.e.
the PR that removes `telegram_bot/graph/graph.py::build_graph`.

## Sequence

Order of execution follows the dependency arrows below. Do **not** start a
later slice before its predecessors land — each one assumes the previous
slice's invariants.

```
#1535 (ADR-0010)        ─┐
                         ├──► #2050 (tools)  ──►  #2051 (rewire)  ──►  ADR-0010 → Accepted
#1948 (layering)  ──────┘                                                    │
                                                                             ▼
                                                                        #2048 (lifecycle)
```

| Step | Issue | Status | Notes |
|---|---|---|---|
| 1 | [#1535](https://github.com/yastman/rag/issues/1535) — design plan | open / `Proposed` | ADR-0010 lives at [docs/adr/0010-voice-path-create-agent-migration-plan.md](../adr/0010-voice-path-create-agent-migration-plan.md). Stays Proposed until the rewire lands and the legacy graph file is removed. |
| 2 | [#2050](https://github.com/yastman/rag/issues/2050) — convert nodes to tools | **closed** (done) | Voice graph nodes (`guard`, `classify`, `retrieve`, `rerank`, `rewrite`, `grade`, cache) are now `create_agent`-compatible callables in `telegram_bot/graph/tools/`. |
| 3 | [#2051](https://github.com/yastman/rag/issues/2051) — rewire voice handler | open | Replace `Bot.handle_voice`'s `build_graph(...).ainvoke(...)` with the same `create_bot_agent`-driven path the text supervisor already uses. Pre-agent transcription stays. Preserves checkpointer namespace + `trace_id` injection. |
| 4 | [#2048](https://github.com/yastman/rag/issues/2048) — extract `PropertyBot` lifecycle | open, **unblocked** | Was waiting on #1948's `src.runtime` migration so the extracted lifecycle module would not need `from telegram_bot.*` back-imports. PR [#2135](https://github.com/yastman/rag/pull/2135) closed the last allowlist entry, so #2048 can now extract `_warmup_bge`, `_polling_lock_heartbeat_tick`, `_postgres_pool_init`, `_kommo_seed`, `_register_handlers`, etc. into a thin `bot_lifecycle.py` module while keeping `bot.py` as a facade. |
| 5 | ADR-0010 → Accepted | follow-up PR | Same PR removes `telegram_bot/graph/graph.py`, deletes the StateGraph-only nodes, and updates this doc's `Status` to `Done`. |

## Next executable slice

For a contributor picking up the next move:

* **#2051 — rewire voice handler.** This is the highest-value next slice and
  is the one that lets ADR-0010 flip to Accepted. The work is bounded:
    1. Build the voice variant of the agent inside
       `Bot.handle_voice` (mirror `_handle_query_supervisor`).
    2. Move the pre-agent transcription stage so it runs before
       `create_bot_agent.ainvoke(...)`.
    3. Swap `build_graph(...).ainvoke(...)` for the agent invocation.
    4. Run `python -m pytest tests/unit/graph/ tests/unit/test_bot_handlers.py -q`
       (per the issue's `Validation` block).
* **#2048 — extract `PropertyBot` lifecycle.** Independent of #2051.
  Now unblocked. Recommended sub-slices:
    - 4a. lifecycle (`start`, `stop`, `_warmup_bge`,
      `_polling_lock_heartbeat_tick`);
    - 4b. handlers registration (`_register_handlers` + the FSM
      handlers that hang off it);
    - 4c. pre-agent (`_handle_apartment_fast_path`,
      `_extract_pre_agent_filters`, `_get_pre_agent_filter_extractor`);
    - 4d. streaming + scoring (`_astream_supervisor_with_recovery`,
      `_ainvoke_supervisor_with_recovery`).
  Each sub-slice mirrors the [#1265](https://github.com/yastman/rag/issues/1265) `_bot_<topic>.py`
  pattern (PR-1..PR-7); each one ratchets the `bot.py` line-count
  ceiling down further.

## Cross-references

* [ADR-0010 — voice path migration plan](../adr/0010-voice-path-create-agent-migration-plan.md) — the *why*.
* [`tests/contract/test_voice_create_agent_migration_plan_contract.py`](../../tests/contract/test_voice_create_agent_migration_plan_contract.py) — pins ADR-0010 status + structure.
* [`tests/contract/test_voice_migration_sequence_doc_contract.py`](../../tests/contract/test_voice_migration_sequence_doc_contract.py) — pins this document.
* [`tests/contract/test_layering_no_telegram_bot_imports_contract.py`](../../tests/contract/test_layering_no_telegram_bot_imports_contract.py) — guards the `src/` ↔ `telegram_bot/` boundary that #2048 must respect when extracting lifecycle.
* [#1265](https://github.com/yastman/rag/issues/1265) — bot.py decomposition track that #2048 piggy-backs on.
