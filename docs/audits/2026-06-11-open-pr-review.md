# Open PR review checklist — 2026-06-11

Scope: focused solo-dev review of the cleanup/runtime PR queue in `yastman/rag`.
This audit began when PRs `#2510` through `#2517` were open and was refreshed
when the remaining open queue was `#2519` and this docs PR (`#2520`).

## Current queue outcome

| PR | Outcome | Notes |
|---|---|---|
| `#2519` — Agent 3 boundary cleanup | Merged | Required GitHub checks were green. Focused validation passed (`72 passed`), and `make test-core` passed (`91 passed, 1 warning`) after syncing provider extras. |
| `#2520` — this audit doc | Ready to merge | Docs-only change refreshed to preserve the historical review while avoiding stale "currently open" wording. |

## Historical merge order reviewed

The original queue had stacked cleanup/runtime work. The intended merge order was:

1. `#2510` — handoff state boundary
2. `#2511` — production test import hygiene
3. `#2512` — verified dead-code cleanup
4. `#2513` — Mini App dead Kommo helper removal
5. `#2514` — break runtime generation adapter cycle
6. `#2515` — remove remaining runtime Telegram allowlist entries
7. `#2517` — wire API queries through assistant core

Important historical note: `#2515` was stacked on
`codex/2486-break-generation-cycle`, so `#2514` needed to merge or be rebased
before `#2515`.

## Historical PR notes

### #2510 — Fix #2490 handoff state boundary

Status: low risk.

What it does:
- Moves canonical handoff state implementation into `src.services.handoff_state`.
- Keeps `telegram_bot.services.handoff_state` as a compatibility re-export.

Validation recommended at review time:
- `uv run pytest tests/unit/services/test_handoff_state.py -q`
- `uv run ruff check src/services/handoff_state.py telegram_bot/services/handoff_state.py`
- Optional: handler integration tests in an environment with Telegram extras installed.

No required autofix found.

### #2511 — Fix #2491 production test import hygiene

Status: safe.

What it does:
- Adds a contract test preventing production modules under `src/` from importing `tests` or `tests.*`.

Validation recommended at review time:
- `uv run pytest tests/contract/test_src_no_tests_imports_contract.py -q`
- `uv run ruff check tests/contract/test_src_no_tests_imports_contract.py`

No required autofix found.

### #2512 — Fix #2492 remove verified dead functions

Status: safe if focused tests pass.

What it removes:
- `trace_search_with_spans`
- `DoclingClient.convert_file`
- `GraphConfig.create_hybrid_embeddings`
- unused Sentry breadcrumb wrappers

Validation recommended at review time:
- `uv run pytest tests/contract/test_dead_code_cleanup_contract.py -q`
- the PR's focused `ruff check` command
- confirmation that no external scripts rely on these deleted helpers outside the repository

No required autofix found.

### #2513 — Fix #2488 remove Mini App dead Kommo helper

Status: safe.

What it does:
- Removes deprecated `mini_app.phone.get_kommo_client`.
- Keeps Mini App phone flow on explicit DI through the API lifespan path.
- Adds a contract test to keep the helper removed.

Validation recommended at review time:
- `python -m pytest tests/contract/test_2488_miniapp_dead_code_contract.py tests/unit/mini_app/test_phone_kommo_di.py -q`
- the PR's focused `ruff check` command

No required autofix found.

### #2514 — Break runtime generation adapter cycle

Status: safe, but needed to merge before `#2515`.

What it does:
- Removes runtime assistant pipeline dependency on `telegram_bot.services.generate_response`.
- Uses `src.runtime.generation.generate_answer()` directly.
- Updates tests to assert `GenerationRequest` / `GenerationResult` behavior.

Validation recommended at review time:
- `uv run pytest tests/contract/test_runtime_no_telegram_bot_coupling_contract.py tests/unit/core/test_assistant_entrypoint.py::TestRunAssistantRequestRuntime tests/unit/runtime/test_assistant_pipeline.py -q`
- the PR's focused `ruff check` command

No required autofix found.

### #2515 — Remove remaining runtime Telegram allowlist entries

Status: safe after `#2514` was merged or the branch was rebased.

What it does:
- Replaces dynamic Telegram string-coupled runtime imports in `src/runtime/pipeline/rag.py` with direct runtime/core imports.
- Changes legacy graph builder default so runtime no longer defaults to an adapter-owned graph factory.
- Shrinks `tests/data/known_runtime_telegram_bot_couplings.json` to `{}`.

Validation recommended at review time:
- merge/rebase after `#2514`
- `uv run pytest tests/contract/test_runtime_no_telegram_bot_coupling_contract.py tests/unit/runtime/graph/test_builder.py -q`
- the PR's focused `ruff check` command

No required autofix found.

### #2517 — Wire API queries through assistant core

Status: safe after its small test cleanup autofix and follow-up validation.

What it does:
- Replaces API lifespan graph construction with `CoreDependencies` construction.
- Routes `/query` through `src.core.run_assistant_request()`.
- Preserves the public `QueryResponse` shape.
- Keeps Langfuse span update and score writing when Langfuse is enabled.

Autofix applied at review time:
- Commit `ba962aae8fa7851342b974ee2f7a80d9217c765d` on `codex/2483-api-core-entrypoint`.
- Removed stale `_DummyGraph` helper and extra blank lines left after switching tests away from `app.state.graph`.

Validation recommended at review time:
- `uv run ruff check src/api/main.py tests/unit/api/test_rag_api_runtime.py`
- `uv run pytest tests/unit/api/test_rag_api_runtime.py -q`
- verify CI after the autofix commit

## General recommendation

No hard code blockers were found in this focused pass. The original operational
requirement was merge order: `#2514` before `#2515`, then retest `#2517` after
its small test cleanup commit. The refreshed queue pass also found `#2519` clean
after focused validation and core validation.
