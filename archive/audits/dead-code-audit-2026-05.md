# Dead-Code Audit — 2026-05 Slice 1

_Archived from `docs/engineering/dead-code-audit-2026-05.md` during #2613 cleanup. This is historical methodology/evidence, not an active roadmap._

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
