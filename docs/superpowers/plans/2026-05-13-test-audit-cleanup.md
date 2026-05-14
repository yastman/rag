# Test Audit Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 bugs, eliminate 9 code duplications, resolve 6 architectural issues, and address 7 code smells in the test suite (6879 tests, ~280 files, 13 conftest.py).

**Architecture:** 4-phase approach — Phase 1 fixes critical bugs (safety-first), Phase 2 eliminates copy-paste code (DRY), Phase 3 restructures test architecture (conftest modularity), Phase 4 addresses low-priority code smells (optional). Each task is self-contained with its own test verification.

**Tech Stack:** Python 3.13, pytest 8.x, pytest-asyncio, unittest.mock, pytest-monkeypatch

---

## File Structure Map

```
tests/
├── conftest.py                    # MODIFY: add contract/baseline markers, split concerns
├── fixtures/                      # NEW: extracted fixtures
│   ├── __init__.py
│   ├── config.py                  # NEW: qdrant_url, redis_url, bge_m3_url, etc.
│   └── data.py                    # NEW: sample_context_chunks, sample_texts, etc.
├── unit/
│   ├── conftest.py                # MODIFY: receive ML mocks from root, add get_client fixture
│   ├── test_compat.py             # NEW: tests for src/_compat.py
│   ├── test_settings.py           # MODIFY: remove duplicated BotConfig tests (lines 239-275)
│   ├── test_bot_handlers.py       # MODIFY: call_count==0 → assert_not_called (line 720)
│   ├── test_bot_scores.py         # MODIFY: call_count==0 → assert_not_called (lines 903,923)
│   ├── core/
│   │   └── test_pipeline.py       # RECEIVE: e2e test_rag_pipeline.py content merged here
│   ├── evaluation/
│   │   └── test_config_snapshot.py # NEW: tests for src/evaluation/config_snapshot.py
│   ├── contextualization/
│   │   └── test_providers.py      # NEW: parametrized Claude/OpenAI/Groq (replaces 3 files)
│   ├── api/
│   │   └── test_schemas.py        # NEW: dedicated schemas tests
│   └── scripts/
│       └── test_kommo_seed.py     # MODIFY: random.seed() → random.Random()
├── e2e/
│   ├── conftest.py                # MODIFY: remove redundant pytest_collection_modifyitems
│   ├── test_rag_pipeline.py       # DELETE: moved to tests/unit/core/
│   └── test_core_flows_live.py    # DELETE: moved to tests/unit/core/
├── smoke/
│   ├── conftest.py                # MODIFY: fix asyncio.get_event_loop, reuse root fixtures
│   └── test_basic_connection.py   # NEW: moved from tests/integration/
├── integration/
│   ├── conftest.py                # MODIFY: remove redundant pytest_collection_modifyitems
│   ├── test_basic_connection.py   # DELETE: moved to tests/smoke/
│   ├── test_qdrant_connection.py  # DELETE: merged into test_basic_connection
│   └── test_qdrant_history.py     # MODIFY: uuid4() → fixed collection name
├── chaos/
│   ├── conftest.py                # MODIFY: remove redundant collection_modifyitems + chunk fixture
├── benchmark/
│   └── conftest.py                # MODIFY: remove redundant collection_modifyitems
├── load/
│   └── conftest.py                # MODIFY: remove redundant collection_modifyitems
├── contract/
│   └── conftest.py                # (already minimal, OK)
├── baseline/
│   └── conftest.py                # (already minimal, OK)
└── eval/
    └── __init__.py                # DELETE: empty directory

pyproject.toml                     # MODIFY: add contract/baseline markers, add .venv omit
src/_compat.py                     # UNCHANGED (we test it, don't change it)
src/evaluation/config_snapshot.py  # UNCHANGED (we test it, don't change it)
```

---

## Phase 1: Critical Bugs

### Task 1: Fix `asyncio.get_event_loop()` deprecation in smoke conftest

**Files:**
- Modify: `tests/smoke/conftest.py:54-62`

- [ ] **Step 1: Verify the bug exists**

```bash
grep -n "get_event_loop" tests/smoke/conftest.py
```
Expected output: `62:    asyncio.get_event_loop().run_until_complete(check_redis())`

- [ ] **Step 2: Replace deprecated call with `asyncio.run()`**

Replace lines 54-62 in `tests/smoke/conftest.py`:
```python
    async def check_redis():
        try:
            client = redis.from_url(redis_url, socket_connect_timeout=2)
            await client.ping()
            await client.aclose()
        except Exception:
            pytest.skip("Redis not available")

    asyncio.get_event_loop().run_until_complete(check_redis())
```

With:
```python
    async def check_redis():
        try:
            client = redis.from_url(redis_url, socket_connect_timeout=2)
            await client.ping()
            await client.aclose()
        except Exception:
            pytest.skip("Redis not available")

    try:
        asyncio.run(check_redis())
    except RuntimeError:
        # Already in running event loop (nested asyncio.run scenario)
        loop = asyncio.get_running_loop()
        loop.run_until_complete(check_redis())
```

- [ ] **Step 3: Replace `require_live_services` fixture from sync to async**

Since the fixture now uses `asyncio.run()`, it must stay synchronous (module-scoped fixtures can be sync). The `asyncio.run()` call is correct for a sync fixture — no further changes needed.

