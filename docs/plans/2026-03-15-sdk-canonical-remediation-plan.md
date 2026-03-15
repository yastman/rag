# SDK Canonical Remediation Plan

Date: 2026-03-15
Branch: `review/project-dev`
Status: canonical execution plan derived from repository review plus historical local SDK plan artifacts

## Precedence

This file is the canonical execution plan for SDK-first cleanup and bounded SDK adoption on this branch.

It consolidates and supersedes the execution direction spread across:

- `docs/plans/2026-03-15-sdk-review-remediation-plan.md`
- local historical artifacts found outside this worktree:
  - `docs/plans/2026-03-02-sdk-migration-audit.md`
  - `docs/plans/2026-03-13-issue-728-sdk-realignment-plan.md`
  - `docs/plans/2026-03-13-sdk-first-remediation-plan.md`
  - `docs/SDK_MIGRATION_AUDIT_2026-03-13.md`
  - `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md`

## Executive Verdict

The correct direction is not a big-bang replacement of the current stack.

The repo should:

1. Keep the SDKs that already match the product well.
2. Remove custom layers that duplicate vendor SDK behavior without adding product value.
3. Collapse duplicate in-repo adapters where one canonical internal abstraction is enough.
4. Treat promising SDK migrations as bounded spikes behind flags or compatibility shims.

## Keeper Stack

These are the stacks the plan assumes will remain primary:

- `aiogram` for Telegram transport, routing, middleware data, and typed callback handling
- `aiogram-dialog` for menu/dialog state transitions
- direct `qdrant-client` for main retrieval paths with hybrid search, fusion, and rerank features
- `redisvl` for cache/router-classifier responsibilities
- `Langfuse` for tracing, prompts, and possible bounded eval expansion
- current first-party/in-repo Kommo integration rather than third-party Kommo SDKs

## Non-Goals

- No replacement of `aiogram`, `aiogram-dialog`, `qdrant-client`, or `redisvl`.
- No big-bang rewrite to another orchestration or agent framework.
- No migration to third-party Kommo packages without a separate approval decision.
- No forced replacement of direct Qdrant APIs with higher-level wrappers unless advanced feature parity is proven.
- No full ingestion architecture rewrite as part of the Docling work.

## Guardrails

- Preserve Telegram transport/domain boundaries from `telegram_bot/AGENTS.override.md`.
- Preserve ingestion determinism/resumability and file identity semantics from `src/ingestion/unified/AGENTS.override.md`.
- Preserve LangGraph state and node contract shapes while refactoring bot/runtime code.
- Preserve trace/score instrumentation unless an explicit replacement is defined and validated.
- Before introducing or keeping custom integration code, check Context7 for official/native SDK patterns for the target library.
- Every bounded spike must have:
  - explicit acceptance criteria
  - rollback path
  - targeted tests
  - documented measured result

## Required SDK Discovery Workflow

For each workstream, use this decision order:

1. Check Context7 for official/native SDK support.
2. Prefer first-party SDK or native framework capability when it covers the requirement.
3. Keep custom code only if:
   - the SDK does not support the needed behavior,
   - the SDK path would regress product/runtime constraints,
   - or the custom adapter is the minimal glue layer between subsystems.

Context7 should be queried first for these libraries/frameworks when relevant:

- `Langfuse`
- `qdrant-client`
- `aiogram`
- `aiogram-dialog`
- `RedisVL`
- `Docling`
- `LiveKit Agents`

Expected output from each Context7 check:

- what the official SDK already supports
- what custom code can be removed
- what custom code must remain
- any SDK constraints or version-sensitive caveats

## Current Audit Findings (2026-03-15)

These findings came from repository audit against the current worktree and should be treated as active backlog input.

### High

- Broken documentation references in tracked files:
  - `compose.yml` references missing `docs/plans/2026-03-05-docker-compose-unification-design.md`
  - `telegram_bot/AGENTS.override.md` and `src/ingestion/unified/AGENTS.override.md` reference missing `docs/agent-rules/*`
