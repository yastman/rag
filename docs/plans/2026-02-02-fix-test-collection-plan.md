# Test Collection Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 12 pytest collection errors so `pytest tests/ --collect-only` succeeds

**Architecture:** Fix syntax errors, add import skips for optional deps, exclude legacy tests from default collection

**Tech Stack:** Python 3.12, pytest, pyproject.toml

---

## Pre-flight Check

**Run before starting:**

```bash
uv run python -m pytest tests/ --collect-only 2>&1 | tail -20
```

**Expected output (current broken state):**

```
ERROR tests/baseline/test_cli.py
ERROR tests/benchmark/test_docling_vs_pymupdf.py
...
!!!!!!!!!!!!!!!!!!! Interrupted: 12 errors during collection !!!!!!!!!!!!!!!!!!!
```

---

## Task 1: Fix SyntaxError in cli.py

**Files:**
- Modify: `tests/baseline/cli.py:191-230`

**Step 1: Verify the syntax error**

Run:
```bash
uv run python -c "import tests.baseline.cli" 2>&1 | head -5
```

Expected: `SyntaxError: unexpected character after line continuation character`

**Step 2: Fix the escaped quotes in f-string**

The file has `f\"\"\"` instead of `f"""` and `\\"` instead of `"`. This is a copy-paste artifact.

In `tests/baseline/cli.py`, make these replacements:

**Line 191:** Replace `f\"\"\"` with `f"""`
**Line 192:** Replace `lang=\\"en\\"` with `lang="en"`
**Line 194:** Replace `charset=\\"UTF-8\\"` with `charset="UTF-8"`
**Line 212:** Replace `class=\\"{'pass'` with `class="{'pass'` and `'fail'}\\">` with `'fail'}">`
**Line 257:** Replace `\"\"\"` with `"""`

Or use sed for bulk fix:
```bash
sed -i 's/\\"/"/g; s/f\\"\\"\\"/f"""/g; s/\\"\\"\\"/"""/g' tests/baseline/cli.py
```

**Simpler approach:** The escapes are `\"` → `"` throughout lines 191-257. Use editor find/replace.

**Step 3: Verify fix**

Run:
```bash
uv run python -c "import tests.baseline.cli; print('OK')"
```

Expected: `OK`

**Step 4: Verify test collection**

Run:
```bash
uv run python -m pytest tests/baseline/test_cli.py --collect-only 2>&1 | tail -5
```

Expected: `4 tests collected` (no errors)

**Step 5: Commit**

```bash
git add tests/baseline/cli.py
git commit -m "fix(tests): fix escaped quotes in baseline cli.py HTML template"
```

---

## Task 2: Fix HybridRetrieverService Import

**Files:**
- Modify: `tests/e2e/test_e2e_pipeline.py:12-19`

**Step 1: Verify the import error**

Run:
```bash
uv run python -c "from telegram_bot.services import HybridRetrieverService" 2>&1
```

Expected: `AttributeError: module 'telegram_bot.services' has no attribute 'HybridRetrieverService'`

**Step 2: Check what's actually exported**

Run:
```bash
uv run python -c "from telegram_bot.services import RetrieverService; print(RetrieverService)"
```

Expected: `<class 'telegram_bot.services.retriever.RetrieverService'>`

**Step 3: Update the import in test file**

In `tests/e2e/test_e2e_pipeline.py`, change line 14:

From:
```python
from telegram_bot.services import (
    CacheService,
    HybridRetrieverService,
    LLMService,
```

To:
```python
from telegram_bot.services import (
    CacheService,
    RetrieverService,
    LLMService,
```

**Step 4: Update any usage of HybridRetrieverService in the file**

Search and replace `HybridRetrieverService` → `RetrieverService` throughout the file.

**Step 5: Verify fix**

Run:
```bash
uv run python -m pytest tests/e2e/test_e2e_pipeline.py --collect-only 2>&1 | tail -5
```

Expected: Tests collected (no import error)

**Step 6: Commit**

```bash
git add tests/e2e/test_e2e_pipeline.py
git commit -m "fix(tests): use RetrieverService instead of HybridRetrieverService"
```

---

## Task 3: Fix asyncpg Import with importorskip

**Files:**
- Modify: `tests/integration/test_docker_services.py:1-6`

**Step 1: Verify the import error**

Run:
```bash
uv run python -c "import asyncpg" 2>&1
```

Expected: `ModuleNotFoundError: No module named 'asyncpg'`

**Step 2: Update imports to use importorskip**

In `tests/integration/test_docker_services.py`, change the top of file from:

```python
import aiohttp
import asyncpg
import pytest
import redis.asyncio as redis
from qdrant_client import QdrantClient
```

To:

```python
import aiohttp
import pytest
import redis.asyncio as redis
from qdrant_client import QdrantClient

# Optional dependency - skip tests if not installed
asyncpg = pytest.importorskip("asyncpg", reason="asyncpg not installed")
```

**Step 3: Verify fix**

Run:
```bash
uv run python -m pytest tests/integration/test_docker_services.py --collect-only 2>&1 | tail -5
```

