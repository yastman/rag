# Issue 1091 Unified Ingestion Coverage Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development`, `superpowers:requesting-code-review`, and `superpowers:verification-before-completion` before commit.

**Goal:** Add deterministic unit coverage for unified ingestion state transitions, flow wiring, and target connector state/write paths without changing ingestion identity or runtime semantics unless a test exposes a real defect.

**Architecture:** This is a test-coverage issue. Keep production changes minimal and only when a new test reveals an existing correctness bug. Split work by test ownership so part workers can run in parallel without shared files.

**Tech Stack:** pytest, unittest.mock, async mocks, CocoIndex-gated tests with `pytest.importorskip("cocoindex")`, existing `UnifiedStateManager`, `flow.py`, and `QdrantHybridTargetConnector`.

---

## Smart Routing

Lane: `Full plan` because issue #1091 is `lane:plan-needed`, touches ingestion runtime contracts, and spans state manager, flow, and target connector coverage.

Execution shape:
- `W-1091-state`: state manager transition and concurrency tests only.
- `W-1091-flow`: flow/manifest wiring tests only.
- `W-1091-target`: target connector state/write path tests only.
- `W-1091-final`: merge part branches, run focused checks, create PR against `dev`.

Parallelization guard:
- Workers must use separate git worktrees and branches.
- Part workers must not create PRs.
- Part workers own disjoint test files; no shared file edits.

## Repository Constraints

- Root `AGENTS.md` applies.
- `src/ingestion/unified/AGENTS.override.md` applies to ingestion runtime contracts.
- Preserve deterministic/resumable ingestion behavior.
- Do not alter collection names, manifest identity, content hashing, or file identity semantics unless a failing regression proves a bug.
- For test-only changes, run focused pytest first, then `make check`. Final worker/orchestrator decides whether broad `make test-unit` is needed based on CI and runtime-surface changes.

## Worker Slices

### Task 1: State Manager Transitions

**Owner:** `W-1091-state`

**Files:**
- Create or modify only: `tests/unit/ingestion/test_state_manager_transitions.py`

**Acceptance Criteria:**
- Cover async transition SQL for `pending/new -> processing -> indexed`.
- Cover `processing/error -> error` retry bookkeeping and truncation through existing async method behavior.
- Cover concurrent async updates deterministically with mock pool calls, without a real database.
- Cover `sync_context()` cleanup: pool is closed and manager pool/runner are reset after context exit.
- Do not edit production code unless a test exposes a real defect.

**Suggested Tests:**
- `test_mark_processing_upserts_processing_for_new_file`
- `test_processing_to_indexed_resets_error_and_retry_fields`
- `test_mark_error_updates_retry_backoff_atomically`
- `test_concurrent_mark_processing_updates_all_file_ids`
- `test_sync_context_closes_pool_and_resets_runner`

**Commands:**
- `uv run pytest tests/unit/ingestion/test_state_manager_transitions.py -q`
- `make check`

### Task 2: Flow And Manifest Wiring

**Owner:** `W-1091-flow`

**Files:**
- Create or modify only: `tests/unit/ingestion/test_unified_flow_wiring.py`

**Acceptance Criteria:**
- Cover manifest directory selection via `UnifiedConfig.effective_manifest_dir()` in `build_flow()`.
- Cover `file_id_from_content()` passes content hash to manifest and remains rename-stable via manifest lookup.
- Cover `build_flow()` closes an existing registered flow before opening a replacement.
- Cover `run_once()` trace behavior for success and error paths.
- Tests must be deterministic and skip cleanly if `cocoindex` extra is unavailable.

**Suggested Tests:**
- `test_build_flow_uses_effective_manifest_dir`
- `test_file_id_from_content_passes_content_hash_to_manifest`
- `test_build_flow_closes_registered_flow_before_reopen`
- `test_run_once_records_error_status_when_update_fails`
- If a close-on-error regression is found, add a focused test and minimal production fix.

**Commands:**
- `uv run pytest tests/unit/ingestion/test_unified_flow_wiring.py -q`
- `make check`

### Task 3: Target Connector State/Writer Paths

**Owner:** `W-1091-target`

**Files:**
- Create or modify only: `tests/unit/ingestion/test_qdrant_hybrid_target_state_paths.py`

**Acceptance Criteria:**
- Cover delete mutation calls writer delete and marks state deleted.
- Cover upsert skips parse/write when `should_process_sync()` returns `False`.
- Cover empty parser chunks marks indexed with zero chunks.
- Cover writer errors call `mark_error_sync()` and optionally DLQ when retry count reaches max.
- Tests must patch writer/docling/content hash and avoid real Qdrant, Postgres, Docling, or embedding services.
- Tests must skip cleanly if `cocoindex` extra is unavailable.

**Suggested Tests:**
- `test_handle_delete_deletes_points_and_marks_deleted`
- `test_handle_upsert_skips_unchanged_file_before_parsing`
- `test_handle_upsert_empty_chunks_marks_indexed_zero`
- `test_handle_upsert_writer_error_marks_error`
- `test_handle_upsert_moves_to_dlq_after_max_retries`

**Commands:**
- `uv run pytest tests/unit/ingestion/test_qdrant_hybrid_target_state_paths.py -q`
- `make check`

### Task 4: Final Integration

**Owner:** `W-1091-final`

**Files:**
- Existing plan file.
- Test files from part workers.
- Minimal production files only if part workers exposed/fixed a real defect.

**Steps:**
- Merge `origin/fix/1091-state-tests`, `origin/fix/1091-flow-tests`, and `origin/fix/1091-target-tests` into `fix/1091-ingestion-coverage`.
- Resolve conflicts conservatively. Do not rewrite worker tests unless needed for integration.
- Run focused suite:
  - `uv run pytest tests/unit/ingestion/test_state_manager_transitions.py tests/unit/ingestion/test_unified_flow_wiring.py tests/unit/ingestion/test_qdrant_hybrid_target_state_paths.py -q`
- Run `make check`.
- If production behavior changed under `src/ingestion/unified/**`, also run:
  - `python -m src.ingestion.unified.cli preflight`
  - `make ingest-unified-status`
- Create PR against `dev` with `Closes #1091`.

**Done Definition:**
- Plan committed before implementation.
- Each part branch has focused tests and `make check` evidence in DONE JSON.
- Final PR targets `dev`, links `Closes #1091`, and includes verification evidence.
- Orchestrator performs diff review and fresh verification before merge.