- `LLMService` remains widely embedded in tests/docs even though runtime direction has moved to `generate_response()`
- Prompt management still contains manual Langfuse prompt probing via `_probe_prompt_available()` and `client.api.prompts.get(...)`
- Kommo OAuth/token state is duplicated across `telegram_bot/services/kommo_tokens.py` and `telegram_bot/services/kommo_token_store.py`
- Voice agent still uses inline shared `httpx.AsyncClient` plumbing inside `src/voice/agent.py` instead of a typed internal client boundary

### Medium

- Qdrant client/config/query policy is duplicated across bot, retrieval, ingestion, and evaluation code
- README/runtime support drift:
  - README advertises Python 3.12+
  - `pyproject.toml` requires `>=3.11`
  - Ruff target is `py311`
- README project structure still points to top-level `evaluation/`, while the repo uses `src/evaluation/`
- Multiple deprecated/legacy compatibility surfaces remain active in runtime/docs/tests, increasing cleanup cost and masking dead code

### Low

- Several evaluation modules still carry TODO placeholders and legacy references that should be either promoted into explicit backlog or removed
- Deprecated ingestion/chunking helpers remain documented/tested beyond their current product importance

## Workstreams

### Phase 0: Recover Source Of Truth

Goal: restore one tracked documentation baseline before code cleanup continues.

Actions:

- Restore the historically relevant SDK audit/roadmap docs into git, or archive them explicitly if they are intentionally obsolete.
- Keep this file as the canonical execution plan.
- Fix stale doc references in code/comments, especially broken `docs/plans/...` links.
- Align README/runtime version statements where they currently disagree.

Acceptance criteria:

- At least one historical SDK migration/audit document beyond this file is restored as tracked documentation.
- Broken plan references in tracked files are either repaired or removed.
- Team can point to one canonical plan and one canonical audit snapshot.

Suggested checks:

- `rg -n "docs/plans/" README.md compose.yml telegram_bot src docs`

### Phase 1: Harden Docker Secret Posture

Goal: separate development convenience from base security posture.

Actions:

- Remove predictable secret fallbacks from `compose.yml`.
- Keep local/dev-only defaults in `compose.dev.yml`.
- Document which services may continue to use environment variables for secrets and which should move to `secrets:` or `*_FILE` patterns.
- Re-check service exceptions to `x-security-defaults`.

Primary files:

- `compose.yml`
- `compose.dev.yml`
- `compose.vps.yml`
- `docs/LOCAL-DEVELOPMENT.md`

Acceptance criteria:

- Base Compose fails fast on missing sensitive credentials.
- Dev overrides still provide a low-friction local startup path.
- Secret handling target model is documented.

### Phase 2: Simplify Langfuse Prompt Management

Goal: stop duplicating SDK prompt lookup behavior in local code.

Actions:

- Check Context7 Langfuse docs for the current prompt-management API before changing code.
- Refactor `telegram_bot/integrations/prompt_manager.py` toward SDK-native `client.get_prompt(...)` behavior.
- Remove or shrink `_probe_prompt_available()`, `_missing_prompts_until`, and `_known_prompts_until` if they are no longer justified.
- Keep fallback behavior only where the SDK/client is absent or still raises recoverable exceptions.
- Preserve public API and prompt variable compilation behavior for callers.

Primary files:

- `telegram_bot/integrations/prompt_manager.py`
- `tests/unit/integrations/test_prompt_manager.py`

Acceptance criteria:

- Happy path does not require manual `client.api.prompts.get(...)` probing.
- Fallback behavior remains deterministic.
- Existing callers do not need to change.

Suggested checks:

- `uv run pytest tests/unit/integrations/test_prompt_manager.py -q`
- `rg -n "client\\.api\\.prompts\\.get|_probe_prompt_available|Prompt availability probe" telegram_bot tests`

### Phase 3: Retire Deprecated `LLMService` From Active Runtime Surface

Goal: make `generate_response()` the canonical runtime path.

Actions:

