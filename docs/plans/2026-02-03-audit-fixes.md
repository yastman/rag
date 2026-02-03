# RAG 2026 Audit Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 4 issues found during RAG 2026 audit: ACORN tests, missing pytest-httpx, lint errors, mypy errors

**Architecture:** Sequential fixes — dependencies first, then ACORN, then lint/types. Each fix isolated and verified.

**Tech Stack:** pytest, qdrant-client, ruff, mypy, uv

---

## Task 1: Add Missing pytest-httpx Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Check current test collection errors**

Run: `pytest --collect-only 2>&1 | grep -E "error|httpx" | head -10`
Expected: Errors mentioning pytest_httpx

**Step 2: Add pytest-httpx to dev dependencies**

Run: `uv add pytest-httpx --dev`
Expected: Package added to pyproject.toml

**Step 3: Verify collection errors fixed**

Run: `pytest --collect-only 2>&1 | grep -E "error" | head -5`
Expected: No httpx-related errors

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "fix(deps): add missing pytest-httpx dev dependency"
```

---

## Task 2: Fix ACORN Tests — Diagnose Issue

**Files:**
- Check: `tests/unit/test_acorn.py`
- Check: `src/retrieval/acorn.py` or similar

**Step 1: Run ACORN tests to see exact failures**

Run: `pytest tests/unit/test_acorn.py -v 2>&1 | head -50`
Expected: See which tests fail and why

**Step 2: Check qdrant-client version**

Run: `uv pip show qdrant-client | grep -E "Version|Name"`
Expected: Version info

**Step 3: Check if AcornSearchParams exists in qdrant-client**

Run: `python -c "from qdrant_client.models import AcornSearchParams; print('OK')" 2>&1`
Expected: Either OK or ImportError

**Step 4: Document finding**

If ImportError → Task 3A (update qdrant-client)
If OK but tests fail → Task 3B (fix test implementation)

---

## Task 3A: Update qdrant-client (if AcornSearchParams missing)

**Files:**
- Modify: `pyproject.toml`

**Step 1: Check latest qdrant-client version with ACORN support**

Run: `uv pip index versions qdrant-client 2>/dev/null | head -5 || pip index versions qdrant-client 2>/dev/null | head -5`
Expected: List of versions

**Step 2: Update qdrant-client to latest**

Run: `uv add qdrant-client@latest`
Expected: Updated in pyproject.toml

**Step 3: Verify AcornSearchParams now available**

Run: `python -c "from qdrant_client.models import AcornSearchParams; print('OK')"`
Expected: OK

**Step 4: Run ACORN tests**

Run: `pytest tests/unit/test_acorn.py -v 2>&1 | tail -20`
Expected: All pass or fewer failures

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "fix(deps): update qdrant-client for ACORN support"
```

---

## Task 3B: Skip ACORN Tests (if qdrant-client update not possible)

**Files:**
- Modify: `tests/unit/test_acorn.py`

**Step 1: Add skip marker to tests requiring AcornSearchParams**

```python
import pytest

try:
    from qdrant_client.models import AcornSearchParams
    ACORN_AVAILABLE = True
except ImportError:
    ACORN_AVAILABLE = False

@pytest.mark.skipif(not ACORN_AVAILABLE, reason="AcornSearchParams not in qdrant-client")
```

**Step 2: Apply skip marker to failing tests**

Add decorator to each test that uses AcornSearchParams.

**Step 3: Run tests**

Run: `pytest tests/unit/test_acorn.py -v 2>&1 | tail -20`
Expected: Tests skipped, no failures

**Step 4: Commit**

```bash
git add tests/unit/test_acorn.py
git commit -m "fix(tests): skip ACORN tests when AcornSearchParams unavailable"
```

---

## Task 4: Fix Lint Errors

**Files:**
- Multiple files with Optional style issues

**Step 1: Check lint error count**

Run: `ruff check . 2>&1 | tail -5`
Expected: Shows error count

**Step 2: Auto-fix safe lint errors**

Run: `ruff check . --fix`
Expected: Many errors auto-fixed

**Step 3: Check remaining errors**

Run: `ruff check . 2>&1 | head -30`
Expected: Fewer errors, review what remains

**Step 4: Fix remaining errors manually (if any)**

Review output and fix manually if needed.

**Step 5: Verify clean**

Run: `ruff check . 2>&1 | tail -3`
Expected: No errors or only acceptable ones

**Step 6: Commit**

```bash
git add -u
git commit -m "fix(lint): auto-fix ruff errors"
```

---

## Task 5: Review MyPy Errors

**Files:**
- Multiple files with type errors

**Step 1: Run mypy and capture errors**

Run: `mypy src/ 2>&1 | head -50`
Expected: List of type errors

**Step 2: Identify error categories**

Run: `mypy src/ 2>&1 | grep -oE "\[.*\]" | sort | uniq -c | sort -rn | head -10`
Expected: Most common error types

**Step 3: Decide action**

- If mostly third-party stubs missing → add type-ignore comments
- If real errors → fix them
- If external deps (mlflow) → ignore

**Step 4: Fix critical type errors only**

Focus on errors in core business logic, not external dependencies.

**Step 5: Commit**

```bash
git add -u
git commit -m "fix(types): address critical mypy errors"
```

---

## Task 6: Final Verification

**Files:**
- None (verification only)

**Step 1: Run full test suite**

Run: `make test 2>&1 | tail -30`
Expected: All tests pass (or only known skips)

**Step 2: Run lint**

Run: `make check 2>&1 | tail -20`
Expected: Clean or acceptable warnings only

**Step 3: Verify ACORN status**

Run: `pytest tests/unit/test_acorn.py -v 2>&1 | tail -10`
Expected: All pass or properly skipped

**Step 4: Document final status**

Update audit report with results.

---

## Summary

| Task | Description | Priority |
|------|-------------|----------|
| 1 | Add pytest-httpx | HIGH |
| 2 | Diagnose ACORN | HIGH |
| 3A/3B | Fix/Skip ACORN | HIGH |
| 4 | Fix lint errors | MED |
| 5 | Review mypy errors | MED |
| 6 | Final verification | HIGH |

**Estimated time:** 20-30 minutes

---

## Dependencies

```
Task 1 → independent
Task 2 → depends on Task 1 (clean collection)
Task 3A/3B → depends on Task 2 diagnosis
Task 4 → independent
Task 5 → independent
Task 6 → depends on all above
```

Parallel execution possible: Task 1, Task 4, Task 5 can run simultaneously.
