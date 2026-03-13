# SDK Migration Audit (Refreshed)

**As of:** 2026-03-13
**Source issue:** #728

## Executive Verdict

The original SDK migration audit is partially stale. Several "to-do migration" items are already implemented in the current codebase. The remaining work should be narrowed to high-ROI incremental SDK adoption, not a big-bang replatforming.

## Validated Ready-Made SDK Paths

- `aiogram` already covers the main transport-layer primitives we need: modular `Router` composition, dispatcher workflow-data injection, typed `CallbackData`, and centralized `dp.errors` handlers. Continue refactors inside aiogram instead of adding another routing/DI layer.
- `aiogram-dialog` already covers dialog stack transitions via `Start`, `SwitchTo`, `StartMode`, and `ShowMode`. Keep menu/navigation flows on `aiogram-dialog` rather than expanding custom FSM machinery.
- `qdrant-client` remains the correct primary retrieval SDK. Official Query API patterns (`query_points`, `prefetch`, fusion, filters, groups) match the repo's dense+sparse+ColBERT requirements better than higher-level wrappers.
- `redisvl` already provides the right ready-made primitives for this repo's classifier/cache layer: `SemanticRouter`, `SemanticCache`, and `EmbeddingsCache`. Prefer calibration of current thresholds over speculative optimizer migrations.
- `langfuse` should stay scoped to prompt management and a bounded evaluation/experiment follow-up. This is an incremental SDK improvement area, not a broad migration track.
- `docling` official Python `DocumentConverter` is a valid migration candidate, but only as a feature-flagged spike. We still need proof that native runtime/deployment behavior matches the current `docling-serve` path in unified ingestion.

## Already Implemented (Remove from Active Backlog)

- Shared RAG core extraction exists in `telegram_bot/services/rag_core.py`.
- aiogram dispatcher workflow DI (`dp[...]` / workflow data) is in use.
- Typed aiogram `CallbackData` factories are in place.
- Favorite callback monolith is already split into per-action handlers with compatibility shim.
- RedisVL `SemanticRouter` path exists behind classifier mode.
- RedisVL `EmbeddingsCache` is integrated in cache layer.
- aiogram `dp.errors` error registration is implemented.

## Keep Active

- Continue reducing `PropertyBot` surface area into routers/modules.
- Retire legacy `LLMService` usage and keep `generate_response` as canonical runtime path.
- Remove extra client-side prompt probing around Langfuse where the official SDK already exposes `get_prompt(...)` fallback/cache behavior.
- Evaluate Langfuse experiment APIs for eval workflow consolidation.
- Keep direct Qdrant SDK for main retrieval path where advanced prefetch/fusion/ColBERT is required.

## Re-Scope as Spikes (Not Broad Migrations)

- `langchain-qdrant` SelfQueryRetriever: apartment-filter prototype only.
- Docling migration: current state is mixed (direct Python API in one path, HTTP client in unified path); evaluate with packaging/runtime constraints.
- Langfuse experiment/dataset workflow: bounded spike around current eval scripts before any broad observability refactor.
- NeMo Guardrails / Presidio: optional research track with explicit quality targets.

## Drop/Replace Recommendations

- Replace unverified RedisVL `CacheThresholdOptimizer` recommendation with internal threshold calibration using existing traces/evals.
- Do not treat `dishka + pydantic-ai/pydantic-graph` big-bang rewrite as default continuation of issue #728.
- Do not introduce another Telegram abstraction layer while `aiogram` + `aiogram-dialog` already cover routers, dialog state, middleware data, and callback typing.

## Validation Basis

- Repository implementation checks
- Installed package introspection
- Official SDK docs via Context7 / vendor docs for `aiogram`, `qdrant-client`, `langfuse`, and `docling`
- Official docs search via Exa for `aiogram-dialog` and `redisvl`

## Source Pointers

- Aiogram DI / workflow data / middleware data: `https://docs.aiogram.dev/en/latest/dispatcher/dependency_injection.html`
- Aiogram typed callbacks: `https://docs.aiogram.dev/en/latest/dispatcher/filters/callback_data.html`
- aiogram-dialog transitions and show modes: `https://aiogram-dialog.readthedocs.io/en/stable/`
- Qdrant Query API / hybrid queries: `https://qdrant.tech/documentation/concepts/hybrid-queries/`
- Qdrant API reference for `query_points`: `https://api.qdrant.tech/api-reference/search/query-points`
- Langfuse Python prompts/evaluations: `https://langfuse.com/docs/sdk/python/overview`
- RedisVL Semantic Router / EmbeddingsCache: `https://docs.redisvl.com/en/latest/`
- Docling Python quickstart / `DocumentConverter`: `https://docling-project.github.io/docling/getting_started/quickstart/`
