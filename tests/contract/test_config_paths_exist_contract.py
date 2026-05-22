"""Contract: every path referenced in tool configs must exist (#1947).

Linter, formatter, and test-runner configs in ``pyproject.toml`` and
``.pre-commit-config.yaml`` reference filesystem paths (directories,
glob prefixes). When those paths are removed from the repo but the
config entries linger, the rules become dead weight and mislead
contributors into thinking the code still exists.

This contract parses the relevant config sections and verifies that
each referenced path resolves to an existing location in the repo.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

# Directories that are virtual or environment-specific and should not
# be validated against the filesystem.
VIRTUAL_DIRS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        "__pypackages__",
        ".git",
        ".git-rewrite",
        "node_modules",
        "build",
        "dist",
        "site-packages",
        "_build",
        "buck-out",
        ".bzr",
        ".direnv",
        ".eggs",
        ".hg",
        ".ipynb_checkpoints",
        ".mypy_cache",
        ".nox",
        ".pants.d",
        ".pyenv",
        ".pytest_cache",
        ".pytype",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".vscode",
    }
)

# Pre-commit exclude patterns to skip (maintained elsewhere or intentionally
# referencing non-existent paths for future use).
SKIP_PRE_COMMIT_EXCLUDES: frozenset[str] = frozenset({"scripts/archive"})


def _load_pyproject() -> dict:
    """Load and parse pyproject.toml from repo root."""
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def _load_pre_commit() -> dict:
    """Load and parse .pre-commit-config.yaml from repo root."""
    with open(REPO_ROOT / ".pre-commit-config.yaml") as f:
        return yaml.safe_load(f)


def _dir_from_glob(glob_key: str) -> str | None:
    """Extract the leading directory component from a glob/path key.

    Examples:
        "legacy/*.py"  -> "legacy"
        "__init__.py"  -> None (no directory component)
        "tests/**/*.py" -> "tests"
        "*.py"         -> None
    """
    # Strip leading quotes if present
    key = glob_key.strip('"').strip("'")
    parts = Path(key).parts
    if len(parts) <= 1:
        return None
    return parts[0]


def _is_virtual(name: str) -> bool:
    """Return True if the name is a known virtual/environment directory."""
    return name in VIRTUAL_DIRS


def _dir_exists_anywhere(name: str) -> bool:
    """Return True if a directory with this name exists anywhere in the repo.

    Tools like ruff, bandit, and pylint may match directory names at any
    depth. A reference to "evaluation" is valid if src/evaluation/ exists,
    even though there is no top-level evaluation/ directory.
    """
    for path in REPO_ROOT.rglob(name):
        if path.is_dir() and ".venv" not in path.parts and ".git" not in path.parts:
            return True
    return False


# =============================================================================
# Collect dead path references from pyproject.toml
# =============================================================================


def _collect_ruff_per_file_ignores(pyproject: dict) -> list[tuple[str, str]]:
    """Collect directory references from [tool.ruff.lint.per-file-ignores]."""
    results = []
    per_file = pyproject.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
    for key in per_file:
        dirname = _dir_from_glob(key)
        if dirname and not _is_virtual(dirname):
            results.append((f"[tool.ruff.lint.per-file-ignores] key: {key}", dirname))
    return results


def _collect_bandit_exclude_dirs(pyproject: dict) -> list[tuple[str, str]]:
    """Collect directory references from [tool.bandit].exclude_dirs."""
    results = []
    exclude_dirs = pyproject.get("tool", {}).get("bandit", {}).get("exclude_dirs", [])
    for entry in exclude_dirs:
        if not _is_virtual(entry):
            results.append((f"[tool.bandit] exclude_dirs: {entry}", entry))
    return results


def _collect_pylint_ignore(pyproject: dict) -> list[tuple[str, str]]:
    """Collect directory references from [tool.pylint.main].ignore."""
    results = []
    ignore = pyproject.get("tool", {}).get("pylint", {}).get("main", {}).get("ignore", [])
    for entry in ignore:
        if not _is_virtual(entry):
            results.append((f"[tool.pylint.main] ignore: {entry}", entry))
    return results


def _collect_pytest_norecursedirs(pyproject: dict) -> list[tuple[str, str]]:
    """Collect path references from [tool.pytest.ini_options].norecursedirs."""
    results = []
    norecursedirs = (
        pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("norecursedirs", [])
    )
    for entry in norecursedirs:
        # norecursedirs entries are paths relative to repo root
        results.append((f"[tool.pytest.ini_options] norecursedirs: {entry}", entry))
    return results


def _collect_pre_commit_excludes(pre_commit: dict) -> list[tuple[str, str]]:
    """Collect directory references from pre-commit hook exclude patterns.

    Looks for exclude values starting with ^ and extracts the directory
    prefix (e.g., "^legacy/" -> "legacy").
    """
    results = []
    for repo in pre_commit.get("repos", []):
        for hook in repo.get("hooks", []):
            exclude = hook.get("exclude", "")
            if isinstance(exclude, str) and exclude.startswith("^"):
                # Extract directory prefix: ^legacy/ -> legacy
                match = re.match(r"^\^([a-zA-Z0-9_\-./]+?)/?$", exclude)
                if match:
                    dirname = match.group(1).rstrip("/")
                    if not _is_virtual(dirname) and dirname not in SKIP_PRE_COMMIT_EXCLUDES:
                        hook_id = hook.get("id", "unknown")
                        results.append(
                            (
                                f".pre-commit-config.yaml hook '{hook_id}' exclude: {exclude}",
                                dirname,
                            )
                        )
    return results


# =============================================================================
# Build parametrized test cases
# =============================================================================


def _collect_all_path_references() -> list[tuple[str, str]]:
    """Collect all path references from config files."""
    pyproject = _load_pyproject()
    pre_commit = _load_pre_commit()

    refs: list[tuple[str, str]] = []
    refs.extend(_collect_ruff_per_file_ignores(pyproject))
    refs.extend(_collect_bandit_exclude_dirs(pyproject))
    refs.extend(_collect_pylint_ignore(pyproject))
    refs.extend(_collect_pytest_norecursedirs(pyproject))
    refs.extend(_collect_pre_commit_excludes(pre_commit))
    return refs


ALL_PATH_REFS = _collect_all_path_references()


@pytest.mark.contract
@pytest.mark.parametrize(
    ("source", "path_ref"),
    ALL_PATH_REFS,
    ids=[f"{src} -> {p}" for src, p in ALL_PATH_REFS],
)
def test_config_path_exists(source: str, path_ref: str) -> None:
    """Every path referenced in tool configuration must exist on disk.

    Dead path references in linter/formatter/test configs are confusing
    and indicate stale configuration that should be pruned (#1947).
    """
    target = REPO_ROOT / path_ref
    # Check exact path first.
    if target.exists():
        return
    # For single-component paths (e.g. "legacy", "evaluation"), check if
    # the directory name exists anywhere in the repo. Tools like ruff,
    # bandit, and pylint can match directory names at any depth.
    parts = Path(path_ref).parts
    if len(parts) == 1 and _dir_exists_anywhere(parts[0]):
        return
    raise AssertionError(
        f"Dead path reference in {source}: '{path_ref}' does not exist "
        f"at {target.relative_to(REPO_ROOT)}. Remove or update the config "
        f"entry to reference an existing path (#1947)."
    )