Expected: Either tests collected OR clean skip message (not import error)

**Step 4: Commit**

```bash
git add tests/integration/test_docker_services.py
git commit -m "fix(tests): make asyncpg optional in docker services test"
```

---

## Task 4: Exclude Legacy Tests from Collection

**Files:**
- Modify: `pyproject.toml` (pytest section, around line 277)

**Step 1: Count legacy test errors**

Run:
```bash
uv run python -m pytest tests/legacy/ --collect-only 2>&1 | grep "ERROR collecting" | wc -l
```

Expected: 7 errors

**Step 2: Add norecursedirs to pytest config**

In `pyproject.toml`, find the `[tool.pytest.ini_options]` section (line 277) and add `norecursedirs`:

From:
```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = """
    -ra
    --strict-markers
    --strict-config
    --showlocals
"""
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
```

To:
```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = """
    -ra
    --strict-markers
    --strict-config
    --showlocals
"""
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
norecursedirs = ["tests/legacy"]
```

**Step 3: Verify legacy tests are excluded**

Run:
```bash
uv run python -m pytest tests/ --collect-only 2>&1 | grep "tests/legacy" | wc -l
```

Expected: 0 (no legacy tests collected)

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "fix(tests): exclude legacy tests from default collection"
```

---

## Task 5: Fix Benchmark pymupdf_chunker Import

**Files:**
- Modify: `tests/benchmark/test_docling_vs_pymupdf.py:18`

**Step 1: Verify the import error**

Run:
```bash
uv run python -c "from pymupdf_chunker import PyMuPDFChunker" 2>&1
```

Expected: `ModuleNotFoundError: No module named 'pymupdf_chunker'`

**Step 2: Check if legacy module exists**

Run:
```bash
ls -la legacy/pymupdf_chunker.py
```

Expected: File exists

**Step 3: Update import to use legacy path**

In `tests/benchmark/test_docling_vs_pymupdf.py`, change line 18:

From:
```python
from pymupdf_chunker import PyMuPDFChunker
```

To:
```python
from legacy.pymupdf_chunker import PyMuPDFChunker
```

**Step 4: Verify fix**

Run:
```bash
uv run python -m pytest tests/benchmark/test_docling_vs_pymupdf.py --collect-only 2>&1 | tail -3
```

Expected: `1 test collected`

**Step 5: Commit**

```bash
git add tests/benchmark/test_docling_vs_pymupdf.py
git commit -m "fix(tests): use legacy path for pymupdf_chunker import"
```

---

## Task 6: Fix Smoke Test pymupdf_chunker Import

**Files:**
- Modify: `tests/smoke/test_chunking_smoke.py:17`

**Step 1: Verify the import error**

Run:
```bash
uv run python -m pytest tests/smoke/test_chunking_smoke.py --collect-only 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'pymupdf_chunker'`

**Step 2: Update import to use legacy path**

In `tests/smoke/test_chunking_smoke.py`, change line 17:

From:
```python
from pymupdf_chunker import PyMuPDFChunker
```

To:
```python
from legacy.pymupdf_chunker import PyMuPDFChunker
```

**Step 3: Verify fix**

Run:
```bash
uv run python -m pytest tests/smoke/test_chunking_smoke.py --collect-only 2>&1 | tail -3
```

Expected: Tests collected (no import error)

**Step 4: Commit**

```bash
git add tests/smoke/test_chunking_smoke.py
git commit -m "fix(tests): use legacy path for pymupdf_chunker in smoke test"
```

---

## Task 7: Final Collection Verification

**Step 1: Run full collection check**

Run:
```bash
uv run python -m pytest tests/ --collect-only 2>&1 | tail -10
```

Expected:
```
================= X tests collected in Y.YYs =================
```

No `ERROR collecting` messages.

**Step 2: Verify error count is zero**

Run:
```bash
uv run python -m pytest tests/ --collect-only 2>&1 | grep -c "ERROR collecting"
```

Expected: `0`

**Step 3: Run quick unit test subset to verify nothing broke**

Run:
```bash
uv run python -m pytest tests/unit/test_settings.py -v
```

Expected: All tests pass

**Step 4: Commit verification (optional tag)**

If all checks pass:
```bash
git tag -a test-collection-fixed -m "pytest collection errors fixed"
```

---

## Verification Checklist

- [ ] `tests/baseline/cli.py` imports without SyntaxError
- [ ] `tests/e2e/test_e2e_pipeline.py` uses `RetrieverService`
- [ ] `tests/integration/test_docker_services.py` uses `importorskip` for asyncpg
- [ ] `pyproject.toml` has `norecursedirs = ["tests/legacy"]`
- [ ] `tests/benchmark/test_docling_vs_pymupdf.py` uses `legacy.pymupdf_chunker`
- [ ] `tests/smoke/test_chunking_smoke.py` uses `legacy.pymupdf_chunker`
- [ ] `pytest tests/ --collect-only` shows 0 errors

---

## Rollback

If something goes wrong:

```bash
git checkout HEAD~N -- <file>  # Revert specific file
git reset --hard HEAD~N        # Revert all N commits
```
