# Dead-Code Audit — 2026-05 Slice 1

Working artefact for [#1978](https://github.com/yastman/rag/issues/1978)
("Audit and remove dead runtime code paths"). Companion to:

- [#1944](https://github.com/yastman/rag/issues/1944) — broader repo audit
  roll-up.
- [#1947](https://github.com/yastman/rag/issues/1947) — stale config-only
  cleanup.

This file is the **inventory** the issue's "Acceptance Criteria" calls for.
It uses the four classifications from the issue body and is updated as
slices land. The first deletion PR sits alongside this file.

## Methodology

For each candidate the audit answers four questions, in order:

1. **Runtime entrypoints** — does Docker/Compose/K8s, Makefile, CI workflow,
   CLI script, or `tests/e2e` smoke path reach this symbol?
2. **Import / call graph** — does any non-test, non-self caller import or
   call this symbol? (Verified with `grep -rn` over `src/`, `telegram_bot/`,
   `mini_app/`, `services/`, `scripts/`, `docs/`, `Makefile`, `.github/`.)
3. **Public compatibility surface** — is this re-exported from a package
   `__init__.py` or referenced by a documented external contract?
4. **Test surface** — do tests reference it, and do those tests cover only
   already-deleted behaviour?

A symbol enters `delete_now` only when the first three answers are "no" and
the fourth is either "no" or "the tests test only this dead symbol".

## Inventory

### `delete_now` — landed in this slice

| Symbol | File | Evidence |
|--------|------|----------|
| `index_test_properties_prod` script | `scripts/index_test_properties_prod.py` (128 LOC) | `grep -rn index_test_properties_prod` over `src/`, `telegram_bot/`, `tests/`, `docs/`, `scripts/`, `Makefile`, `.github/` returns **zero hits** outside the file itself. The sibling `scripts/index_test_properties.py` is the live counterpart. The script imports `VoyageService` from the bot package and was a one-off manual UPSERT helper for production Qdrant — replaced by the unified ingestion pipeline (#1532). Pinned as not-coming-back by `tests/contract/test_dead_code_audit_2026_05_contract.py`. |

### `needs_decision` — explicitly deferred

| Symbol | File | Why deferred |
|--------|------|--------------|
| `src/retrieval/search_engines.py` (~30 KB) | duplicates the name of `src/evaluation/search_engines.py` (~14 KB) | `src/evaluation/search_engines.py` has live callers (`src/evaluation/run_ab_test.py`, `src/evaluation/search_engines_rerank.py`, `src/evaluation/smoke_test.py`, `tests/unit/evaluation/test_search_engines_eval.py`). `src/retrieval/search_engines.py` is referenced only by `tests/unit/retrieval/test_search_engines.py` and a single comment in `telegram_bot/services/qdrant.py:32` ("ACORN filtered search (Feb 2026): Code ready in src/retrieval/search_engines.py"). The retrieval module is therefore **dead-but-tested**. Decision required: either delete with its tests (treating the comment as historical) or wire the ACORN feature in. Out of scope for an automated dead-code pass. |

### `keep` — verified live, do not retire

| Symbol | Reason |
|--------|--------|
| `telegram_bot/services/voyage.py` | Despite being a 7-line re-export shim (`from src.services.voyage import VoyageService`), it has **10+ callers** across `src/ingestion/`, `scripts/`, and `telegram_bot/` that use the bot-package import path. Removing the shim would force a coordinated rename across all callers; treat as a separate refactor (not dead). |

### `quarantine` — already covered by other contracts

The legacy ingestion modules called out in the issue
(`src/ingestion/docling_client.py`, `src/ingestion/service.py`) are already
guarded by [`tests/contract/test_legacy_ingestion_removed_contract.py`](../../tests/contract/test_legacy_ingestion_removed_contract.py)
with documented `KNOWN_LIVE_CALLERS`, so they are intentionally retained
until those callers migrate. No new action here; tracked under #1532.

## Acceptance against #1978

- [x] Inventory produced with `delete_now`, `quarantine`, `keep`,
      `needs_decision` sections.
- [x] At least one low-risk deletion PR identified — delivered alongside
      this doc as the same PR (`scripts/index_test_properties_prod.py`).
- [x] Methodology applied per candidate (no blind deletions).
- [ ] Subsequent slices will add rows under `delete_now` as they land.

## How to extend this doc

Each follow-up dead-code PR appends a row to `delete_now` with:

- the file/symbol removed;
- the four-question evidence (entrypoints, call graph, compatibility,
  test surface);
- the contract test that pins the deletion (or `n/a` with rationale).

Audit-only PRs (no deletion yet) move rows into `needs_decision` and link
the follow-up issue.

## Refs

- Source issue: [#1978](https://github.com/yastman/rag/issues/1978)
- Methodology cross-link:
  [`docs/engineering/repo-hygiene-runbook.md`](repo-hygiene-runbook.md)
- Contract test:
  [`tests/contract/test_dead_code_audit_2026_05_contract.py`](../../tests/contract/test_dead_code_audit_2026_05_contract.py)
