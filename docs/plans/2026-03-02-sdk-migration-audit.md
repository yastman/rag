# SDK Migration Audit

> Reviewed and refreshed on **2026-03-13** against the current repository state, installed dependencies, and official SDK documentation.

**Original scope:** audit custom code that may be replaced by SDK/native framework solutions.

**Current verdict:** the audit summary in issue `#728` is directionally useful, but it is no longer a reliable execution plan as-is. Several "migration" items are already implemented, one recommended RedisVL SDK feature could not be verified, and the historical "big bang" rewrite direction is too risky for the current codebase.

---

## What Is Already Done

These items should be removed from the active migration backlog:

- `telegram_bot/services/rag_core.py` already exists and has extracted shared RAG logic for cache/retrieve/rerank/rewrite.
- `aiogram` service injection via dispatcher workflow data is already used in `PropertyBot`.
- Typed `CallbackData` factories already exist in `telegram_bot/callback_data.py`.
- `handle_favorite_callback()` is already downgraded to a compatibility dispatcher while production routing uses per-action handlers.
- `RedisVL SemanticRouter` is already integrated as an optional classifier path behind `CLASSIFIER_MODE=semantic`.
- `RedisVL EmbeddingsCache` is already integrated in the cache layer.
- `dp.errors` registration is already present; the legacy middleware wrapper remains only for backward compatibility.

## Keep As Active Work

These items remain valid and worth planning:

- Continue shrinking `PropertyBot` into router/domain modules. The file is still large enough to justify decomposition.
- Finish removing legacy `LLMService` call sites and treat `generate_response.py` as the single supported path.
- Evaluate `Langfuse` experiment APIs for dataset-backed evaluation instead of growing more custom experiment scaffolding.
- Keep direct Qdrant SDK usage for the main retrieval path where nested `prefetch`, fusion, and ColBERT reranking are required.

## Re-Scope Before Doing

These items are plausible, but only as narrow spikes with explicit success criteria:

### `langchain-qdrant` `SelfQueryRetriever`

Use only for a contained apartment-filter prototype. Do **not** treat it as a replacement for the current main retrieval stack, because the repository intentionally uses direct Qdrant APIs for features that exceed the thin vector-store wrapper.

### Docling Python API

Do not frame this as a blanket "HTTP client -> Python API" migration. The repository already uses direct `DocumentConverter` in `src/ingestion/document_parser.py`, while unified ingestion still uses `src/ingestion/docling_client.py`. Any further migration must account for packaging, runtime isolation, and whether ingestion runs with the `docling` extra installed.

### Guardrails / PII SDKs

`NeMo Guardrails` and `Presidio` are still optional exploratory candidates. They are not installed in the current environment and should not be elevated above the existing regex/content-filter path without a measured eval plan.

## Drop Or Replace

These points should not stay in the plan unchanged:

### RedisVL `CacheThresholdOptimizer`

This recommendation is not verified in the current environment and was not confirmed in the official RedisVL docs review. Replace it with an internal threshold-calibration task based on existing trace/eval data.

### Big-Bang Stack Rewrite

Do not replace LangChain/LangGraph with `pydantic-ai` / `pydantic-graph` in one migration branch. That is a separate architecture proposal, not a safe follow-up to issue `#728`. The current repository is already on `langchain>=1.2` and uses SDK-native agent features; a wholesale rewrite would mix platform migration with cleanup work and destroy incremental validation.

---

## Reviewed Roadmap

### Phase 1: Remove Stale Audit Items

- Update issue `#728` summary so already-shipped items are marked done.
- Link this file instead of the previously missing local artifact.
- Split "implemented", "active", and "exploratory" recommendations.

### Phase 2: Finish High-ROI SDK Adoption

- Remove remaining `LLMService` call sites and compatibility exports.
- Continue `PropertyBot` decomposition into routers/handlers without changing the transport stack.
- Keep using aiogram native patterns (`CallbackData`, `dp.errors`, workflow data / DI) instead of introducing a second DI system.

### Phase 3: Evaluate Bounded SDK Spikes

- `Langfuse` experiment runner for offline/managed evals.
- `langchain-qdrant` only for apartment metadata filtering prototype.
- Direct Docling Python API only for the unified ingestion path, if packaging/runtime constraints are acceptable.

### Phase 4: Optional Research Track

- `Presidio` for PII detection if the product needs higher recall than regex.
- `NeMo Guardrails` only if there is a concrete policy layer requirement that current prompt + regex guards cannot satisfy.

---

## Review Notes

- Issue `#728` references this path, but the file was missing in the working tree as of **2026-03-13**.
- A historical successor design in git history (`docs/plans/2026-03-03-sdk-migration-design.md`) proposed a big-bang move to `dishka` + `pydantic-ai`; that direction is intentionally **not** adopted here as the default recommendation.
- This document is a corrected local source of truth for the audit until the GitHub issue text is updated.
