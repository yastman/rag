# Issue #728: SDK Realignment Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Realign the stale SDK migration backlog around what the repo already ships well (`aiogram`, `aiogram-dialog`, `qdrant-client`, `redisvl`) and execute only the remaining high-ROI SDK work.

**Architecture:** Treat this as three tracks: (1) close stale audit scope and lock in guardrails, (2) simplify runtime code where official SDKs already cover the behavior (`Langfuse` prompts, deprecated `LLMService` surface), (3) run bounded spikes where native SDKs are promising but not yet proven (`Docling`, optional Langfuse eval expansion).

**Tech Stack:** aiogram 3, aiogram-dialog, Langfuse Python SDK, qdrant-client, RedisVL, Docling, pytest

---

## Research Report

- `aiogram` already provides the transport-layer primitives we need: `Router`, dispatcher workflow data, typed `CallbackData`, and `dp.errors`. No extra Telegram abstraction layer is justified right now.
- `aiogram-dialog` already provides the menu/navigation primitives we need: `Start`, `SwitchTo`, `StartMode`, and `ShowMode`. Dialog work should stay there instead of expanding custom FSM code.
- `qdrant-client` should remain the primary retrieval SDK because the official Query API already matches our dense+sparse+fusion+rerank path.
- `redisvl` is already correctly scoped to cache/router duties. The right next step is threshold calibration, not a framework migration.
- `langfuse` is the best remaining SDK candidate for incremental value: prompt management should become more SDK-native, and evaluation APIs are worth a bounded spike.
- `docling` native Python API is real and viable, but only a feature-flagged contract-parity spike is justified while unified ingestion still depends on `docling-serve`.

## Execution Order

1. Cleanup stale audit scope and make the repo guidance canonical.
2. Remove prompt-manager complexity that duplicates the Langfuse SDK.
3. Retire deprecated `LLMService` surface from active runtime/documentation paths.
4. Run the Docling native spike behind a flag with parity tests.
5. Revisit broader SDK migrations only after the above lands and is measured.

## Task 1: Canonicalize The Audit And Roadmap

**Files:**
- Modify: `docs/SDK_MIGRATION_AUDIT_2026-03-13.md`
- Modify: `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md`
- Modify: `README.md`

**Step 1: Lock the refreshed verdict into repo docs**

- Add the validated keeper stack explicitly: `aiogram`, `aiogram-dialog`, `qdrant-client`, `redisvl`.
- Mark `Langfuse` and `Docling` as bounded follow-up work, not broad migrations.
- Link the audit from the docs index if the team wants it discoverable from `README.md`.

**Step 2: Verify docs remain coherent**

Run: `git diff -- docs/SDK_MIGRATION_AUDIT_2026-03-13.md docs/SDK_MIGRATION_ROADMAP_2026-03-13.md README.md`
Expected: wording is specific about what stays, what is a spike, and what is dropped.

**Step 3: Commit**

```bash
git add docs/SDK_MIGRATION_AUDIT_2026-03-13.md docs/SDK_MIGRATION_ROADMAP_2026-03-13.md README.md
git commit -m "docs: realign sdk migration audit around shipped stack"
```

## Task 2: Simplify Prompt Management To SDK-Native Langfuse

**Files:**
- Modify: `telegram_bot/integrations/prompt_manager.py`
- Modify: `tests/unit/integrations/test_prompt_manager.py`
- Reference: `telegram_bot/services/generate_response.py`

**Step 1: Write the failing tests**

- Add/adjust tests to assert `get_prompt()` relies on `client.get_prompt(..., cache_ttl_seconds=..., fallback=...)`.
- Add a regression test that missing prompts no longer depend on `client.api.prompts.get(...)`.
- Keep variable compilation and span-output behavior covered.

**Step 2: Run the focused test**

Run: `uv run pytest tests/unit/integrations/test_prompt_manager.py -q`
Expected: FAIL once tests require SDK-native behavior instead of the current probe/cache helpers.

**Step 3: Write the minimal implementation**

- Remove `_probe_prompt_available()`, `_missing_prompts_until`, and `_known_prompts_until`.
- Keep one fallback path for SDK exceptions and no-client mode.
- Preserve the current public API and span metadata so downstream callers do not change.

