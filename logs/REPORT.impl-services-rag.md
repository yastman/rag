# Worker Finish Report: impl-services-rag (card_1275fa96a00c)

## Status: DONE

**Branch:** `fix/services-rag-slice`
**Commit:** `c80f4af03b`

---

## Moved Files (15)

All 15 files relocated from `telegram_bot/services/` → `telegram_bot/services/rag/`:

| File | Note |
|---|---|
| `rag_core.py` | Core RAG helpers (embedding, rerank, cache check, rewrite) |
| `cache_policy.py` | Semantic cache decision logic |
| `grounding_policy.py` | Grounding/reuse policy |
| `query_analyzer.py` | LLM-based query analysis |
| `query_filter_signal.py` | Filter signature detection |
| `query_preprocessor.py` | HyDE + short-query expansion |
| `coverage_mode.py` | Coverage mode detection |
| `small_to_big.py` | Small-to-big context expansion |
| `colbert_reranker.py` | ColBERT reranker service |
| `vectorizers.py` | BGE-M3 Redis vectorizer shim |
| `semantic_classifier.py` | Semantic query classifier |
| `bge_m3_client.py` | BGE-M3 client re-export shim |
| `bge_m3_query_bundle.py` | BGE-M3 query bundle re-export shim |
| `voyage.py` | Voyage AI service re-export shim |
| `response_style_detector.py` | Response style detection |

---

## Importer Migration

**Total files updated:** 21

- `telegram_bot/agents/rag_pipeline.py` — 7 import lines rewritten
- `telegram_bot/integrations/prompt_templates.py` — 1 import line
- `telegram_bot/services/__init__.py` — `QueryAnalyzer` lazy-import path updated
- 18 test files in `tests/` (unit, smoke, chaos, integration)

**Intra-group imports fixed** (within moved files):
- `rag_core.py`: `bge_m3_query_bundle`, `cache_policy`, `colbert_reranker` → `services.rag.*`
- `colbert_reranker.py`: `bge_m3_client` → `services.rag.bge_m3_client`
- `cache_policy.py`: `grounding_policy`, `query_filter_signal` → `services.rag.*`

**Patch strings updated** (unittest.mock.patch):
- `telegram_bot.services.colbert_reranker.ColbertRerankerService` → `telegram_bot.services.rag.colbert_reranker.ColbertRerankerService` (3 occurrences)
- `telegram_bot.services.voyage.get_client` → `telegram_bot.services.rag.voyage.get_client` (1 occurrence)

**monkeypatch.delitem strings** auto-updated by sed:
- `telegram_bot.services.query_analyzer` → `telegram_bot.services.rag.query_analyzer` (2 occurrences)

**`from telegram_bot.services import query_analyzer as qa_mod`** → `from telegram_bot.services.rag import query_analyzer as qa_mod` (3 occurrences)

---

## Pre-existing Fixes Applied

1. **`telegram_bot/observability.py`** — Added `get_client` and `observe` no-op stubs.
   `rag_core.py` and `response_style_detector.py` (and crm_notes, crm_tasks, kommo_token_store)
   all imported these from `telegram_bot.observability`; they were broken since Langfuse removal
   (#2969) missed adding stubs. This is consistent with what the observability slice commit
   (`d83dfaf352`) documents as a fix.

2. **`telegram_bot/services/rag/vectorizers.py`** — Removed `UserBaseVectorizer` from the
   re-export shim. `src.services.vectorizers` no longer defines it (archived, deepvk/USER2-base).
   Pre-existing breakage; fixing it here is the right place.

---

## Acceptance Gate Results

| Gate | Result |
|---|---|
| `import telegram_bot.services.rag.rag_core, .cache_policy, .colbert_reranker, .vectorizers; import telegram_bot.bot` | ✅ exit 0 |
| No stale `services.<module>` refs (grep without `services.rag.`) | ✅ 0 matches |
| `uv run --frozen lint-imports` | ✅ 0 broken (4/4 contracts kept) |
| `make test-core` | ✅ 126/126 passed |
| `uv run pytest tests/characterization -q` | ✅ exit 0 (0 tests — dir has only `__init__.py`, no test files yet) |
| `test_rag_pipeline.py` | ✅ 83 passed, 1 pre-existing failure (`test_hybrid_retrieve_emits_topic_relax_trace_markers` — unchanged from baseline) |
| `test_rag_tool.py` | ✅ 0 new failures — all 19 errors are pre-existing (`BotContext kommo_client` signature mismatch) |

---

## Notes

- `test_hybrid_retrieve_emits_topic_relax_trace_markers` was failing on HEAD before this PR (verified with `git stash`). Not caused by this change.
- `test_rag_tool.py` 19 collection errors are pre-existing `BotContext.__init__()` signature mismatch. Not caused by this change.
- `telegram_bot.services.vectorizers.UserBaseVectorizer` import in `tests/unit/test_vectorizers.py` and `tests/integration/test_userbase_cache.py` was already broken pre-move (pre-existing). Tests updated to new path but still fail on missing class — not in `test-core` scope.
