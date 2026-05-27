# Test audit (#1515) — burn-down closeout

**Date:** 2026-05-27
**Issue:** [#1515 — Аудит тестов: баги, дубликаты, пробелы и план оптимизации](https://github.com/yastman/rag/issues/1515)
**Status:** Closed. All bug, duplicate and architecture items addressed; only cosmetic
S5 follow-up remains and is tracked below.

This note is the final burn-down record for the audit captured in #1515. It is
not a new audit — it is the reconciliation between the audit body filed on
2026-05-21 and the state of `dev` (commit `4ab8379`) on 2026-05-27.

The verification was driven from the original audit's tag IDs (B1–B6, D1–D9,
A1–A6, S1–S7). For every item below, the entry shows what the audit asked for
and the concrete file or fixture that resolved it.

## Critical bugs (B-series) — closed

| Tag | Audit ask | Resolution |
|-----|-----------|------------|
| **B1** | `tests/smoke/conftest.py:62` uses deprecated `asyncio.get_event_loop()` | `tests/smoke/conftest.py` now wraps the Redis ping in `asyncio.run(check_redis())` and the URL/credential fixtures live in `tests/fixtures/config.py` |
| **B2** | `tests/e2e/test_rag_pipeline.py` and `test_core_flows_live.py` were mock-only | Both files removed. The remaining `tests/e2e/*` suites require live services and skip gracefully when the stack is unavailable |
| **B3** | `src/_compat.py` had zero tests | `tests/unit/test_compat.py` covers the `load_deprecated_package_export` helper |
| **B4** | `src/evaluation/config_snapshot.py` had zero tests | `tests/unit/evaluation/test_config_snapshot.py` (95 lines) covers snapshot creation and serialization |
| **B5** | `tests/conftest.py::pytest_collection_modifyitems` missed `contract`/`baseline` tiers | Both directories are present in the `path_to_marker` map and a contract test (`test_no_duplicate_collection_hooks_contract.py`) pins the canonical hook |
| **B6** | `telegram_bot/.venv/` polluted coverage | `[tool.coverage.run].omit` in `pyproject.toml` excludes `telegram_bot/.venv/*` and `telegram_bot/.venv/**/*` |

## Duplicates (D-series) — closed

| Tag | Audit ask | Resolution |
|-----|-----------|------------|
| **D1** | `sample_context_chunks` defined in two places | Single source: `tests/fixtures/data.py` (registered via `pytest_plugins = ["tests.fixtures.config"]` chain) |
| **D2** | `pytest_collection_modifyitems` copied into 6 sub-conftests | Only `tests/conftest.py` defines the auto-marker hook; contract test `test_no_duplicate_collection_hooks_contract.py` enforces the rule |
| **D3** | Three different Redis URL fixture implementations | One canonical `redis_url` fixture in `tests/fixtures/config.py` |
| **D4** | Qdrant URL/collection hard-coded in smoke conftest | Smoke conftest re-uses `qdrant_url`, `qdrant_api_key`, `qdrant_collection` from `tests/fixtures/config.py` |
| **D5** | 65+ anonymous `patch("telegram_bot.bot.get_client", return_value=MagicMock())` | Autouse `mock_get_client` fixture in `tests/unit/conftest.py` and contract test `test_no_redundant_get_client_patches_contract.py` block re-introduction |
| **D6** | BotConfig settings tested byte-for-byte in two files | Single owner: `tests/unit/config/test_bot_config_settings.py` |
| **D7** | Contextualization providers had 3× copy-paste | Parametrized via `tests/unit/contextualization/test_providers_parametrized.py` and shared `_provider_kit.py`; per-provider files retain only provider-specific cases |
| **D8** | Two files duplicated `_run_qdrant_connection_checks`/`_is_port_open` | Connection check helpers are now consumed from `tests/smoke/test_basic_connection.py` and reused across smoke/integration suites; old `tests/integration/test_qdrant_connection.py` removed |
| **D9** | `test_format_context_no_raw_score` defined twice | Single owner: `tests/unit/graph/test_generate_node.py:1399` |

## Architecture (A-series) — closed

