# Open PR review checklist — 2026-06-11

Scope: quick review of the currently open cleanup/runtime PRs in `yastman/rag`.

## Merge order

1. `#2510` — handoff state boundary
2. `#2511` — production test import hygiene
3. `#2512` — verified dead-code cleanup
4. `#2513` — Mini App dead Kommo helper removal
5. `#2514` — break runtime generation adapter cycle
6. `#2515` — remove remaining runtime Telegram allowlist entries
7. `#2517` — wire API queries through assistant core

Important: `#2515` is stacked on `codex/2486-break-generation-cycle`, so merge or rebase `#2514` before `#2515`.

## PR notes

### #2510 — Fix #2490 handoff state boundary

Status: low risk.

What it does:
- Moves canonical handoff state implementation into `src.services.handoff_state`.
- Keeps `telegram_bot.services.handoff_state` as a compatibility re-export.

Before merge:
- Run `uv run pytest tests/unit/services/test_handoff_state.py -q`.
- Run `uv run ruff check src/services/handoff_state.py telegram_bot/services/handoff_state.py`.
- Optional: run handler integration tests in an environment with Telegram extras installed.

No required autofix found.

### #2511 — Fix #2491 production test import hygiene

Status: safe.

What it does:
- Adds a contract test preventing production modules under `src/` from importing `tests` or `tests.*`.

Before merge:
- Run `uv run pytest tests/contract/test_src_no_tests_imports_contract.py -q`.
- Run `uv run ruff check tests/contract/test_src_no_tests_imports_contract.py`.

No required autofix found.

### #2512 — Fix #2492 remove verified dead functions

Status: safe if focused tests pass.

What it removes:
- `trace_search_with_spans`
- `DoclingClient.convert_file`
- `GraphConfig.create_hybrid_embeddings`
- unused Sentry breadcrumb wrappers

Before merge:
- Run `uv run pytest tests/contract/test_dead_code_cleanup_contract.py -q`.
- Run the PR's focused `ruff check` command.
- Confirm no external scripts rely on these deleted helpers outside the repository.

No required autofix found.

### #2513 — Fix #2488 remove Mini App dead Kommo helper

Status: safe.

What it does:
- Removes deprecated `mini_app.phone.get_kommo_client`.
- Keeps Mini App phone flow on explicit DI through the API lifespan path.
- Adds a contract test to keep the helper removed.

Before merge:
- Run `python -m pytest tests/contract/test_2488_miniapp_dead_code_contract.py tests/unit/mini_app/test_phone_kommo_di.py -q`.
- Run the PR's focused `ruff check` command.

No required autofix found.

### #2514 — Break runtime generation adapter cycle

Status: safe, but merge before `#2515`.

What it does:
- Removes runtime assistant pipeline dependency on `telegram_bot.services.generate_response`.
- Uses `src.runtime.generation.generate_answer()` directly.
- Updates tests to assert `GenerationRequest` / `GenerationResult` behavior.

Before merge:
- Run `uv run pytest tests/contract/test_runtime_no_telegram_bot_coupling_contract.py tests/unit/core/test_assistant_entrypoint.py::TestRunAssistantRequestRuntime tests/unit/runtime/test_assistant_pipeline.py -q`.
- Run the PR's focused `ruff check` command.

No required autofix found.

### #2515 — Remove remaining runtime Telegram allowlist entries

Status: safe after `#2514` is merged or the branch is rebased.

What it does:
- Replaces dynamic Telegram string-coupled runtime imports in `src/runtime/pipeline/rag.py` with direct runtime/core imports.
- Changes legacy graph builder default so runtime no longer defaults to an adapter-owned graph factory.
- Shrinks `tests/data/known_runtime_telegram_bot_couplings.json` to `{}`.

Before merge:
- Merge/rebase after `#2514`.
- Run `uv run pytest tests/contract/test_runtime_no_telegram_bot_coupling_contract.py tests/unit/runtime/graph/test_builder.py -q`.
- Run the PR's focused `ruff check` command.

No required autofix found.

### #2517 — Wire API queries through assistant core

Status: needs updated branch check after autofix.

What it does:
- Replaces API lifespan graph construction with `CoreDependencies` construction.
- Routes `/query` through `src.core.run_assistant_request()`.
- Preserves the public `QueryResponse` shape.
- Keeps Langfuse span update and score writing when Langfuse is enabled.

Autofix already applied:
- Commit `ba962aae8fa7851342b974ee2f7a80d9217c765d` on `codex/2483-api-core-entrypoint`.
- Removed stale `_DummyGraph` helper and extra blank lines left after switching tests away from `app.state.graph`.

Before merge:
- Run `uv run ruff check src/api/main.py tests/unit/api/test_rag_api_runtime.py`.
- Run `uv run pytest tests/unit/api/test_rag_api_runtime.py -q`.
- Verify CI after the autofix commit.

## General recommendation

No hard code blockers were found in this focused pass. The main operational requirement is merge order: `#2514` before `#2515`, and retest `#2517` after the small test cleanup commit.