- Check Context7 for the current supported OpenAI-compatible and Langfuse instrumentation patterns used by the repo.
- Audit all imports and references to `LLMService`.
- Separate runtime-critical dependencies from compatibility tests and legacy documentation.
- Remove `LLMService` from package-level “recommended” surface in `telegram_bot/services/__init__.py`.
- Update bot-facing docs to point to `generate_response()` as the supported path.
- Keep `telegram_bot/services/llm.py` only as a bounded compatibility shim until test migration is complete, or remove it once no supported imports remain.

Primary files:

- `telegram_bot/services/__init__.py`
- `telegram_bot/services/llm.py`
- `telegram_bot/services/generate_response.py`
- `telegram_bot/README.md`
- tests under `tests/unit/` and `tests/integration/` that still target `LLMService`

Acceptance criteria:

- No production/runtime path depends on `LLMService`.
- Any remaining references are explicit compatibility debt with an owner.
- Canonical documentation no longer presents `LLMService` as the primary API.

Suggested checks:

- `rg -n "LLMService" telegram_bot src tests`
- `uv run pytest tests/unit/services/test_generate_response.py -q`

### Phase 4: Consolidate Kommo Token Store Duplication

Goal: stop maintaining two competing token-store implementations.

Current duplication:

- `telegram_bot/services/kommo_tokens.py`
- `telegram_bot/services/kommo_token_store.py`

Actions:

- Choose one canonical token-store implementation and one Redis keying model.
- Convert the other module into a compatibility shim or delete it after import cleanup.
- Ensure `telegram_bot/services/kommo_client.py` and bot startup use the same abstraction.
- Preserve refresh-token flow and env-seeding behavior.

Primary files:

- `telegram_bot/services/kommo_client.py`
- `telegram_bot/services/kommo_tokens.py`
- `telegram_bot/services/kommo_token_store.py`
- `telegram_bot/bot.py`
- related unit tests

Acceptance criteria:

- One canonical token-store implementation is used in runtime code.
- Redis key format is consistent.
- OAuth refresh behavior remains intact.

Suggested checks:

- `uv run pytest tests/unit/services/test_kommo_tokens.py tests/unit/services/test_kommo_token_store.py tests/unit/services/test_kommo_client.py -q`

### Phase 5: Add A Typed Voice RAG API Client

Goal: replace inline voice-to-RAG HTTP calls with one typed internal boundary.

Actions:

- Check Context7 for current LiveKit Agents patterns around external backend/tool calls before refactoring the client boundary.
- Create a dedicated client module for voice-to-RAG API interaction.
- Move request schema, timeout handling, and error mapping out of `src/voice/agent.py`.
- Keep the user-facing fallback behavior unchanged.

Primary files:

- `src/voice/agent.py`
- `src/voice/rag_api_client.py` or equivalent shared internal client module
- `tests/unit/voice/test_voice_agent.py`
- new tests for the typed client

Acceptance criteria:

- `search_knowledge_base()` no longer owns ad-hoc inline HTTP request assembly.
- Request payload shape remains explicit and tested.
- Error handling is centralized.

Suggested checks:

- `uv run pytest tests/unit/voice/test_voice_agent.py -q`

### Phase 6: Run A Feature-Flagged Docling Native Spike

Goal: evaluate native Docling usage in unified ingestion without forcing a full migration.

Actions:

- Check Context7 for current Docling native conversion/chunking patterns before implementing the adapter.
- Add a narrow native adapter using `DocumentConverter` and the current normalized chunk contract.
- Gate native vs HTTP behavior behind explicit config.
- Keep current HTTP behavior as rollback path until parity is demonstrated.
- Measure contract parity, runtime behavior, and packaging/deployment implications.

Primary files:

- `src/ingestion/docling_client.py`
- `src/ingestion/docling_native.py`
- `src/ingestion/unified/config.py`
- `src/ingestion/unified/targets/qdrant_hybrid_target.py`
- `tests/unit/ingestion/test_docling_client.py`
- `tests/unit/ingestion/test_docling_native.py`

Acceptance criteria:

