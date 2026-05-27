# `telegram_bot/bot.py` decomposition plan — 2026-05-27

**Issue:** [#1265 — refactor: decompose bot.py god-object after current PropertyBot audit](https://github.com/yastman/rag/issues/1265)
**Lane:** `lane:design-first`
**Verify:** `verify:repo-only`
**Status of this document:** Slice 2 plan. Slice 1 already shipped across PR-1…PR-7 referenced inside each `_bot_*.py` module.

This document is the design-first deliverable required by `lane:design-first`.
It captures (a) the post-Slice-1 inventory of `telegram_bot/bot.py`, (b) the
atomic-PR sequence proposed for Slice 2, and (c) the testing rules each PR
must satisfy. It is intentionally a plan, not an implementation — execution
is tracked under the child issues listed below.

## Slice 1 — done

Seven byte-for-byte extractions landed under #1265 and shrank `bot.py` from
~5099 → 4582 lines (–10 %). Each module is referenced from `bot.py` via thin
wrappers and is pinned by a contract test in `tests/contract/`.

| PR | Module | LOC | Concern |
|----|--------|-----|---------|
| PR-1 | `telegram_bot/_bot_state_helpers.py` | 77 | `_state_apartment_results`, `_state_control_message_id`, `_extract_current_turn` |
| PR-2 | `telegram_bot/_bot_observability.py` | 97 | `_build_trace_metadata`, `_write_voice_error_scores` |
| PR-3 | `telegram_bot/_bot_error_classification.py` | 86 | `_is_post_pipeline_cleanup_error`, `_is_checkpointer_runtime_error` |
| PR-4 | `telegram_bot/_bot_streaming.py` | 132 | `_new_draft_id`, `_stream_agent_to_draft`, `_extract_stream_chunk_text` |
| PR-5 | `telegram_bot/_bot_pre_agent.py` | 163 | `_build_pre_agent_state_contract`, `_has_async_method`, `_get_or_compute_pre_agent_dense`, `_prepare_pre_agent_retrieval_vectors` |
| PR-6 | `telegram_bot/_bot_kommo.py` | 57 | `_seed_kommo_access_token` |
| PR-7 | `telegram_bot/_bot_postgres_bootstrap.py` | 285 | `_extract_database_name`, `_ensure_postgres_database_exists`, `_ensure_realestate_schema` |
| **total** |  | **897** |  |

Slice-1 invariants (preserved by the contract tests):

- Module-level imports stay within stdlib + the helper's narrow third-party need.
- No `aiogram`, `langgraph`, `qdrant_client`, `langchain` or `fastapi` imports at module scope of an `_bot_*.py` file — keeps unit tests cheap.
- The `bot.py` thin wrappers preserve `from telegram_bot.bot import _xxx` resolution so existing tests keep working.

## Post-Slice-1 inventory

`bot.py` (4582 lines) breaks down roughly as:

| Concern | Approximate LOC | Representative methods |
|---------|-----------------|------------------------|
| Module preamble + free helpers (compat shims `create_bot_agent`, `build_graph`, `classify_query`, `detect_injection`) | 1–356 | top-of-file shims |
| `PropertyBot.__init__` | 370–557 | `__init__` |
| Misc instance helpers, history save bridge | 558–730 | `_spawn_history_save`, `_get_pre_agent_filter_extractor`, `_setup_middlewares`, `_register_handlers`, `_resolve_user_role` |
| Mini-app entry & deeplink | 749–973 | `_handle_deeplink_start`, `_process_miniapp_start`, `_run_miniapp_rag`, `_miniapp_subscriber_loop`, `_is_admin` |
| Menu / navigation / favourites callbacks | 979–1922 | `handle_menu_button`, `_handle_search`, `_handle_services`, `_handle_viewing`, `_handle_bookmarks`, `_handle_ask`, `handle_*_callback`, `handle_fav_*` |
| Free-form text query path (text agent) | 1922–2202 | `handle_query`, `_send_markdown_chunks`, `_handle_apartment_fast_path`, `_handle_client_direct_pipeline` |
| Supervisor query path (LangGraph) | 2202–2972 | `_handle_query_supervisor` (~750 LOC, the largest single method) |
| Streaming/sync supervisor recovery | 2973–3201 | `_astream_supervisor_with_recovery`, `_ainvoke_supervisor_with_recovery` |
| Voice path | 3201–3441 | `handle_voice` (#2051 child) |
| HITL flow | 3442–3570 | `_send_hitl_confirmation`, `handle_hitl_callback` |
| Feedback flow | 3571–3730 | `handle_feedback`, `handle_feedback_reason`, `_clear_feedback_confirmation_later` |
| Cache management callbacks | 3731–3873 | `handle_clearcache_callback`, `handle_menu_action` |
| Lifecycle (`start`/`stop`, warmup, polling lock heartbeat) | 3873–end | `start`, `_warmup_bge`, `_polling_lock_heartbeat_tick`, `stop` |

19 public `handle_*` methods and 12 private `_handle_*` dispatchers remain.

## Slice 2 — proposed extractions

Slice 2 targets the remaining ~3500 lines that are not pure helpers. The
guiding rule from Slice 1 still holds: every PR must be byte-for-byte
behaviour-preserving and pinned by a new contract test under
`tests/contract/`.

### PR-8 — Lifecycle extraction (tracked by [#2048](https://github.com/yastman/rag/issues/2048))

**Move target:** `telegram_bot/_bot_lifecycle.py`

**Methods extracted from `PropertyBot`:**

- `start` (lines 3873–4447, ~575 LOC)
- `_warmup_bge` (4448–4455, ~8 LOC)
- `_polling_lock_heartbeat_tick` (4456–4479, ~24 LOC)
- `stop` (4480–end, ~100 LOC)

**Approach:**

- Convert `start`/`stop` into module-level functions that take
  `(self) -> Awaitable[None]` so tests can mock the wiring without
  instantiating `PropertyBot`. (Or keep them as bound methods and
  delegate to module-level helpers — pick whichever passes the
  characterization test with the smallest call-site delta.)
- Lift `_warmup_bge` and `_polling_lock_heartbeat_tick` to module level
  with `(config, logger)` signatures.
- Keep the `PropertyBot.start`/`stop` methods on the class as thin
  wrappers (`return await _bot_lifecycle.start(self)`).

**Acceptance:**

- `bot.py` shrinks by ~700 lines.
- `_bot_lifecycle.py` has no `aiogram` / `langgraph` import at module
  scope (lazy imports allowed inside function bodies).
- New `tests/contract/test_bot_lifecycle_extraction_contract.py`
  asserts `bot.start is _bot_lifecycle.start_property_bot` (or the
  thin-wrapper equivalent) and that the import graph is clean.
- Existing tests under `tests/unit/test_bot_handlers.py` and
  `tests/unit/test_bot_scores.py` keep passing without changes.

### PR-9 — Handlers extraction (proposed new child issue)

**Move target:** `telegram_bot/_bot_handlers.py`

**Methods extracted:**

- All 19 public `handle_*` methods (menu, callbacks, query, voice, HITL, feedback, clearcache).
- The 12 private `_handle_*` dispatchers (search, services, viewing, bookmarks, ask, manager, group_message, apartment_fast_path, client_direct_pipeline, query_supervisor, demo, complete_handoff, close_handoff).

**Approach:**

- Each handler becomes a module-level `async def` that takes `(self, …)`
  as its first argument. The `PropertyBot` class keeps `handle_*` /
  `_handle_*` methods as thin delegates.
- Note that `_handle_query_supervisor` is ~750 LOC on its own — it
  splits naturally into:
  - state-prep section,
  - graph-invoke section (the `_astream_supervisor_with_recovery` /
    `_ainvoke_supervisor_with_recovery` pair already lives lower in the
    file and can move with the handler),
  - response-emit section.
  Each section becomes a private function inside `_bot_handlers.py`.

**Risk:** highest in the plan — `handle_query` and
`_handle_query_supervisor` are the hottest call sites. Land in two
sub-PRs: callbacks + menu first, query/voice last.

**Acceptance:**

- `bot.py` shrinks by ~2000 lines.
- New contract test pins `bot.handle_X is _bot_handlers.X` for every
  handler.
- The existing characterization tests under
  `tests/unit/test_bot_handlers.py` (the largest single test file in
  the repo) keep passing without signature changes.

### PR-10 — Supervisor recovery extraction (proposed)

**Move target:** `telegram_bot/_bot_supervisor_recovery.py`

**Methods extracted:**

- `_astream_supervisor_with_recovery` (~140 LOC)
- `_ainvoke_supervisor_with_recovery` (~85 LOC)

**Approach:**

- Lift to module-level functions taking `(self, agent, …)`. The
  `_run_once` inner closure stays inside the function body; nothing in
  the body touches `self` after the first line, so the recovery loop is
  effectively pure.

**Acceptance:**

- `bot.py` shrinks by ~225 lines.
- Contract test pins both helpers as module-level callables.

### PR-11 — Optional: scoring/Langfuse glue (low priority)

The `bot_scoring.py` mentioned in #1265's target decomposition already
exists outside `bot.py` as `telegram_bot/scoring.py` (31 LOC). Only the
`PropertyBot._spawn_history_save` and a handful of inline score writes
remain inside `bot.py`. Defer until PR-8 / PR-9 / PR-10 land — the
remaining glue may end up small enough to leave in place.

## Testing strategy — TDD characterization

Every Slice 2 PR follows the same characterization-first loop, mirroring
Slice 1:

1. **Capture current behaviour.** Before moving anything, add a new
   contract test under `tests/contract/` that asserts the bound-method
   identity (`PropertyBot.X is _bot_module.X` or thin-wrapper
   equivalent) and the import-graph rules. The contract test passes
   only after the extraction.
2. **Add narrow unit coverage if missing.** If the moved method is not
   already exercised by `tests/unit/test_bot_handlers.py` /
   `tests/unit/test_bot_scores.py`, write a targeted unit test that
   pins the observable behaviour (return value, side effects on
   `self`, calls to mocked dependencies) before the move.
3. **Cut the slice.** Move the body to the new module, leave a thin
   wrapper on the class, run `make test-unit`. Both the new contract
   test and the existing unit tests must stay green.
4. **Lint the import graph.** `_bot_*.py` files MUST NOT import
   `aiogram`, `langgraph`, `qdrant_client` or `fastapi` at module
   scope. Catch this in the contract test.

## Verification command

For every Slice 2 PR (matching the issue body's `Validation` line):

```
uv run --python 3.12 pytest \
  tests/unit/test_bot_handlers.py \
  tests/unit/test_bot_scores.py \
  tests/contract/test_bot_*_extraction_contract.py \
  -q --timeout=30
```

## Sequencing

1. PR-8 (lifecycle, #2048) — first, smallest delta, sets the pattern for `_bot_*.py` extraction with `self` argument.
2. PR-9 (handlers, new child) — split into PR-9a (callbacks/menu/feedback/HITL) and PR-9b (query/voice). PR-9b is the biggest piece of work in the plan.
3. PR-10 (supervisor recovery) — independent of the others; can land in parallel once the lifecycle pattern is set.
4. PR-11 (scoring glue) — only if the residual `bot.py` size still merits it.

## Out of scope

- Re-naming `_bot_*.py` to `bot_*.py`. The leading-underscore convention
  signals "internal helpers re-exported by the `bot.py` facade" and
  should be kept until the entire god-object is dissolved.
- Splitting `bot.py` into a package directory. That is a larger
  follow-up that should only be considered after Slice 2 lands.
- Voice path migration to `create_agent` — tracked separately by #2051
  on top of PR-9b.

## Decision

Adopt this plan. Execute PR-8 under #2048, then file follow-up child
issues for PR-9 / PR-10 / PR-11. Keep #1265 open as the umbrella for
the decomposition and close it only after the residual `bot.py` is at
or below 1500 lines.