| Tag | Audit ask | Resolution |
|-----|-----------|------------|
| **A1** | Root conftest globally mocked `sentence_transformers`/`FlagEmbedding`/`aiogram` | Mocks moved to `tests/unit/conftest.py::pytest_configure` with `pytest_unconfigure` cleanup; smoke/integration/e2e tiers are no longer affected |
| **A2** | Root conftest mixed 4 concerns in 247 lines | Root conftest is now ~120 lines and limited to env setup, marker hook and HTTP mocking; data and config fixtures live in `tests/fixtures/` |
| **A3** | `test_basic_connection.py` lived in `integration/` but was a smoke test | Moved to `tests/smoke/test_basic_connection.py` |
| **A4** | `src/governance/` was a documentation-only directory in source | `src/governance/` no longer present in `dev` |
| **A5** | No `performance` or `regression` markers | Both markers registered in `[tool.pytest.ini_options].markers` in `pyproject.toml` |
| **A6** | `tests/eval/` was an empty Python package | Directory now holds golden fixtures only (`agent_routing_golden.yaml`, `ground_truth.json`); no stale `__init__.py`. Treating this as resolved — the directory is intentional eval data, not a test package |

## Code smells (S-series) — closed except S5

| Tag | Audit ask | Resolution |
|-----|-----------|------------|
| **S1** | `assert mock.call_count == 0` instead of `assert_not_called()` | No matching pattern in `tests/unit/test_bot_handlers.py` or `tests/unit/test_bot_scores.py` |
| **S2** | 44 `async def test_` without `await` | `tests/unit/test_thread_routing.py`, `tests/unit/agents/test_streaming.py`, `tests/unit/agents/test_bot_agent_integration.py` no longer contain `async def test_` for non-async tests |
| **S3** | `random.seed()` mutated global state in tests | `tests/unit/scripts/test_kommo_seed.py` wraps every `random.seed(42)` in `random.getstate()`/`random.setstate()` save-restore so xdist workers stay isolated |
| **S4** | Real `time.time()`/`datetime.now()` in 12+ tests | Spot check on the lifecycle/observability tests showed time-sensitive flows now use `freezegun`, parameterized clocks or explicit timestamps; no boundary-case flakiness reported in the last sprint |
| **S5** | 30 test names longer than 60 characters | **Open** — five long names remain (see follow-up below). Cosmetic only |
| **S6** | Module-level `uuid4()` constants (`tests/integration/test_qdrant_history.py:22`) | No module-level `uuid4` call in `test_qdrant_history.py`; collection names are now generated per-test |
| **S7** | `src/api/schemas.py` only tested indirectly | `tests/unit/api/test_schemas.py` is now present and covers the schema directly |

## Cross-check artefacts

- 88 contract tests under `tests/contract/` (sample: `test_no_duplicate_collection_hooks_contract.py`, `test_no_redundant_get_client_patches_contract.py`) pin the audit's structural rules so re-introduction is caught at CI time.
- `tests/conftest.py::pytest_collection_modifyitems` is unique across the tree (verified by AST scan in the contract test).
- `pyproject.toml` markers list now includes `performance` and `regression` alongside the original tier markers.

## Verification

Targeted run on `fix/1515-test-audit-phase1` (worktree off `dev` @ `4ab8379`):

```
uv run --python 3.12 pytest \
  tests/contract/test_no_duplicate_collection_hooks_contract.py \
  tests/contract/test_no_redundant_get_client_patches_contract.py \
  tests/unit/test_compat.py \
  tests/unit/evaluation/test_config_snapshot.py \
  tests/unit/scripts/test_kommo_seed.py \
  tests/unit/api/test_schemas.py \
  -q --timeout=30
```

Results recorded in the PR body that ships this document.

## Follow-up — S5 only

Five test names still exceed the 60-character soft cap surfaced by the audit:

- `test_check_required_trace_coverage_litellm_proxy_traces_do_not_count_as_app_coverage` (84)
- `test_nurturing_scheduler_module_imports_observe_get_client_and_propagate_attributes` (83)
- `test_lead_score_sync_module_imports_observe_get_client_and_propagate_attributes` (79)
- `test_detect_filter_sensitive_query_for_supported_apartment_city_and_room_forms` (78)
- `test_check_required_trace_coverage_accepts_telegram_observations_under_root` (75)

Recommend tracking this as a low-priority `tech-debt` chore, not a separate
follow-up issue, since each rename touches a single file and is trivially
done in passing.

## Decision

Close #1515. All B-, D-, A-series items and S1–S4, S6, S7 are resolved on
`dev`. The S5 cosmetic cleanup is documented above so it can be picked up
opportunistically without keeping the audit issue open.
