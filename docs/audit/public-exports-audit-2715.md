# Public Exports, Compatibility Shims, and Stale API Surfaces Audit

Issue: #2715

## Audit Table

| Export / shim | Owner package | Current caller(s) | Compatibility reason | Keep until | Action |
|---|---|---|---|---|---|
| `src/__init__.__getattr__` → `ClaudeContextualizer`, `DBSFColBERTSearchEngine`, `DocumentChunker`, `DocumentIndexer`, `Settings`, `UniversalDocumentParser` | `src` | `test_lazy_imports.py` only (intentional compat test) | Deprecated shim via `_compat.py`; warns on use | After all callers migrated to canonical paths | Keep shim; test intentionally covers compat path; no production callers |
| `src/config.__getattr__` → `SmallToBigMode` | `src.config` | `test_lazy_imports.py` (compat test) | Deprecated shim via `_compat.py` | After callers migrate to `from src.config.constants import SmallToBigMode` | Keep shim; test intentional |
| `src/contextualization.__getattr__` → `ClaudeContextualizer`, `GroqContextualizer`, `OpenAIContextualizer`, `ContextualizeProvider` | `src.contextualization` | `test_lazy_imports.py` (compat test) | Deprecated shims via `_compat.py`; `__all__` advertises old names | After callers migrate to canonical submodule imports | Keep shim; create child issue to remove after migration |
| `src/ingestion.__getattr__` → `DoclingClient`, `DoclingConfig`, `chunk_document`, `create_text_for_embedding`, `get_ingestion_status`, `ingest_from_directory`, `ingest_from_gdrive`, `parse_document` | `src.ingestion` | `test_lazy_imports.py` (compat test for `DoclingClient`) | Deprecated shims via `_compat.py` | After callers migrate to canonical submodule imports | Keep shim; no production callers found |
| `src/ingestion/unified.__getattr__` → `FileState`, `QdrantHybridWriter`, `UnifiedConfig`, `UnifiedStateManager`, `WriteStats` | `src.ingestion.unified` | `test_lazy_imports.py` (compat test for `UnifiedConfig`) | Deprecated shims via `_compat.py` | After callers migrate to canonical paths | Keep shim; no production callers found |
| `src/services.__init__` → `BGEM3Client`, `BGEM3SyncClient` (lazy via `__getattr__`) | `src.services` | `src/runtime/integrations/cache.py` → `src.services.vectorizers` directly | Lazy export for convenience; canonical path is `src.services.bge_m3_client` | No removal needed; clean lazy export | Keep; active and correctly wired |
| `telegram_bot/services.__init__` → `VoyageService` (TYPE_CHECKING + `__all__` + `_IMPORT_MAP`) | `telegram_bot.services` | None — archived in #2631 | Voyage path removed in #2631; no live callers | **Already overdue** (#2631) | **REMOVED in this PR** — stale export, test `test_telegram_bot_services_init_has_no_voyage_service` was failing |
| `telegram_bot/services.__init__` → `BgeM3CacheVectorizer` (TYPE_CHECKING only, not in `__all__`, not in `_IMPORT_MAP`) | `telegram_bot.services` | None — callers import from `src.services.vectorizers` directly | Incomplete/stale TYPE_CHECKING import, never wired | Already dead | **REMOVED in this PR** — dead TYPE_CHECKING import with no callers via this path |
| `telegram_bot/graph/config.py` → `GraphConfig` re-export from `src.runtime.graph.config` | `telegram_bot.graph` | `telegram_bot/agents/history_graph/nodes.py`, `telegram_bot/graph/nodes/generate.py`, `telegram_bot/graph/nodes/grade.py`, `telegram_bot/graph/nodes/rewrite.py`, `telegram_bot/services/generate_response.py`, many test files | Back-compat shim after reverse-layering migration (#2045/#2049) | After all callers migrated to `from src.runtime.graph.config import GraphConfig` | Keep shim; active callers. Open child issue for migration |
| `telegram_bot/graph/state.py` → `RAGState`, `make_initial_state` re-export from `src.runtime.graph.state` | `telegram_bot.graph` | Many test and production files (20+ callers) | Back-compat shim after reverse-layering migration (#2045/#2049) | After all callers migrated to `from src.runtime.graph.state import ...` | Keep shim; high caller count. Open child issue for migration |
| `telegram_bot/graph/edges.py` → `route_*` re-exports from `src.runtime.graph.edges` | `telegram_bot.graph` | `tests/unit/graph/test_call_limits.py`, `tests/unit/graph/test_edges.py` | Back-compat shim after reverse-layering migration (#2045/#2049) | After test files migrated to canonical import | Keep shim; test callers. Open child issue |
| `telegram_bot/graph/context.py` → `GraphContext` re-export from `src.runtime.graph.context` | `telegram_bot.graph` | No callers found via `telegram_bot.graph.context` | Back-compat shim; no active callers | Immediate candidate for removal | Open child issue to remove; confirm with broader grep before deleting |
| `telegram_bot/graph/nodes/classify.py` → back-compat re-export from `src.runtime.graph.nodes.classify` | `telegram_bot.graph.nodes` | `telegram_bot/graph/middleware/classify.py` | Back-compat shim after Slice B migration (#2049/#1948) | After `middleware/classify.py` migrated to canonical import | Keep shim; active caller. Open child issue |
| `telegram_bot/graph/nodes/guard.py` → back-compat re-export from `src.runtime.graph.nodes.guard` | `telegram_bot.graph.nodes` | `telegram_bot/graph/middleware/guard.py` | Back-compat shim after Slice B migration (#2049/#1948) | After `middleware/guard.py` migrated to canonical import | Keep shim; active caller. Open child issue |
| `telegram_bot/graph/nodes/transcribe.py` → back-compat re-export from `src.runtime.graph.nodes.transcribe` | `telegram_bot.graph.nodes` | No callers found via `telegram_bot.graph.nodes.transcribe` directly | Back-compat shim after Slice B migration | After confirming no callers | Open child issue to remove |
| `telegram_bot/graph/__init__.py` → `GraphConfig`, `RAGState`, `build_graph`, `make_initial_state` | `telegram_bot.graph` | Tests import from submodules directly, not from `telegram_bot.graph` top-level | Primary public API of `telegram_bot.graph` | Active; no changes needed | Keep; this is the intended public surface for the graph package |
| `src/runtime/__init__.py` (empty / migration placeholder) | `src.runtime` | N/A — exposes nothing | Migration destination package for #1948/#2045/#2049 | Until migration slices complete | Keep as placeholder; documented in module docstring |
| `src/runtime/integrations/__init__.py` (empty) | `src.runtime.integrations` | N/A | Migration destination package | Until migration slices complete | Keep as placeholder |
| `src/runtime/services/__init__.py` (empty) | `src.runtime.services` | N/A | Migration destination package | Until migration slices complete | Keep as placeholder |
| `archive/scripts/eval/run_experiment.py` and `scripts/archive/run_experiment.py` → `from telegram_bot.graph.graph import build_graph`, `from telegram_bot.graph.state import make_initial_state` | `archive/`, `scripts/archive/` | These are archived scripts | Old import path; live canonical path exists in `src.runtime.graph` | N/A (archived) | No action required; archived code |

## Changes Made in This PR

1. **Removed `VoyageService`** from `telegram_bot/services/__init__.py` (`TYPE_CHECKING` block, `__all__`, and `_IMPORT_MAP`). VoyageService was archived in #2631 with no live callers. The existing test `test_telegram_bot_services_init_has_no_voyage_service` was failing as a result.

2. **Removed stale `BgeM3CacheVectorizer`** from `TYPE_CHECKING` block in `telegram_bot/services/__init__.py`. It was present only in `TYPE_CHECKING` but absent from `__all__` and `_IMPORT_MAP` — never a functional export. All callers import `BgeM3CacheVectorizer` directly from `src.services.vectorizers`.

## Child Issues Recommended

- Migrate `telegram_bot/graph/config.py` callers to `from src.runtime.graph.config import GraphConfig` and delete the shim.
- Migrate `telegram_bot/graph/state.py` callers to `from src.runtime.graph.state import ...` and delete the shim.
- Migrate `telegram_bot/graph/edges.py` test callers and delete the shim.
- Confirm zero callers and delete `telegram_bot/graph/context.py` shim.
- Confirm zero callers and delete `telegram_bot/graph/nodes/transcribe.py` shim.
- Migrate `telegram_bot/graph/nodes/classify.py` and `guard.py` shim callers to canonical `src.runtime.graph.nodes.*` paths.
- Clean up deprecated `src/contextualization.__init__` exports once all callers use canonical paths.

## Docs

No documentation found advertising old import paths as preferred. The `telegram_bot/graph/*.py` shim docstrings already state canonical alternatives.

## Tests

Tests in `tests/unit/test_lazy_imports.py` intentionally exercise deprecated shim paths using `pytest.deprecated_call()` — these are correct and should be preserved until shims are removed.