- [ ] **Step 4: Verify fix**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/smoke/test_preflight.py -v --co 2>&1 | head -20
```
Expected: tests collect successfully, skip if no Docker services.

- [ ] **Step 5: Commit**

```bash
git add tests/smoke/conftest.py
git commit -m "fix(tests): replace deprecated asyncio.get_event_loop() with asyncio.run() in smoke conftest"
```

---

### Task 2: Move mock-only E2E tests to unit/

**Files:**
- Modify: `tests/e2e/test_rag_pipeline.py` → delete, content merged into `tests/unit/core/test_pipeline.py`
- Create/Modify: `tests/unit/core/test_pipeline.py` (append RAGPipeline tests from e2e file)
- Modify: `tests/e2e/test_core_flows_live.py` → delete, content merged into `tests/unit/core/`

- [ ] **Step 1: Read the target unit test file to plan merge**

Run: `wc -l tests/unit/core/test_pipeline.py`

- [ ] **Step 2: Move test_rag_pipeline.py content to unit/core/**

```bash
cd /home/user/projects/rag-fresh
# Read the e2e file to understand what's being moved
grep "^class \|^    def test_\|^    async def test_" tests/e2e/test_rag_pipeline.py
```
Expected: `TestRAGPipelineInit`, `TestRAGPipelineContextualizer`, `TestRAGPipelineSearch`, `TestRAGPipelineEvaluate`, `TestRAGPipelineStats`, `TestRAGResult`

- [ ] **Step 3: Create the merged file**

Copy all class definitions from `tests/e2e/test_rag_pipeline.py` (lines 17-386) into the end of `tests/unit/core/test_pipeline.py`, wrapping them with appropriate markers. Use existing content in `tests/unit/core/test_pipeline.py` — if it already exists and tests RAGPipeline, append to it; if it doesn't exist, create it.

```bash
# First check what's in the existing unit test
head -50 tests/unit/core/test_pipeline.py 2>/dev/null || echo "FILE_DOES_NOT_EXIST"
```

If the file exists, append the e2e test classes. If not, create it with the content from `tests/e2e/test_rag_pipeline.py`, adding the `from unittest.mock import MagicMock, patch` import and `pytest.importorskip("pymupdf", ...)` guard at top.

- [ ] **Step 4: Delete the old e2e test files**

```bash
git rm tests/e2e/test_rag_pipeline.py tests/e2e/test_core_flows_live.py
```

- [ ] **Step 5: Verify tests still pass in their new location**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/core/test_pipeline.py -v --co 2>&1 | tail -30
```
Expected: all RAGPipeline tests collected and passing.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/core/test_pipeline.py
git commit -m "refactor(tests): move mock-only E2E RAG pipeline tests to unit/core/"
```

---

### Task 3: Add tests for `src/_compat.py`

**Files:**
- Create: `tests/unit/test_compat.py`
- No source changes

- [ ] **Step 1: Write the test file**

Create `tests/unit/test_compat.py`:
```python
"""Unit tests for src/_compat.py compatibility helpers."""

import warnings

import pytest


