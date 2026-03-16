# SDK Canonical Remediation Report

Date: 2026-03-15
Branch: `feat/sdk-canonical-remediation`
Plan: `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md`

## Scope

This report summarizes execution of phases 0-8 from the canonical SDK remediation plan, including autofixes, SDK-aligned refactors, and validation results.

## Context7 SDK Inputs Used

- Langfuse (`/langfuse/langfuse-docs`): use `get_prompt(...)` + `compile(...)`, fallback-safe prompt retrieval, and `update_current_span(...)`.
- Qdrant (`/qdrant/qdrant-client`): standard sync/async client initialization and query API usage.
- LiveKit Agents (`/livekit/agents`): `@function_tool` boundaries with explicit tool-layer error handling and testability.
- Docling (`/docling-project/docling`): native `DocumentConverter` adapter pattern with format/pipeline options.

## Implemented Changes By Phase

### Phase 0: Source Of Truth Recovery

- Restored and tracked historical SDK docs + canonical plan in `docs/plans/`.
- Fixed stale broken references in compose/docs/agents override files.
- Aligned Python version and structure drift in README/docs.
- Updated `.gitignore` to allow tracking canonical plan/audit docs.

### Phase 1: Compose Secret Posture

- Removed predictable secret defaults from `compose.yml` baseline.
- Moved dev-only secret defaults into `compose.dev.yml`.
- Updated compose secret policy documentation in `docs/LOCAL-DEVELOPMENT.md`.
- Updated unit tests to enforce secure baseline + dev override model.

### Phase 2: Langfuse Prompt Manager Simplification

- Removed manual prompt probe path (`client.api.prompts.get(...)`).
- Kept SDK-native prompt flow (`client.get_prompt(...)`) with deterministic fallback.
- Preserved prompt version span output updates.
- Updated prompt manager tests accordingly.

### Phase 3: LLMService Runtime Surface Retirement

- Removed `LLMService` from `telegram_bot.services.__all__` recommended surface.
- Kept compatibility lazy import path (`services.LLMService`) for legacy consumers.
- Updated bot-facing README to present `generate_response()` as canonical runtime path.
- Added a public API unit test for this contract.

### Phase 4: Kommo Token Store Consolidation

- Made `telegram_bot/services/kommo_tokens.py` canonical implementation.
- Replaced `kommo_token_store.py` with compatibility shim inheriting canonical store.
- Kept serialized refresh behavior via shim-level lock.
- Updated `kommo_client` to depend on token-store protocol, not duplicate implementation type.
- Updated unit tests to target canonical HTTP path.

### Phase 5: Typed Voice RAG API Client

- Added `src/voice/rag_api_client.py` with:
  - `RagQueryRequest` typed payload
  - `RagApiClient` HTTP boundary
  - centralized error mapping (`RagApiClientError`)
- Refactored `src/voice/agent.py` tool call path to use typed client.
- Kept compatibility wrappers for shared HTTP lifecycle behavior.
- Added unit tests for typed client behavior.

### Phase 6: Feature-Flagged Docling Native Spike

- Added optional native adapter `src/ingestion/docling_native.py` using `DocumentConverter`.
- Added `docling_backend` + `docling_native_enabled` config flags.
- Updated unified ingestion target connector to choose HTTP vs native path by flag.
- Added unit tests for native adapter chunking/error path.

### Phase 7: Qdrant Configuration Policy Consolidation

- Added shared helper `src/config/qdrant_policy.py` for canonical collection naming.
- Wired helper into:
  - `src/config/settings.py`
  - `telegram_bot/config.py`
  - `telegram_bot/services/qdrant.py`
- Added unit tests for collection policy helper.

### Phase 8: Langfuse Runtime Surface Reduction

- Extracted bootstrap-only infrastructure helpers into `telegram_bot/observability_bootstrap.py`.
- Preserved backward-compatible private wrappers in `telegram_bot/observability.py` (`_is_endpoint_reachable`, `_disable_otel_exporter`) for existing tests and call sites.
- Kept existing tracing/score contracts unchanged.

## Additional Autofixes

- Fixed test regressions in bot stop lifecycle, graph doc limit assertion, apartment extractor invalid-city fixture, and env-sensitive config tests.
- Kept full unit suite green after SDK refactors.

## Validation Results

Passed:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- `uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q`
- `make ingest-unified-status`

Known environment-limited check:

- `uv run python -m src.ingestion.unified.cli preflight`
  Result: `3/5 checks passed — NOT READY` because Docling service (`http://localhost:5001`) was unreachable in local runtime at verification time.

## Outcome

The branch now follows SDK-first canonical direction with:

- reduced custom surface,
- compatibility-safe shims where removal would be risky,
- typed boundaries for voice external calls,
- feature-flagged native Docling path,
- shared Qdrant policy logic,
- and green core validation gates.
