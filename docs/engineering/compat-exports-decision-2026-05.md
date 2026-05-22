# Deprecated Compatibility Exports — Decision Record (2026-05)

Decision artefact for [#1999](https://github.com/yastman/rag/issues/1999)
("refactor: decide and remove deprecated compat exports"). Sub-issue of
the [#1978](https://github.com/yastman/rag/issues/1978) dead-code audit
(`lane:design-first`).

Companion docs:

- [`dead-code-audit-2026-05.md`](dead-code-audit-2026-05.md) — broader
  inventory of dead runtime code paths.
- `bot-inert-paths-inventory-2026-05.md` (delivered separately under
  #1998).
- `scripts-inventory-2026-05.md` (delivered separately under #1997).

## Surface in scope

Five package `__init__.py` files declare lazy `_DEPRECATED_EXPORTS`
dictionaries that route legacy attribute access through
[`src/_compat.py::load_deprecated_package_export`](../../src/_compat.py),
which emits a `DeprecationWarning` and re-resolves the attribute from
its canonical submodule:

| Package | Deprecated symbols |
|---------|--------------------|
| `src/__init__.py` | `ClaudeContextualizer`, `DBSFColBERTSearchEngine`, `DocumentChunker`, `DocumentIndexer`, `RAGPipeline`, `Settings`, `UniversalDocumentParser` |
| `src/config/__init__.py` | `SmallToBigMode` |
| `src/contextualization/__init__.py` | `ContextualizeProvider` |
| `src/ingestion/__init__.py` | `DoclingClient`, `DoclingConfig`, `chunk_document`, `create_text_for_embedding`, `get_ingestion_status`, `ingest_from_directory`, `ingest_from_gdrive`, `parse_document` |
| `src/ingestion/unified/__init__.py` | `FileState`, `QdrantHybridWriter`, `UnifiedConfig`, `UnifiedStateManager`, `WriteStats` |

Internal callers were verified with `grep -rn "from src import <sym>"`
(and the equivalent for each subpackage) over `src/`,
`telegram_bot/`, `mini_app/`, `services/`, `scripts/`, `tests/`,
ignoring the package's own `__init__.py` and `_compat.py`.

## Findings

- **Zero non-test internal callers** use any of these deprecated paths
  on `dev` (`0fb989e8`). The five symbols that show up in
  `tests/unit/test_lazy_imports.py` are the test parametrize fixtures
  that *validate the deprecation behaviour itself*; they do not exercise
  a runtime code path.
- The non-deprecated lazy attributes in `src/ingestion/__init__.py`'s
  `_LAZY_ATTRS` (`DocumentChunker`, `DocumentIndexer`, etc.) **do** have
  live callers (e.g. `src/core/pipeline.py:16`). Those imports go
  through the lazy shim, **not** the deprecated shim, and remain
  supported.
- External API compatibility is **not proven**. The repository is an
  internal RAG platform, not a published PyPI package, and there is no
  `setup.py` / `pyproject.toml` distribution metadata that exposes
  these names as a public API. Still, downstream consumers (mini-app
  runtime images, VPS-deployed bots) may have been written against the
  deprecated paths during development.

## Decision

**Keep all deprecated exports for one release** (per the
"Acceptance Criteria" option B in the issue body), then remove. The
shim machinery is small (one helper + five `__getattr__` hooks) and
has zero hot-path cost — `__getattr__` only fires on the first access
to a non-existent module attribute. Removal in a single sweep is safer
than per-symbol guesswork because:

1. Internal callers all use canonical submodule imports today;
   removal does not break any production code path inside the repo.
2. The deprecation warning is the contract — once a release ships the
   warning, downstream code has time to migrate before removal.
3. Maintaining five `_DEPRECATED_EXPORTS` dictionaries plus
   `src/_compat.py` is recurring cost; consolidating the removal makes
   that cost end at a single point in time.

### Removal plan (follow-up PRs, not in this slice)

The follow-up work happens **after** the next release tag. Each follow-up
PR should:

1. Delete the corresponding `_DEPRECATED_EXPORTS` entry from the
   package `__init__.py`.
2. Drop the matching parametrize row from
   `tests/unit/test_lazy_imports.py` (`test_pruned_package_exports_keep
   _deprecated_compatibility` and
   `test_deprecated_package_exports_support_explicit_import`).
3. Once the last `_DEPRECATED_EXPORTS` dictionary is empty, delete the
   `__getattr__` shim from that package's `__init__.py`.
4. Once **all** `_DEPRECATED_EXPORTS` dictionaries are gone, delete
   `src/_compat.py` and the `from src._compat import …` lines at the
   top of each affected `__init__.py`.
5. Pin the deletions in
   [`tests/contract/test_dead_code_audit_2026_05_contract.py`](../../tests/contract/test_dead_code_audit_2026_05_contract.py)
   so the shims do not accidentally come back.

Suggested PR cuts (one per row, smallest blast radius first):

| Order | Package | Symbol(s) | Notes |
|-------|---------|-----------|-------|
| 1 | `src/contextualization/__init__.py` | `ContextualizeProvider` | one symbol, one test parametrize row |
| 2 | `src/config/__init__.py` | `SmallToBigMode` | one symbol, one test parametrize row |
| 3 | `src/ingestion/unified/__init__.py` | five symbols | self-contained subpackage |
| 4 | `src/ingestion/__init__.py` | eight symbols | larger but isolated |
| 5 | `src/__init__.py` | seven symbols | top-level removal |
| 6 | delete `src/_compat.py` and the import lines | — | last step, only after all five `__init__.py` are clean |

## What this PR delivers

- **Decision recorded** (this document) — keep for one release, then
  remove per the plan above.
- **No code change.** Internal callers are already on canonical paths;
  no migration is needed before the deletion phase.
- **Owner**: tech-debt maintainer, scheduled for the post-release tag.

## Acceptance against #1999

- [x] Decision recorded: keep for one release, then remove per the
      sequenced plan above.
- [x] Migration notes accompany each shim entry — already present in
      the existing `_DEPRECATED_EXPORTS` dicts as the third
      tuple element (e.g. `"from src.config import Settings"`); no
      code change needed.
- [x] Removal owner and schedule documented (tech-debt maintainer,
      post next release tag).
- [ ] Imports / tests verified after removal — deferred to the
      follow-up PRs that actually delete each row.

## Refs

- [#1999](https://github.com/yastman/rag/issues/1999) (this issue).
- Parent: [#1978](https://github.com/yastman/rag/issues/1978).
- Companion docs:
  [`dead-code-audit-2026-05.md`](dead-code-audit-2026-05.md).
- Compatibility helper: [`src/_compat.py`](../../src/_compat.py).
- Existing test surface:
  [`tests/unit/test_lazy_imports.py`](../../tests/unit/test_lazy_imports.py).
