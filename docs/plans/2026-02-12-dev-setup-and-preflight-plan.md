# Dev Setup & Preflight Guards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `make install-dev` so it actually installs dev dependencies (#169), and add dirty-worktree preflight guard to verification scripts (#165).

**Architecture:** Two independent fixes: (1) Migrate dev extras from `[project.optional-dependencies]` to `[dependency-groups]` (PEP 735) so `uv sync` installs them by default. (2) Add `git diff --quiet` preflight check in `validate_traces.py` and baseline CLI.

**Tech Stack:** uv (PEP 735 dependency-groups), Python 3.12, git subprocess

---

## Task 1: Migrate dev deps to `[dependency-groups]` (#169)

**Files:**
- Modify: `pyproject.toml:53-70` (move extras → dependency-groups)
- Modify: `Makefile:33-46` (update install targets)
- Modify: `.github/workflows/ci.yml:26,53,85` (remove `--extra dev`)

**Step 1: Update `pyproject.toml` — add `[dependency-groups]` section**

Move `[project.optional-dependencies].dev` contents to new `[dependency-groups]` section:

```toml
# REMOVE this block:
# [project.optional-dependencies]
# dev = [ ... ]

# ADD new section (after [project.optional-dependencies]):
[dependency-groups]
dev = [
    "ruff>=0.6.0",
    "mypy>=1.11.0",
    "pylint>=3.2.0",
    "bandit>=1.7.9",
    "vulture>=2.11",
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
    "pytest-asyncio>=1.2.0",
    "pytest-httpx>=0.35.0",
    "pytest-timeout>=2.4.0",
    "pytest-xdist>=3.8.0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.39.0",
    "pre-commit>=3.8.0",
    "telethon>=1.42.0",
]
```

Оставить `[project.optional-dependencies]` только для `docs`, `voice`, `e2e` и других published extras.

**Step 2: Update Makefile install targets**

```makefile
install: ## Install production dependencies
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	uv sync --no-dev
	@echo "$(GREEN)✓ Production dependencies installed$(NC)"

install-dev: ## Install development dependencies (linters, formatters, etc.)
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	uv sync
	@echo "$(GREEN)✓ Development dependencies installed$(NC)"

install-all: ## Install all dependencies (prod + dev + docs + voice)
	@echo "$(BLUE)Installing all dependencies...$(NC)"
	uv sync --all-extras --all-groups
	@echo "$(GREEN)✓ All dependencies installed$(NC)"
```

**Step 3: Update CI — remove `--extra dev`**

В `.github/workflows/ci.yml` заменить все `uv sync --frozen --extra dev` на `uv sync --frozen`:

```yaml
# lines 26, 53, 85
- name: Install dependencies
  run: uv sync --frozen
```

`uv sync` теперь автоматически включает `[dependency-groups].dev`.

**Step 4: Regenerate lockfile**

Run: `uv lock`

**Step 5: Verify**

```bash
# Удалить .venv и пересоздать
rm -rf .venv
uv sync
# Проверить что pytest доступен
uv run pytest --version
uv run ruff --version
uv run mypy --version
```

Expected: все три команды выводят версию без ошибок.

**Step 6: Run tests**

Run: `uv run pytest tests/unit/ -x -q --timeout=30`
Expected: PASS

**Step 7: Commit**

```bash
git add pyproject.toml uv.lock Makefile .github/workflows/ci.yml
git commit -m "fix(build): migrate dev deps to [dependency-groups] (PEP 735) #169"
```

---

## Task 2: Add dirty-worktree preflight guard (#165)

**Files:**
- Modify: `scripts/validate_traces.py:1085-1093` (add preflight in `run_validation`)
- Modify: `tests/baseline/cli.py` (add preflight in compare command)
- Create: `tests/unit/test_preflight_worktree.py`

**Step 1: Write failing test**