**Step 4: Run the focused test again**

Run: `uv run pytest tests/unit/integrations/test_prompt_manager.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/integrations/prompt_manager.py tests/unit/integrations/test_prompt_manager.py
git commit -m "refactor: use langfuse sdk prompt fallback directly"
```

## Task 3: Retire The Deprecated `LLMService` Surface

**Files:**
- Modify: `telegram_bot/services/__init__.py`
- Modify: `telegram_bot/services/llm.py`
- Modify: `telegram_bot/README.md`
- Modify: `tests/unit/test_llm_service.py`
- Modify: `tests/unit/services/test_llm.py`
- Reference: `telegram_bot/services/generate_response.py`
- Reference: `telegram_bot/pipelines/client.py`

**Step 1: Write the failing tests**

- Add one test that the package-level public surface no longer encourages `LLMService` usage.
- Keep one compatibility test if the module stays as a shim, but require deprecation to be explicit and non-runtime-critical.
- Add a grep-based assertion or targeted import test that production code paths use `generate_response()` instead.

**Step 2: Run the focused tests**

Run: `uv run pytest tests/unit/test_llm_service.py tests/unit/services/test_llm.py tests/unit/services/test_generate_response.py -q`
Expected: FAIL once the public-surface expectations are tightened.

**Step 3: Write the minimal implementation**

- Remove `LLMService` from `telegram_bot.services.__all__` and lazy exports.
- Update `telegram_bot/README.md` to point to `generate_response()` as the canonical path.
- Keep `telegram_bot/services/llm.py` only as an explicit compatibility shim or remove it if no supported imports remain.

**Step 4: Re-run the focused tests**

Run: `uv run pytest tests/unit/test_llm_service.py tests/unit/services/test_llm.py tests/unit/services/test_generate_response.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/__init__.py telegram_bot/services/llm.py telegram_bot/README.md tests/unit/test_llm_service.py tests/unit/services/test_llm.py tests/unit/services/test_generate_response.py
git commit -m "refactor: retire deprecated llmservice surface"
```

## Task 4: Run A Feature-Flagged Docling Native Spike

**Files:**
- Create: `src/ingestion/docling_native.py`
- Modify: `src/ingestion/unified/config.py`
- Modify: `src/ingestion/unified/targets/qdrant_hybrid_target.py`
- Modify: `tests/unit/ingestion/test_docling_client.py`
- Create: `tests/unit/ingestion/test_docling_native.py`
- Reference: `src/ingestion/docling_client.py`

**Step 1: Write the failing tests**

- Add a contract test that native chunks expose the same normalized fields used today by the unified ingestion target.
- Add a config test for selecting `docling_native` vs `docling_http`.
- Keep the current `DoclingClient` tests unchanged for the HTTP path.

**Step 2: Run the focused tests**

Run: `uv run pytest tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py -q`
Expected: FAIL because the native adapter and selector do not exist yet.

**Step 3: Write the minimal implementation**

- Introduce a narrow adapter around Docling `DocumentConverter`.
- Gate it behind explicit config so rollback is immediate.
- Preserve deterministic metadata mapping and chunk identity.
- Do not remove `docling-serve` until native parity is demonstrated on representative documents.

**Step 4: Re-run the focused tests**

Run: `uv run pytest tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py -q`
Expected: PASS

**Step 5: Run one integration confirmation if fixtures are available**

Run: `uv run pytest tests/integration/test_gdrive_ingestion.py -q`
Expected: PASS when local services/fixtures are available; otherwise document the blocker.

**Step 6: Commit**

```bash
git add src/ingestion/docling_native.py src/ingestion/unified/config.py src/ingestion/unified/targets/qdrant_hybrid_target.py tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py
git commit -m "feat(ingestion): add feature-flagged native docling path"
```

## Guardrails

- No big-bang replacement of `aiogram`, `aiogram-dialog`, `qdrant-client`, or `redisvl`.
- No new Telegram orchestration layer unless a concrete gap is proven against native aiogram features.
- No replacement of direct `qdrant-client` in the main retrieval path unless advanced feature parity is demonstrated.
- Every spike must ship with a rollback path, focused tests, and explicit measurement criteria.
