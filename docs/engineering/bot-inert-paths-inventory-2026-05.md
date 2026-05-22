# Telegram Bot Inert Runtime Paths Inventory — 2026-05

Working artefact for [#1998](https://github.com/yastman/rag/issues/1998)
("bot: decide cleanup or wiring for inert runtime paths"). Sub-issue of
the [#1978](https://github.com/yastman/rag/issues/1978) dead-code audit.

Companion docs:

- [`dead-code-audit-2026-05.md`](dead-code-audit-2026-05.md) — overall
  dead-code inventory across the repo.
- `scripts-inventory-2026-05.md` (sister inventory for `scripts/`,
  delivered separately under #1997).

## Methodology (per the #1978 four-question check)

Each candidate was checked for:

1. **Production caller** — any non-test, non-self Python import or call.
2. **Env / config wiring** — any code path that reads an env flag and
   actually instantiates the symbol at runtime (not just a config field
   declaration without a producer).
3. **Test surface** — what tests reference it, and do they cover live
   behaviour or only the inert symbol itself?
4. **Documentation surface** — operator-facing runbooks or READMEs that
   present the symbol as live runtime behaviour.

A symbol is `delete_now` only when **(1) is empty** and **(2) is empty**
and **(3) tests cover only the inert symbol** and **(4) no doc presents
it as live**.

## Inventory

### `delete_now` — landed in this slice

| Symbol | Evidence |
|--------|----------|
| `telegram_bot/services/manager_menu.py` (10 LOC, single function `render_start_menu`) | (1) zero non-test callers — `bot.py` imports `dialogs.manager_menu`, not `services.manager_menu` (different file); (2) no env wiring; (3) only two smoke tests reference it (`test_render_manager_menu`, `test_render_client_menu` in `tests/smoke/test_manager_flow.py`), both of which test the inert symbol itself, not a runtime flow — they go away with the module; (4) no doc presents it as live. The sibling `telegram_bot/dialogs/manager_menu.py` (133 LOC) is the live `aiogram_dialog` implementation and is unaffected. |

### `archive` — keep in tree, mark as inert

These files are inert today but the implementation is non-trivial,
self-contained, and matches an articulated future use case. Deleting
them would lose engineering history. Each row records the trigger
that should re-enable wiring.

| Symbol | LOC | Why archive | Trigger to re-wire |
|--------|-----|-------------|--------------------|
| `telegram_bot/runtime_events.py` | 220 | Structured runtime-event JSONL writer. Disabled by default (`RUNTIME_EVENTS_ENABLED=0`) and performs no I/O when off, but no production code path emits an event today — the writer is fully tested in isolation but never called. | Wire the event writer into `bot.py` lifecycle hooks and node entry points (graph or aiogram middleware). |
| `telegram_bot/runtime_events_config.py` | 64 | Companion env loader for `runtime_events.py`. Together they form a self-contained pair. | Same trigger as `runtime_events.py`. |
| `telegram_bot/services/semantic_classifier.py` | 194 | RedisVL `SemanticRouter`-based query classifier. The `CLASSIFIER_MODE` env (`graph/config.py:151`) and the `GraphContext.semantic_classifier` field exist, **but the field is never assigned** — `bot.py` does not instantiate `SemanticClassifier` even when `CLASSIFIER_MODE=semantic`. The fall-back log in `graph/nodes/classify.py:303` covers a code path that cannot fire today. | Instantiate in `bot.py` lifecycle when `CLASSIFIER_MODE=semantic` and assign onto `GraphContext`. Only after that is the existing test surface meaningful. |
| `telegram_bot/services/normalizer.py` | 126 | RU/UK query normalizer (semantic-noise stripping for cache hit rates). No non-test callers; designed as an optional pre-processor. | Wire into `cache_check` or `query_preprocessor` flows when the cache-hit improvement is benchmarked. |
| `telegram_bot/dialogs/catalog_transport.py` | 38 | Single helper `render_catalog_results_with_keyboard`. Only `tests/unit/services/test_catalog_rendering.py` references it. | Wire from `dialogs/catalog.py` if the keyboard-mode branch is ever enabled in production. |

For each `archive` row the test file documents the inert state in its
docstring; if the trigger fires, the test surface is already in place
to validate the wiring.

> **Why these are not `delete_now`**: each implementation has documented
> design intent (env flag, config field, route registration) and the
> issue body explicitly classifies them as "inert ... should be either
> wired intentionally or removed". The lower-risk decision today is
> "wired intentionally" — kept with the inventory entry as the
> commitment marker. A follow-up issue may convert these to `delete_now`
> if 90 days pass without wiring.

### `keep` — verified live, do not retire

(none added in this slice)

### `needs_decision` — explicitly deferred

| Symbol | Question |
|--------|----------|
| (carried over from `dead-code-audit-2026-05.md`) | none specific to bot inert paths |

## Acceptance against #1998

- [x] Decision recorded for each candidate (`delete_now` / `archive` /
      `keep` / `needs_decision`).
- [x] Removed paths have tests adjusted in the same PR (`services/
      manager_menu.py` removal drops two smoke tests in
      `tests/smoke/test_manager_flow.py`).
- [x] Kept-inert paths have a documented trigger for re-wiring (table
      above).
- [x] Focused bot tests / import checks pass (see commit verification
      block).

## How to extend this doc

When a follow-up PR wires an `archive` row, move the row into `keep`
with the wiring entry point. When a follow-up PR retires an `archive`
row, move it to `delete_now` with the four-question evidence and pin
the deletion in `tests/contract/test_dead_code_audit_2026_05_contract.py`.

## Refs

- [#1998](https://github.com/yastman/rag/issues/1998) (this issue).
- Parent: [#1978](https://github.com/yastman/rag/issues/1978).
- Companion docs: [`dead-code-audit-2026-05.md`](dead-code-audit-2026-05.md),
  `scripts-inventory-2026-05.md` (delivered separately under #1997).
- Contract test: [`tests/contract/test_dead_code_audit_2026_05_contract.py`](../../tests/contract/test_dead_code_audit_2026_05_contract.py).