```python
# tests/unit/test_preflight_worktree.py
"""Tests for dirty-worktree preflight guard."""
from unittest.mock import patch

import pytest


def test_clean_worktree_passes(tmp_path):
    """Clean worktree should not raise."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        # Should not raise
        check_worktree_clean(strict=True)


def test_dirty_worktree_strict_fails(tmp_path):
    """Dirty worktree in strict mode should exit."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        with pytest.raises(SystemExit):
            check_worktree_clean(strict=True)


def test_dirty_worktree_warn_only(tmp_path, caplog):
    """Dirty worktree in warn mode should log warning but not exit."""
    from scripts.validate_traces import check_worktree_clean

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        check_worktree_clean(strict=False)
        assert "dirty worktree" in caplog.text.lower() or "uncommitted" in caplog.text.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_preflight_worktree.py -v`
Expected: FAIL — `ImportError: cannot import name 'check_worktree_clean'`

**Step 3: Implement `check_worktree_clean` in validate_traces.py**

Add after `check_langfuse_config()` (line ~150):

```python
def check_worktree_clean(strict: bool = False) -> None:
    """Preflight: warn or fail if git worktree has uncommitted changes.

    Args:
        strict: If True, exit on dirty worktree. If False, log warning only.
    """
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD"],
        capture_output=True,
    )
    if result.returncode != 0:
        msg = (
            "Dirty worktree detected — uncommitted changes may cause "
            "false positives in validation results"
        )
        if strict:
            logger.error(msg)
            sys.exit(1)
        else:
            logger.warning(msg)
```

**Step 4: Wire into `run_validation`**

In `run_validation()` (line ~1093), add after `check_langfuse_config()`:

```python
check_worktree_clean(strict=args.strict_worktree)
```

Add CLI arg in `main()`:

```python
parser.add_argument(
    "--strict-worktree",
    action="store_true",
    default=False,
    help="Fail if git worktree is dirty (default: warn only)",
)
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_preflight_worktree.py -v`
Expected: PASS (3 tests)

**Step 6: Add preflight to baseline CLI**

In `tests/baseline/cli.py`, add same check before `compare` command:

```python
from scripts.validate_traces import check_worktree_clean

# In compare() function, before running comparison:
check_worktree_clean(strict=False)
```

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/ -x -q --timeout=30`
Expected: PASS

**Step 8: Run lint + types**

Run: `make check`
Expected: PASS

**Step 9: Commit**

```bash
git add scripts/validate_traces.py tests/baseline/cli.py tests/unit/test_preflight_worktree.py
git commit -m "fix(validation): add dirty-worktree preflight guard #165"
```

---

## Task 3: Update issues with acceptance criteria

**Step 1: Update #169 with verification commands**

```bash
gh issue comment 169 --body "## Acceptance Criteria
- [ ] \`rm -rf .venv && uv sync && uv run pytest --version\` — exits 0
- [ ] \`uv sync --no-dev && uv run pytest --version\` — exits 1 (not installed)
- [ ] CI lint/test jobs pass with \`uv sync --frozen\` (no \`--extra dev\`)
- [ ] \`[dependency-groups].dev\` section exists in pyproject.toml
- [ ] \`[project.optional-dependencies].dev\` removed

**Решение:** миграция в \`[dependency-groups]\` (PEP 735), не hotfix \`--extra dev\`"
```

**Step 2: Update #165 with verification commands**

```bash
gh issue comment 165 --body "## Acceptance Criteria
- [ ] \`uv run python scripts/validate_traces.py --help\` shows \`--strict-worktree\` flag
- [ ] Dirty worktree + default run → WARNING in logs, validation continues
- [ ] Dirty worktree + \`--strict-worktree\` → exit 1 before any queries
- [ ] Clean worktree → no warning
- [ ] \`tests/unit/test_preflight_worktree.py\` — 3 tests PASS"
```

**Step 3: Commit (no code changes — just issue updates)**

No commit needed.