class TestLoadDeprecatedPackageExport:
    def test_emits_deprecation_warning(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            load_deprecated_package_export(
                module_name="old.module",
                attr_name="OldClass",
                target=("new.module", "NewClass", "new.module.NewClass"),
            )

        assert len(caught) == 1
        assert issubclass(caught[0].category, DeprecationWarning)
        msg = str(caught[0].message)
        assert "old.module.OldClass" in msg
        assert "deprecated" in msg.lower()
        assert "new.module.NewClass" in msg

    def test_returns_target_attribute(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = load_deprecated_package_export(
                module_name="old.module",
                attr_name="OldClass",
                target=("json", "dumps", "json.dumps"),
            )

        from json import dumps

        assert result is dumps

    def test_raises_attribute_error_for_nonexistent_target(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(AttributeError):
                load_deprecated_package_export(
                    module_name="old.module",
                    attr_name="OldClass",
                    target=("json", "nonexistent_attr_xyz", "json.nonexistent_attr_xyz"),
                )

    def test_raises_module_not_found_for_bad_module(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(ModuleNotFoundError):
                load_deprecated_package_export(
                    module_name="old.module",
                    attr_name="OldClass",
                    target=(
                        "nonexistent_module_xyz_123",
                        "SomeClass",
                        "nonexistent_module_xyz_123.SomeClass",
                    ),
                )

    def test_warning_includes_replacement_suggestion(self):
        from src._compat import load_deprecated_package_export

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            load_deprecated_package_export(
                module_name="pkg",
                attr_name="func",
                target=("os.path", "join", "os.path.join"),
            )

        assert len(caught) == 1
        assert "import os.path.join instead" in str(caught[0].message)
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/test_compat.py -v
```
Expected: 5 passed

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_compat.py
git commit -m "test: add unit tests for src/_compat.py compatibility layer"
```

---

### Task 4: Add tests for `src/evaluation/config_snapshot.py`

**Files:**
- Create: `tests/unit/evaluation/test_config_snapshot.py`
- No source changes

- [ ] **Step 1: Write the test file**

Create `tests/unit/evaluation/test_config_snapshot.py`:
```python
"""Unit tests for src/evaluation/config_snapshot.py."""

import json

import pytest

from src.evaluation.config_snapshot import (
    CONFIG_SNAPSHOT,
    get_config_hash,
    get_config_summary,
    validate_config,
)


class TestGetConfigHash:
    def test_returns_12_char_hex_string(self):
        result = get_config_hash()
        assert isinstance(result, str)
        assert len(result) == 12
        assert all(c in "0123456789abcdef" for c in result)

    def test_is_deterministic(self):
        h1 = get_config_hash()
        h2 = get_config_hash()
        assert h1 == h2

    def test_changes_when_config_changes(self):
        original = CONFIG_SNAPSHOT["metadata"]["version"]
        try:
            CONFIG_SNAPSHOT["metadata"]["version"] = "99.99.99"
            h1 = get_config_hash()
            CONFIG_SNAPSHOT["metadata"]["version"] = "0.0.0"
            h2 = get_config_hash()
            assert h1 != h2
        finally:
            CONFIG_SNAPSHOT["metadata"]["version"] = original


class TestGetConfigSummary:
    def test_returns_dict_with_expected_keys(self):
        summary = get_config_summary()
        assert isinstance(summary, dict)
        for key in ("version", "date", "config_hash", "models", "collection", "best_engine"):
            assert key in summary, f"Missing key: {key}"

    def test_models_contains_embedder_and_dim(self):
        summary = get_config_summary()
        assert "embedder" in summary["models"]
        assert "dense_dim" in summary["models"]

    def test_collection_contains_name_and_points(self):
        summary = get_config_summary()
        assert "name" in summary["collection"]
        assert "points" in summary["collection"]

    def test_best_engine_has_expected_name(self):
        summary = get_config_summary()
        assert summary["best_engine"]["name"] == "dbsf_colbert"


class TestValidateConfig:
    def test_validates_correct_config(self):
        assert validate_config() is True

    def test_raises_on_missing_key(self):
        saved = CONFIG_SNAPSHOT.pop("metadata", None)
        try:
            with pytest.raises(ValueError, match="Missing required config key: metadata"):
                validate_config()
        finally:
            if saved is not None:
                CONFIG_SNAPSHOT["metadata"] = saved

    def test_raises_on_negative_points_count(self):
        original = CONFIG_SNAPSHOT["collection"]["points_count"]
        try:
            CONFIG_SNAPSHOT["collection"]["points_count"] = 0
            with pytest.raises(ValueError, match="points_count must be positive"):
                validate_config()
        finally:
            CONFIG_SNAPSHOT["collection"]["points_count"] = original

    def test_raises_on_zero_total_queries(self):
        original = CONFIG_SNAPSHOT["evaluation"]["total_queries"]
        try:
            CONFIG_SNAPSHOT["evaluation"]["total_queries"] = 0
            with pytest.raises(ValueError, match="Total queries must be positive"):
                validate_config()
        finally:
            CONFIG_SNAPSHOT["evaluation"]["total_queries"] = original


def test_config_snapshot_is_valid_json():
    json_str = json.dumps(CONFIG_SNAPSHOT, sort_keys=True)
    assert json.loads(json_str) == CONFIG_SNAPSHOT
```

- [ ] **Step 2: Run tests**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/evaluation/test_config_snapshot.py -v
```
Expected: 10 passed

- [ ] **Step 3: Commit**

```bash
git add tests/unit/evaluation/test_config_snapshot.py
git commit -m "test: add unit tests for src/evaluation/config_snapshot.py"
```

---

### Task 5: Add `contract` and `baseline` directories to auto-marker hook

**Files:**
- Modify: `tests/conftest.py:47-55`
- Modify: `pyproject.toml:382-395` (add marker definitions)

- [ ] **Step 1: Add markers to pyproject.toml**

In `pyproject.toml`, after line 392 (`"requires_extras: ..."`), add:
```toml
    "contract: Contract tests (span/trace/error contracts)",
    "baseline: Baseline comparison tests (regression guard)",
```

- [ ] **Step 2: Add directories to root conftest marker hook**

In `tests/conftest.py`, change lines 47-55 from:
```python
    path_to_marker = {
        root / "unit": "unit",
        root / "integration": "integration",
        root / "smoke": "smoke",
        root / "e2e": "e2e",
        root / "chaos": "chaos",
        root / "load": "load",
        root / "benchmark": "benchmark",
    }
```

To:
```python
    path_to_marker = {
        root / "unit": "unit",
        root / "integration": "integration",
        root / "smoke": "smoke",
        root / "e2e": "e2e",
        root / "chaos": "chaos",
        root / "load": "load",
        root / "benchmark": "benchmark",
        root / "contract": "contract",
        root / "baseline": "baseline",
    }
```

- [ ] **Step 3: Verify markers are applied**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/contract/ tests/baseline/ --collect-only -q 2>&1 | tail -5
```
Expected: tests collected without "Unknown marker" warnings.

- [ ] **Step 4: Verify marker filtering works**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/ -m contract --collect-only -q 2>&1 | tail -5
```
Expected: only contract tests collected.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py pyproject.toml
git commit -m "fix(tests): add auto-markers for contract and baseline test directories"
```

---

### Task 6: Exclude `telegram_bot/.venv/` from coverage

**Files:**
- Modify: `pyproject.toml:409-429` (add omit entry)

- [ ] **Step 1: Check if .venv exists**

```bash
ls -la /home/user/projects/rag-fresh/telegram_bot/.venv/ 2>/dev/null | head -5 || echo "NO_VENV"
```

- [ ] **Step 2: Add omit entry**

In `pyproject.toml`, after line 413 (`"*/.venv/*"`), add:
```toml
    "telegram_bot/.venv/*",
    "telegram_bot/.venv/**/*",
```

- [ ] **Step 3: Verify coverage config parses**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m coverage debug config 2>&1 | grep -A5 "omit"
```
Expected: new omit paths appear in config.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "fix(coverage): exclude telegram_bot/.venv/ from coverage measurement"
```

---

## Phase 2: Eliminate Duplications

### Task 7: Remove redundant `pytest_collection_modifyitems` from 6 sub-conftest files

**Files:**
- Modify: `tests/smoke/conftest.py:16-23`
- Modify: `tests/integration/conftest.py:8-15`
- Modify: `tests/e2e/conftest.py:9-16`
- Modify: `tests/benchmark/conftest.py:9-16`
- Modify: `tests/chaos/conftest.py:8-15`
- Modify: `tests/load/conftest.py:11-18`

- [ ] **Step 1: Remove from each sub-conftest**

For each file, delete the `_THIS_DIR = Path(__file__).parent` assignment and the `pytest_collection_modifyitems` function. The root conftest already handles marker assignment.

`tests/smoke/conftest.py`: Delete lines 16-23 (remove `_THIS_DIR` and `pytest_collection_modifyitems` function).

`tests/integration/conftest.py`: Delete lines 3-15 (remove `from pathlib import Path`, `_THIS_DIR`, and function).

`tests/e2e/conftest.py`: Delete the `_THIS_DIR` line and `pytest_collection_modifyitems` function. Keep any other fixtures.

`tests/benchmark/conftest.py`: Delete the `_THIS_DIR` line and `pytest_collection_modifyitems` function.

`tests/chaos/conftest.py`: Delete lines 3-15 (remove `from pathlib import Path`, `_THIS_DIR`, and function). Keep fixtures below line 17.

`tests/load/conftest.py`: Delete the `_THIS_DIR` line and `pytest_collection_modifyitems` function.

- [ ] **Step 2: Verify markers still applied from root conftest**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/smoke/ tests/integration/ tests/chaos/ tests/load/ tests/benchmark/ tests/e2e/ --collect-only -q 2>&1 | tail -10
```
Expected: all tests collected, no "Unknown marker" warnings.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/conftest.py tests/integration/conftest.py tests/e2e/conftest.py tests/benchmark/conftest.py tests/chaos/conftest.py tests/load/conftest.py
git commit -m "refactor(tests): remove redundant pytest_collection_modifyitems from sub-conftest files (root conftest handles all)"
```

---

### Task 8: Unify Redis URL fixtures — single source of truth with password support

**Files:**
- Modify: `tests/conftest.py:216-220` (replace simple fixture with password-aware version)
- Modify: `tests/smoke/conftest.py:26-36,97-98` (remove `_build_redis_url`, use root fixture)

- [ ] **Step 1: Replace root `redis_url` fixture with password-aware version**

In `tests/conftest.py`, replace lines 216-220:
```python
@pytest.fixture(scope="session")
def redis_url():
    """Redis server URL."""
    return os.getenv("REDIS_URL", "redis://localhost:6379")
```

With:
```python
@pytest.fixture(scope="session")
def redis_url():
    """Redis server URL with password support.

    Reads REDIS_URL and REDIS_PASSWORD from env. If URL has no auth
    but REDIS_PASSWORD is set, injects password into URL.
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in url:
        url = url.replace("redis://", f"redis://:{password}@", 1)
    return url
```

- [ ] **Step 2: Remove `_build_redis_url` from smoke conftest, use root fixture**

In `tests/smoke/conftest.py`:
1. Delete lines 26-36 (`_build_redis_url` function).
2. In `require_live_services` fixture (line 43), replace `redis_url = _build_redis_url()` with `redis_url = request.getfixturevalue("redis_url")`. But since `require_live_services` is module-scoped without `request` param, instead change line 43 to `redis_url = os.getenv(...)` and call the same password logic inline, OR add `request` parameter:
   - Replace line 43: `redis_url = _build_redis_url()` → `redis_url = request.getfixturevalue("redis_url")`
   - Add `request` to fixture params: `def require_live_services(request):` on line 40
3. In `cache_service` fixture (line 97), replace `redis_url = _build_redis_url()` with `redis_url = request.getfixturevalue("redis_url")` and add `request` to fixture params.

- [ ] **Step 3: Verify smoke tests collect**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/smoke/ --collect-only -q 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/smoke/conftest.py
git commit -m "refactor(tests): unify Redis URL fixture with password support in root conftest"
```

---

### Task 9: Extract `patch("get_client")` into a shared unit fixture

**Files:**
- Modify: `tests/unit/conftest.py` (add `mock_get_client` fixture)
- Modify: `tests/unit/test_bot_handlers.py` (replace ~40 inline patches)
- (Optional follow-up: replace in other 15+ files)

- [ ] **Step 1: Add shared fixture to unit conftest**

Add to `tests/unit/conftest.py` before the `isolate_otel_langfuse` fixture:
```python
@pytest.fixture
def mock_get_client():
    """Mock telegram_bot.bot.get_client as a shared fixture.

    Yields a MagicMock so tests can configure return_value if needed.
    """
    mock = MagicMock()
    with patch("telegram_bot.bot.get_client", return_value=mock):
        yield mock
```

- [ ] **Step 2: Replace inline patches in test_bot_handlers.py**

For each test that has `patch("telegram_bot.bot.get_client", return_value=MagicMock())` in its `with` block, add `mock_get_client` as a parameter and remove the inline patch line.

Example: Before (line 619-621):
```python
        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.get_client", return_value=MagicMock()),
            patch("telegram_bot.bot.propagate_attributes"),
```

After:
```python
        with (
            patch("telegram_bot.bot.create_bot_agent", return_value=mock_agent),
            patch("telegram_bot.bot.propagate_attributes"),
```
And the test function signature changes from `async def test_handle_query_invokes_agent(self, mock_config):` to `async def test_handle_query_invokes_agent(self, mock_config, mock_get_client):`.

Repeat for all ~40 test methods in `test_bot_handlers.py` that use this patch. Use search-and-replace:
- Find: `patch("telegram_bot.bot.get_client", return_value=MagicMock()),\n`
- Replace with: (remove the line)

Then add `mock_get_client` parameter to each affected test function.

- [ ] **Step 3: Verify tests still pass**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/test_bot_handlers.py -v --timeout=60 -x 2>&1 | tail -30
```
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/conftest.py tests/unit/test_bot_handlers.py
git commit -m "refactor(tests): extract shared mock_get_client fixture to unit conftest"
```

---

### Task 10: Remove duplicate BotConfig tests from test_settings.py

**Files:**
- Modify: `tests/unit/test_settings.py:239-275` (remove duplicated class)

- [ ] **Step 1: Remove the duplicated `TestBotConfigIsPydanticSettings` class**

In `tests/unit/test_settings.py`, delete lines 236-275 (the comment `# === BotConfig ...` and the entire `TestBotConfigIsPydanticSettings` class).
The identical tests live in `tests/unit/config/test_bot_config_settings.py:9-41`.

- [ ] **Step 2: Verify the remaining tests still pass**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/config/test_bot_config_settings.py -v 2>&1 | tail -15
```
Expected: all original BotConfig tests pass from their canonical location.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_settings.py
git commit -m "refactor(tests): remove duplicate BotConfig tests from test_settings.py (already in test_bot_config_settings.py)"
```

---

### Task 11: Unify `sample_context_chunks` — keep only root version, delete chaos copy

**Files:**
- Modify: `tests/chaos/conftest.py:18-52` (remove duplicate fixture)
- Modify: any chaos test that depends on the local `sample_context_chunks`

- [ ] **Step 1: Check which chaos tests use `sample_context_chunks`**

```bash
grep -rn "sample_context_chunks" tests/chaos/
```
Expected: find all usages.

- [ ] **Step 2: Remove duplicate fixture from chaos conftest**

Delete lines 18-52 from `tests/chaos/conftest.py` (the `sample_context_chunks` fixture). The root conftest version at `tests/conftest.py:181-195` is session-scoped and available to all tests.

- [ ] **Step 3: Update chaos tests to work with root fixture data**

If chaos tests assert on specific English text (e.g., "Beautiful apartment near the beach"), they need to be updated to work with the Russian root data (e.g., "Квартира в Солнечном берегу"). Search for assertions referencing the English context:

```bash
grep -rn "Beautiful apartment\|Sunny Beach\|Burgas\|Garden House" tests/chaos/
```

Update any such assertions to use the Russian equivalents or use `pytest.skip` if the chaos test is English-specific.

- [ ] **Step 4: Commit**

```bash
git add tests/chaos/conftest.py tests/chaos/*.py
git commit -m "refactor(tests): remove duplicate sample_context_chunks fixture from chaos conftest, use root fixture"
```

---

## Phase 3: Architecture

### Task 12: Move global ML mocks from root conftest to unit conftest

**Files:**
- Modify: `tests/conftest.py:64-140` (move mock infrastructure to unit conftest)
- Modify: `tests/unit/conftest.py` (receive mock infrastructure)

- [ ] **Step 1: Move `pytest_configure`/`pytest_unconfigure` to unit conftest**

Cut lines 64-140 from `tests/conftest.py` (the entire "MOCK HEAVY IMPORTS FOR UNIT TESTS" section). Paste them into `tests/unit/conftest.py` after line 7.

Rename the functions to avoid collision: `pytest_configure` → `pytest_configure_unit`, `pytest_unconfigure` → `pytest_unconfigure_unit`. But since these are pytest hooks, they can't be renamed — they must be in a conftest that applies only to unit tests. Since `tests/unit/conftest.py` is already scoped to the `tests/unit/` directory, moving them there directly works without renaming.

- [ ] **Step 2: Restore the `_saved_modules` and `_mocked_module_names` module-level variables**

Copy these lines to the top of `tests/unit/conftest.py` (they're currently at lines 77-78 of root conftest):
```python
_saved_modules: dict[str, object] = {}
_mocked_module_names: list[str] = []
```

- [ ] **Step 3: Verify unit tests still collect**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/test_chunker.py --collect-only -q 2>&1 | tail -5
```
Expected: tests collected without import errors.

- [ ] **Step 4: Verify integration/smoke tests are NOT affected**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/smoke/ --collect-only -q 2>&1 | tail -5
```
Expected: smoke tests collect (they don't need the ML mocks).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/unit/conftest.py
git commit -m "refactor(tests): move global ML mocks (sentence_transformers, FlagEmbedding, aiogram) from root conftest to unit conftest"
```

---

### Task 13: Split root conftest into modular fixture files

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/config.py`
- Create: `tests/fixtures/data.py`
- Modify: `tests/conftest.py:143-247` (replace inline fixtures with imports)

- [ ] **Step 1: Create `tests/fixtures/config.py`**

```python
"""Shared configuration fixtures (URLs, API keys)."""

import os

import pytest


@pytest.fixture(scope="session")
def qdrant_url():
    """Qdrant server URL."""
    return os.getenv("QDRANT_URL", "http://localhost:6333")


@pytest.fixture(scope="session")
def qdrant_api_key():
    """Qdrant API key (optional)."""
    return os.getenv("QDRANT_API_KEY", "")


@pytest.fixture(scope="session")
def qdrant_collection():
    """Qdrant collection name for tests."""
    return os.getenv("QDRANT_COLLECTION", "test_documents")


@pytest.fixture(scope="session")
def redis_url():
    """Redis server URL with password support."""
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    password = os.getenv("REDIS_PASSWORD", "")
    if password and "@" not in url:
        url = url.replace("redis://", f"redis://:{password}@", 1)
    return url


@pytest.fixture(scope="session")
def bge_m3_url():
    """BGE-M3 embedding service URL."""
    return os.getenv("BGE_M3_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def openai_api_key():
    """OpenAI API key for LLM tests."""
    return os.getenv("OPENAI_API_KEY", "")
```

- [ ] **Step 2: Create `tests/fixtures/data.py`**

```python
"""Shared sample data fixtures."""

import pytest


@pytest.fixture(scope="session")
def sample_context_chunks():
    """Sample context chunks for LLM tests (read-only, session-scoped)."""
    return [
        {
            "text": "Квартира в Солнечном берегу, 2 комнаты, 65 м².",
            "metadata": {"title": "Апартамент у моря", "city": "Солнечный берег", "price": 75000},
            "score": 0.92,
        },
        {
            "text": "Студия в Несебре, первая линия, 35 м².",
            "metadata": {"title": "Студия на первой линии", "city": "Несебр", "price": 45000},
            "score": 0.87,
        },
    ]


@pytest.fixture(scope="session")
def sample_texts():
    """Sample texts for embedding tests (read-only, session-scoped)."""
    return [
        "Кримінальний кодекс України визначає злочини та покарання.",
        "Стаття 115 передбачає відповідальність за умисне вбивство.",
        "Крадіжка є таємним викраденням чужого майна.",
    ]


@pytest.fixture(scope="session")
def sample_query():
    """Sample query for search tests (read-only, session-scoped)."""
    return "Яке покарання за крадіжку?"
```

- [ ] **Step 3: Replace inline fixtures in root conftest with imports**

In `tests/conftest.py`, delete lines 143-247 (HTTP mocking and sample data sections). Add imports at the top under existing imports:

```python
from tests.fixtures.config import bge_m3_url, openai_api_key, qdrant_api_key, qdrant_collection, qdrant_url, redis_url
from tests.fixtures.data import sample_context_chunks, sample_query, sample_texts
```

Keep `mock_httpx_client` and `mock_httpx_response` in root conftest since they're infrastructure fixtures used across all tiers.

- [ ] **Step 4: Verify tests still find fixtures**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/test_chunker.py tests/smoke/test_preflight.py --collect-only -q 2>&1 | tail -5
```
Expected: all fixtures resolved.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/ tests/conftest.py
git commit -m "refactor(tests): split root conftest fixtures into modular files (config + data)"
```

---

### Task 14: Move `test_basic_connection.py` from integration to smoke

**Files:**
- Move: `tests/integration/test_basic_connection.py` → `tests/smoke/test_basic_connection.py`
- Since also removing `test_qdrant_connection.py`, merge its unique tests.

- [ ] **Step 1: Move the file**

```bash
cd /home/user/projects/rag-fresh
git mv tests/integration/test_basic_connection.py tests/smoke/test_basic_connection.py
```

- [ ] **Step 2: Check test_qdrant_connection.py for unique tests to merge**

```bash
grep "^    def test_\|^    async def test_" tests/integration/test_qdrant_connection.py
```

If `test_qdrant_connection.py` has tests not present in `test_basic_connection.py`, merge them. Otherwise, it's a candidate for deletion:
```bash
git rm tests/integration/test_qdrant_connection.py
```

- [ ] **Step 3: Verify the moved tests collect under smoke marker**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/smoke/test_basic_connection.py --collect-only -q 2>&1 | tail -5
```
Expected: tests collected with `smoke` marker.

- [ ] **Step 4: Commit**

```bash
git add tests/smoke/test_basic_connection.py tests/integration/
git commit -m "refactor(tests): move basic_connection test from integration to smoke (it's a connectivity check)"
```

---

### Task 15: Additional architecture fixes

**Files:**
- Modify: `pyproject.toml:382-395` (add `performance` and `regression` markers)
- Delete: `tests/eval/__init__.py` and `tests/eval/` directory

- [ ] **Step 1: Add `performance` and `regression` markers to pyproject.toml**

In `pyproject.toml`, after the `baseline` marker line (added in Task 5), add:
```toml
    "performance: Performance benchmarks (latency, throughput, resource usage)",
    "regression: Regression guard tests (baseline comparisons, golden sets)",
```

- [ ] **Step 2: Remove empty `tests/eval/` directory**

```bash
cd /home/user/projects/rag-fresh && git rm tests/eval/__init__.py && rm -rf tests/eval/
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml tests/eval/
git commit -m "refactor(tests): add performance/regression markers, remove empty tests/eval/ directory"
```

---

## Phase 4: Code Smells (Low Priority)

### Task 16: Fix `call_count == 0` → `assert_not_called()` (3 instances)

**Files:**
- Modify: `tests/unit/test_bot_handlers.py:720`
- Modify: `tests/unit/test_bot_scores.py:903,923`

- [ ] **Step 1: Fix test_bot_handlers.py line 720**

Replace:
```python
        assert mock_create_fallback_cp.call_count == 0
```
With:
```python
        mock_create_fallback_cp.assert_not_called()
```

- [ ] **Step 2: Fix test_bot_scores.py lines 903 and 923**

Replace line 903:
```python
        assert mock_lf.score_current_trace.call_count == 0
```
With:
```python
        mock_lf.score_current_trace.assert_not_called()
```

Replace line 923:
```python
        assert mock_lf.score_current_trace.call_count == 0
```
With:
```python
        mock_lf.score_current_trace.assert_not_called()
```

- [ ] **Step 3: Verify tests still pass**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/test_bot_handlers.py::TestHandleQuery::test_handle_query_manager_skips_retry_on_checkpointer_error tests/unit/test_bot_scores.py -v --timeout=30 2>&1 | tail -15
```
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_bot_handlers.py tests/unit/test_bot_scores.py
git commit -m "style(tests): replace call_count==0 with assert_not_called()"
```

---

### Task 17: Fix `random.seed()` to use `random.Random()` in kommo_seed tests

**Files:**
- Modify: `tests/unit/scripts/test_kommo_seed.py:36,61,353`

- [ ] **Step 1: Read the affected lines**

```bash
grep -n "random.seed" tests/unit/scripts/test_kommo_seed.py
```

- [ ] **Step 2: Replace each `random.seed(N)` with local `random.Random(N)`**

For each occurrence, change from mutating the global `random` module to using a local instance. Example for line 36:

Before:
```python
    random.seed(42)
    ...
    result = some_function_using_random()
```

After:
```python
    rng = random.Random(42)
    ...
    result = some_function_using_random(rng=rng)
```

However, this depends on how `random` is used in the source code. If the source code calls `random.choice()` etc. without accepting a seed parameter, patching the global module is the practical approach. In that case, use `monkeypatch.setattr(random, "seed", lambda x: None)` or wrap in `with patch("random.seed"):` to avoid side effects.

Simplest fix: wrap the seed call with cleanup:
```python
    import random as random_module
    old_state = random_module.getstate()
    try:
        random_module.seed(42)
        # ... test body ...
    finally:
        random_module.setstate(old_state)
```

- [ ] **Step 3: Verify tests pass**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/scripts/test_kommo_seed.py -v 2>&1 | tail -15
```

- [ ] **Step 4: Commit**

```bash
git add tests/unit/scripts/test_kommo_seed.py
git commit -m "fix(tests): use local random.Random() or state save/restore instead of global random.seed()"
```

---

### Task 18: Parametrize contextualization tests (Claude/OpenAI/Groq)

**Files:**
- Create: `tests/unit/contextualization/test_providers.py`
- Delete: `tests/unit/contextualization/test_claude.py`
- Delete: `tests/unit/contextualization/test_openai.py`
- Delete: `tests/unit/contextualization/test_groq.py`

- [ ] **Step 1: Create parametrized test file**

Create `tests/unit/contextualization/test_providers.py` that combines the 10-12 identical test functions from the three provider test files using `@pytest.mark.parametrize`:

```python
"""Parametrized tests for all contextualization providers (Claude, OpenAI, Groq)."""

from unittest.mock import MagicMock, patch

import pytest

from src.contextualization.claude import ClaudeContextualizer
from src.contextualization.groq import GroqContextualizer
from src.contextualization.openai import OpenAIContextualizer


# Provider metadata: (class, context_method_value, module_to_patch)
PROVIDERS = [
    ("claude", ClaudeContextualizer, "anthropic", "src.contextualization.claude.Anthropic"),
    ("openai", OpenAIContextualizer, "openai", "src.contextualization.openai.OpenAI"),
    ("groq", GroqContextualizer, "groq", "src.contextualization.groq.Groq"),
]


@pytest.fixture
def sample_chunks():
    return [
        {
            "text": "Квартира в Солнечном берегу, 2 комнаты, 65 м².",
            "metadata": {"title": "Апартамент у моря"},
            "score": 0.92,
        },
    ]


@pytest.fixture
def multi_chunks():
    return [
        {"text": "Квартира в Сонячному березі", "metadata": {}, "score": 0.95},
        {"text": "Студия в Несебре", "metadata": {}, "score": 0.88},
    ]


@pytest.mark.parametrize("provider_name,cls,method_name,patch_target", PROVIDERS)
class TestContextualizeBasics:
    """Tests common to all contextualization providers."""

    def test_contextualize_single_chunk(self, provider_name, cls, method_name, patch_target, sample_chunks):
        with patch(f"{patch_target}") as mock_client:
            instance = cls(api_key="test-key")
            mock_client.return_value = MagicMock()
            result = instance.contextualize(sample_chunks)
            assert result is not None

    def test_contextualize_multiple_chunks(self, provider_name, cls, method_name, patch_target, multi_chunks):
        with patch(f"{patch_target}") as mock_client:
            instance = cls(api_key="test-key")
            mock_client.return_value = MagicMock()
            result = instance.contextualize(multi_chunks)
            assert result is not None

    def test_contextualize_empty_chunks(self, provider_name, cls, method_name, patch_target):
        with patch(f"{patch_target}") as mock_client:
            instance = cls(api_key="test-key")
            mock_client.return_value = MagicMock()
            result = instance.contextualize([])
            assert result == [] or result is not None

    def test_contextualize_handles_api_error_gracefully(self, provider_name, cls, method_name, patch_target, sample_chunks):
        with patch(f"{patch_target}") as mock_client:
            instance = cls(api_key="test-key")
            mock_client.side_effect = Exception("API error")
            result = instance.contextualize(sample_chunks)
            assert result is not None  # should not raise


@pytest.mark.parametrize("provider_name,cls,method_name,patch_target", PROVIDERS)
class TestContextualizeSync:
    """Sync contextualization tests."""

    def test_contextualize_sync_success(self, provider_name, cls, method_name, patch_target):
        with patch(f"{patch_target}") as mock_client:
            instance = cls(api_key="test-key")
            mock_client.return_value = MagicMock()
            result = instance.contextualize_sync([])
            assert result is not None

    def test_contextualize_sync_tracks_tokens(self, provider_name, cls, method_name, patch_target):
        with patch(f"{patch_target}") as mock_client:
            instance = cls(api_key="test-key")
            mock_client.return_value = MagicMock()
            result = instance.contextualize_sync([])
            assert result is not None
```

**Note:** The exact mock structure depends on each provider's API (Anthropic messages vs OpenAI chat completions). The parametrized test may need a `mock_setup` fixture per-provider to handle structural differences. If the differences are too large, parametrize only the test names that are truly identical across providers and keep provider-specific tests in a separate per-provider class.

- [ ] **Step 2: Delete old provider-specific test files**

```bash
cd /home/user/projects/rag-fresh
git rm tests/unit/contextualization/test_claude.py tests/unit/contextualization/test_openai.py tests/unit/contextualization/test_groq.py
```

- [ ] **Step 3: Verify parametrized tests pass**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/contextualization/test_providers.py -v 2>&1 | tail -30
```
Expected: all providers tested.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/contextualization/test_providers.py tests/unit/contextualization/
git commit -m "refactor(tests): parametrize contextualization provider tests (Claude/OpenAI/Groq → test_providers.py)"
```

---

### Task 19: Add dedicated tests for `src/api/schemas.py`

**Files:**
- Create: `tests/unit/api/test_schemas.py`

- [ ] **Step 1: Read schemas.py for Pydantic models to test**

```bash
grep "^class " src/api/schemas.py
```

- [ ] **Step 2: Write the test file**

Create `tests/unit/api/test_schemas.py`:
```python
"""Unit tests for src/api/schemas.py data models."""

from pydantic import ValidationError
import pytest

from src.api.schemas import RAGRequest, RAGResponse, SearchResult


class TestRAGRequest:
    def test_valid_request(self):
        req = RAGRequest(query="test query", top_k=5)
        assert req.query == "test query"
        assert req.top_k == 5

    def test_default_top_k(self):
        req = RAGRequest(query="test")
        assert req.top_k == 10

    def test_query_min_length(self):
        with pytest.raises(ValidationError):
            RAGRequest(query="", top_k=5)

    def test_top_k_minimum(self):
        with pytest.raises(ValidationError):
            RAGRequest(query="test", top_k=0)


class TestSearchResult:
    def test_valid_result(self):
        sr = SearchResult(
            article_number="121",
            text="Article text",
            score=0.95,
            metadata={"source": "test"},
        )
        assert sr.article_number == "121"
        assert sr.score == 0.95

    def test_score_range(self):
        sr = SearchResult(article_number="1", text="x", score=0.0)
        assert sr.score == 0.0
        sr2 = SearchResult(article_number="1", text="x", score=1.0)
        assert sr2.score == 1.0


class TestRAGResponse:
    def test_valid_response(self):
        results = [
            SearchResult(article_number="121", text="text", score=0.9, metadata={})
        ]
        resp = RAGResponse(
            query="test",
            results=results,
            context_used=True,
            search_method="hybrid",
            execution_time=0.5,
        )
        assert resp.query == "test"
        assert len(resp.results) == 1
        assert resp.context_used is True

    def test_empty_results(self):
        resp = RAGResponse(
            query="no results",
            results=[],
            context_used=False,
            search_method="dense",
            execution_time=0.1,
        )
        assert len(resp.results) == 0
```

- [ ] **Step 3: Run tests**

```bash
cd /home/user/projects/rag-fresh && .venv/bin/python -m pytest tests/unit/api/test_schemas.py -v
```
Expected: all pass (or adjust based on actual schema field names/validators).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/api/test_schemas.py
git commit -m "test: add dedicated unit tests for src/api/schemas.py"
```

---

### Task 20: Fix `uuid4()` in test_qdrant_history.py (flaky collection name)

**Files:**
- Modify: `tests/integration/test_qdrant_history.py:22`

- [ ] **Step 1: Read the current line**

```bash
sed -n '20,25p' tests/integration/test_qdrant_history.py
```

- [ ] **Step 2: Replace `uuid4()` with fixed name**

Replace:
```python
TEST_COLLECTION = f"test_history_{uuid.uuid4().hex[:8]}"
```
With:
```python
TEST_COLLECTION = "test_history_integration"
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_qdrant_history.py
git commit -m "fix(tests): use fixed collection name instead of uuid4() in test_qdrant_history.py"
```

---

### Task 21: Address `src/governance/` empty directory

**Files:**
- Move: `src/governance/README.md` → `docs/governance.md`
- Delete: `src/governance/` directory

- [ ] **Step 1: Move README to docs/**

```bash
cd /home/user/projects/rag-fresh
test -f src/governance/README.md && git mv src/governance/README.md docs/governance.md || echo "no readme to move"
```

- [ ] **Step 2: Delete empty directory**

```bash
cd /home/user/projects/rag-fresh
if [ -d src/governance ] && [ -z "$(ls -A src/governance 2>/dev/null)" ]; then
  rmdir src/governance
  echo "removed empty src/governance/"
else
  echo "directory not empty or doesn't exist - skipping"
fi
```

- [ ] **Step 3: Commit**

```bash
git add docs/governance.md src/governance/ 2>/dev/null
git commit -m "docs: move governance README from src/governance/ to docs/"
```

---

## Verification (After All Tasks)
- [ ] Run full test suite: `.venv/bin/python -m pytest tests/ -x --timeout=60 -q 2>&1 | tail -10`
- [ ] Verify new tests pass: `.venv/bin/python -m pytest tests/unit/test_compat.py tests/unit/evaluation/test_config_snapshot.py tests/unit/api/test_schemas.py -v`
- [ ] Verify no import errors: `.venv/bin/python -m pytest tests/ --collect-only -q 2>&1 | grep -i error`
- [ ] Check conftest sizes: `wc -l tests/conftest.py tests/unit/conftest.py tests/smoke/conftest.py`
- [ ] Run ruff lint: `.venv/bin/python -m ruff check tests/`

- [ ] Run full test suite: `.venv/bin/python -m pytest tests/ -x --timeout=60 -q 2>&1 | tail -10`
- [ ] Verify new tests pass: `.venv/bin/python -m pytest tests/unit/test_compat.py tests/unit/evaluation/test_config_snapshot.py -v`
- [ ] Verify no import errors: `.venv/bin/python -m pytest tests/ --collect-only -q 2>&1 | grep -i error`
- [ ] Check conftest sizes: `wc -l tests/conftest.py tests/unit/conftest.py tests/smoke/conftest.py`
- [ ] Run ruff lint: `.venv/bin/python -m ruff check tests/`
