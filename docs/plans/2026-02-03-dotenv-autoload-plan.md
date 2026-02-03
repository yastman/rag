# Dotenv Autoload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `uv run python -m src.ingestion.gdrive_flow --once` auto-load `.env` without requiring `source .env` or exports.

**Architecture:** Add `load_dotenv()` call at the start of `main()` entrypoint before config initialization. This is the minimal change that works across all environments.

**Tech Stack:** python-dotenv (already installed), pytest, monkeypatch

---

## Task 1: Write failing test for dotenv loading

**Files:**
- Create: `tests/unit/ingestion/test_gdrive_flow_dotenv.py`

**Step 1: Create test file with first test**

```python
"""Test .env loading for gdrive_flow entrypoint."""

import os
from pathlib import Path


class TestDotenvLoading:
    """Test that .env variables are loaded before config initialization."""

    def test_voyage_api_key_loaded_from_dotenv(self, tmp_path: Path, monkeypatch):
        """Config should see VOYAGE_API_KEY from .env file when env var not set."""
        # Arrange: create .env file
        env_file = tmp_path / ".env"
        env_file.write_text("VOYAGE_API_KEY=test-key-from-dotenv\n")

        # Clear any existing env var
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

        # Act: load dotenv and create config
        from dotenv import load_dotenv

        load_dotenv(env_file, override=True)

        # Import AFTER load_dotenv to get fresh defaults
        # Force reimport to pick up new env
        import importlib
        import src.ingestion.gdrive_flow as gf

        importlib.reload(gf)
        config = gf.GDriveFlowConfig()

        # Assert
        assert config.voyage_api_key == "test-key-from-dotenv"
```

**Step 2: Run test to verify it passes (this tests the mechanism, not the fix)**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_flow_dotenv.py::TestDotenvLoading::test_voyage_api_key_loaded_from_dotenv -v`

Expected: PASS (this validates that dotenv mechanism works)

**Step 3: Commit test file**

```bash
git add tests/unit/ingestion/test_gdrive_flow_dotenv.py
git commit -m "test(ingestion): add dotenv loading test for gdrive_flow"
```

---

## Task 2: Add second test for env var precedence

**Files:**
- Modify: `tests/unit/ingestion/test_gdrive_flow_dotenv.py`

**Step 1: Add precedence test to the class**

Add this test method after the first one:

```python
    def test_explicit_env_var_takes_precedence(self, tmp_path: Path, monkeypatch):
        """Explicit env var should override .env file value."""
        # Arrange: .env has one value
        env_file = tmp_path / ".env"
        env_file.write_text("VOYAGE_API_KEY=from-dotenv-file\n")

        # Set explicit env var (should take precedence)
        monkeypatch.setenv("VOYAGE_API_KEY", "from-explicit-export")

        # Act: load dotenv WITHOUT override (default behavior)
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)

        import importlib
        import src.ingestion.gdrive_flow as gf

        importlib.reload(gf)
        config = gf.GDriveFlowConfig()

        # Assert: explicit env var wins
        assert config.voyage_api_key == "from-explicit-export"
```

**Step 2: Run both tests**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_flow_dotenv.py -v`

Expected: 2 passed

**Step 3: Commit**

```bash
git add tests/unit/ingestion/test_gdrive_flow_dotenv.py
git commit -m "test(ingestion): add env var precedence test"
```

---

## Task 3: Add load_dotenv() to gdrive_flow entrypoint

**Files:**
- Modify: `src/ingestion/gdrive_flow.py:339-345`

**Step 1: Read current main() function**

Current code at line 339:
```python
def main():
    """CLI entry point."""
    import argparse

    logging.basicConfig(
```

**Step 2: Add load_dotenv() at the start of main()**

Replace lines 339-345 with:

```python
def main():
    """CLI entry point."""
    from dotenv import load_dotenv

    load_dotenv()  # Load .env before config initialization

    import argparse

    logging.basicConfig(
```

**Step 3: Run existing tests to verify no regression**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_flow.py -v`

Expected: All tests PASS

**Step 4: Run new dotenv tests**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_flow_dotenv.py -v`

Expected: 2 passed

**Step 5: Commit**

```bash
git add src/ingestion/gdrive_flow.py
git commit -m "feat(ingestion): auto-load .env in gdrive_flow entrypoint

Fixes pipeline failing with 'VOYAGE_API_KEY not set' when run from
cron, systemd, or clean shell without sourcing .env first."
```

---

## Task 4: Verify full test suite

**Files:** None (verification only)

**Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v --tb=short`

Expected: All tests PASS

**Step 2: Run linting**

Run: `make check`

Expected: No errors

**Step 3: Test CLI manually (optional integration check)**

Run: `uv run python -m src.ingestion.gdrive_flow --help`

Expected: Shows help without errors

---

## Task 5: Final verification and summary

**Files:** None

**Step 1: Verify the fix works in clean environment**

```bash
# Unset any existing env var
unset VOYAGE_API_KEY

# Run the flow (should load from .env)
uv run python -m src.ingestion.gdrive_flow --once --sync-dir /tmp/empty-test-dir 2>&1 | head -5
```

Expected: Either processes files or shows "No files to process" (not "VOYAGE_API_KEY not set")

**Step 2: Summary of changes**

| File | Lines Changed | Description |
|------|---------------|-------------|
| `src/ingestion/gdrive_flow.py` | +4 | load_dotenv() in main() |
| `tests/unit/ingestion/test_gdrive_flow_dotenv.py` | +45 (new) | 2 tests for dotenv loading |

---

## Rollback

If issues arise:

```bash
git revert HEAD  # Revert the feat commit
git revert HEAD  # Revert the test commits
```

Or simply remove the 4 added lines from `main()`.