- Native path is optional and reversible.
- Normalized chunk contract remains stable.
- Ingestion identity and resumability semantics are preserved.
- Measured result is documented: keep native path, keep HTTP path, or keep both.

Suggested checks:

- `uv run pytest tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py -q`
- `uv run pytest tests/integration/test_gdrive_ingestion.py -q`

### Phase 7: Consolidate Qdrant Configuration Policy

Goal: reduce duplicated client/config/query policy logic without weakening runtime-specific needs.

Actions:

- Check Context7 Qdrant client docs for current sync/async initialization and query API patterns before extracting shared abstractions.
- Introduce one shared source of truth for Qdrant connection and collection policy.
- Centralize collection naming and quantization policy.
- Extract reusable query/search parameter builders where overlap is real.
- Preserve thin runtime-specific adapters when async vs sync or ingestion vs retrieval concerns differ.

Primary files:

- `telegram_bot/services/qdrant.py`
- `src/retrieval/search_engines.py`
- `src/ingestion/unified/qdrant_writer.py`
- `src/ingestion/service.py`
- `src/ingestion/indexer.py`
- `src/evaluation/search_engines.py`

Acceptance criteria:

- Qdrant connection/config policy has one shared source of truth.
- Collection and quantization policy do not drift across runtimes.
- Search feature changes no longer require copy-paste edits in multiple modules.

Suggested checks:

- `rg -n "QdrantClient\\(|AsyncQdrantClient\\(" telegram_bot src`

### Phase 8: Reduce Langfuse Runtime Custom Surface

Goal: keep only project-specific observability behavior that the SDK does not already cover.

Actions:

- Re-check Context7 Langfuse SDK docs before removing or retaining custom observability helpers.
- Split or simplify `telegram_bot/observability.py` into a smaller bootstrap-oriented module.
- Retain PII redaction and explicitly justified custom behavior.
- Move optional startup synchronization logic behind a clear boundary if it remains necessary.
- Preserve current trace/score behavior until equivalent replacement is verified.

Primary files:

- `telegram_bot/observability.py`
- `telegram_bot/middlewares/langfuse_middleware.py`
- `telegram_bot/scoring.py`
- related observability tests

Acceptance criteria:

- Module responsibility is narrower and clearer.
- SDK upgrade risk is reduced.
- Trace/score contracts remain validated.

## Explicitly Dropped Or Deferred Ideas

- `langchain-qdrant` as a replacement for the main retrieval path
- big-bang migration to another agent/orchestration framework
- speculative RedisVL optimizer work not verified against current docs/runtime
- third-party Kommo SDK adoption
- broad Guardrails/PII SDK adoption without a separate eval-driven proposal

## Validation Gates

Required before closing any implementation batch derived from this plan:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`

Additional targeted gates when relevant:

- Graph/bot flow changes:
  - `uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q`
- Ingestion unified changes:
  - `make ingest-unified-status`
  - `python -m src.ingestion.unified.cli preflight`
- Docling spike:
  - `uv run pytest tests/unit/ingestion/test_docling_client.py tests/unit/ingestion/test_docling_native.py -n auto --dist=worksteal -q`
- Voice client work:
  - `uv run pytest tests/unit/voice/test_voice_agent.py -n auto --dist=worksteal -q`

## Recommended Order

1. Phase 0: recover tracked documentation and fix source-of-truth drift.
2. Phase 1: Docker secret hardening.
3. Phase 2: Langfuse prompt-manager simplification.
4. Phase 3: `LLMService` retirement from active runtime surface.
5. Phase 4: Kommo token-store consolidation.
6. Phase 5: typed voice RAG client.
7. Phase 6: Docling native spike.
8. Phase 7: Qdrant configuration consolidation.
9. Phase 8: Langfuse runtime surface reduction.

## Notes

- Historical local plans contained useful task ideas, but some assumptions were stale.
- This plan intentionally keeps the valid detailed tasks and drops the stale migration framing.
- If a phase proves too large, split it into a dedicated sub-plan rather than broadening scope inside implementation.
