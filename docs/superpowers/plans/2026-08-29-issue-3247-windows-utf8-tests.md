# Issue #3247 Deterministic Windows UTF-8 Test Reads Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the eight failing repository-source test reads deterministic on native Windows by declaring their real UTF-8 encoding.

**Architecture:** This is a mechanical test-harness correction. Explicit decoding belongs at each tracked-file read boundary; no global process encoding switch is permitted.

**Tech Stack:** Python 3.12, pathlib, pytest.

**Spec:** `docs/specs/2026-08-29-issue-3247-windows-utf8-tests.md`

## Global Constraints

- Work only in `.worktrees/issue-3247` on `codex/issue-3247-windows-utf8-tests`.
- Modify exactly the seven named test files plus this issue's spec/plan.
- Add no helper/abstraction, environment override, product change, or unrelated encoding cleanup.
- Preserve every assertion and path; only declare UTF-8 at the implicated reads.

---

## Task 1: Capture RED on Native Windows

- [x] Run the seven focused modules without `-X utf8` or encoding environment overrides.
- [x] Record the eight expected `UnicodeDecodeError` nodes and confirm the process default is cp1251.

```powershell
uv run --no-sync pytest -q --tb=short tests/unit/security/test_secret_hygiene.py tests/unit/test_catalog_handler.py tests/unit/test_check_image_drift.py tests/unit/test_cloud_dependency_contract.py tests/unit/test_docker_static_validation.py tests/unit/test_env_example.py tests/unit/test_kfp_kubernetes_dependency_contract.py
```

## Task 2: Add Explicit UTF-8 at the Read Boundaries

**Files:** the seven paths named in Global Constraints.

- [x] Add `encoding="utf-8"` to only the implicated `Path.read_text()` calls.
- [x] Update every read in the catalog concatenation expression.
- [x] Do not alter assertions, fixture content, or application code.

## Task 3: Capture GREEN and Commit

- [x] Run the exact RED command again with no encoding override; all former decoding failures must pass.
- [x] Run `git diff --check` and inspect the full mechanical diff.
- [x] Commit only the nine owned files; do not push or mutate GitHub.

## Review Follow-up: Complete Scoped Repository Reads

- [x] Add `encoding="utf-8"` to the 17 reviewer-identified repository-source reads.
- [x] Re-run the focused suite and prove no scoped unqualified `read_text()` remains.
- [x] Commit the review fix separately.
