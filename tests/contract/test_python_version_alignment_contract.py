# tests/contract/test_python_version_alignment_contract.py
"""Contract: a single canonical Python version (3.12) is declared everywhere.

Closes #1945.

Problem: the codebase referenced multiple Python version strings across
pyproject.toml, CI workflows, pre-commit, and the Makefile.  When they
diverge, tools (ruff, mypy, pylint) disagree on which syntax features are
legal, causing false-positive or false-negative lint results.

This contract ensures all version pins converge on the canonical floor of
Python 3.12.

Note: Docker runtime images (Dockerfile.ingestion, services/bge-m3-api, etc.)
intentionally use newer Python versions (3.13/3.14) for runtime performance.
They are excluded from this contract's scope, which covers only source-level
config artifacts (pyproject.toml, CI workflows, pre-commit, Makefile).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

PYPROJECT = REPO_ROOT / "pyproject.toml"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
NIGHTLY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly-heavy.yml"
MAKEFILE = REPO_ROOT / "Makefile"
SEARCH_ENGINE_SHARED = REPO_ROOT / "src" / "retrieval" / "search_engine_shared.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------
# pyproject.toml checks
# ------------------------------------------------------------------


def test_requires_python_is_312() -> None:
    """pyproject.toml must declare requires-python = '>=3.12'."""
    src = _read(PYPROJECT)
    m = re.search(r'requires-python\s*=\s*"([^"]+)"', src)
    assert m is not None, "requires-python not found in pyproject.toml"
    assert m.group(1) == ">=3.12", (
        f"requires-python must be '>=3.12', got {m.group(1)!r}"
    )


def test_ruff_target_version_is_py312() -> None:
    """[tool.ruff] target-version must be 'py312'.

    Note: this regex matches the first occurrence of target-version in
    pyproject.toml, which is the top-level [tool.ruff] key.  If a second
    target-version appears (e.g. in [tool.ruff.format]), this test would
    need updating to use tomllib for section-aware parsing.
    """
    src = _read(PYPROJECT)
    m = re.search(r'target-version\s*=\s*"([^"]+)"', src)
    assert m is not None, "target-version not found in pyproject.toml [tool.ruff]"
    assert m.group(1) == "py312", (
        f"ruff target-version must be 'py312', got {m.group(1)!r}"
    )


def test_mypy_python_version_is_312() -> None:
    """[tool.mypy] python_version must be '3.12'."""
    src = _read(PYPROJECT)
    m = re.search(r'python_version\s*=\s*"([^"]+)"', src)
    assert m is not None, "python_version not found in pyproject.toml [tool.mypy]"
    assert m.group(1) == "3.12", (
        f"mypy python_version must be '3.12', got {m.group(1)!r}"
    )


def test_pylint_py_version_is_312() -> None:
    """[tool.pylint.main] py-version must be '3.12'."""
    src = _read(PYPROJECT)
    m = re.search(r'py-version\s*=\s*"([^"]+)"', src)
    assert m is not None, "py-version not found in pyproject.toml [tool.pylint.main]"
    assert m.group(1) == "3.12", (
        f"pylint py-version must be '3.12', got {m.group(1)!r}"
    )


# ------------------------------------------------------------------
# .pre-commit-config.yaml
# ------------------------------------------------------------------


def test_pre_commit_default_language_version_is_312() -> None:
    """.pre-commit-config.yaml default_language_version must use python3.12."""
    src = _read(PRE_COMMIT)
    m = re.search(r"python:\s*(python[\d.]+)", src)
    assert m is not None, (
        "default_language_version python entry not found in .pre-commit-config.yaml"
    )
    assert m.group(1) == "python3.12", (
        f"pre-commit python must be 'python3.12', got {m.group(1)!r}"
    )


# ------------------------------------------------------------------
# CI workflows
# ------------------------------------------------------------------


def test_ci_ruff_format_target_version_is_py312() -> None:
    """ci.yml ruff format must use --target-version py312."""
    src = _read(CI_WORKFLOW)
    m = re.search(r"--target-version\s+(py\d+)", src)
    assert m is not None, "--target-version not found in ci.yml"
    assert m.group(1) == "py312", (
        f"ci.yml ruff format --target-version must be 'py312', got {m.group(1)!r}"
    )


def test_nightly_heavy_python_install_is_312() -> None:
    """nightly-heavy.yml must install Python 3.12 via uv."""
    src = _read(NIGHTLY_WORKFLOW)
    m = re.search(r"uv python install\s+([\d.]+)", src)
    assert m is not None, "uv python install not found in nightly-heavy.yml"
    assert m.group(1) == "3.12", (
        f"nightly-heavy.yml must install '3.12', got {m.group(1)!r}"
    )


# ------------------------------------------------------------------
# Makefile
# ------------------------------------------------------------------


def test_makefile_python_version_is_312() -> None:
    """Makefile PYTHON_VERSION must default to 3.12."""
    src = _read(MAKEFILE)
    m = re.search(r"PYTHON_VERSION\s*\?=\s*(\S+)", src)
    assert m is not None, "PYTHON_VERSION not found in Makefile"
    assert m.group(1) == "3.12", (
        f"Makefile PYTHON_VERSION must be '3.12', got {m.group(1)!r}"
    )


# ------------------------------------------------------------------
# PEP-695 syntax validation
# ------------------------------------------------------------------


def test_search_engine_shared_parses_without_syntax_error() -> None:
    """src/retrieval/search_engine_shared.py must parse on the running Python.

    This file uses PEP-695 generic function syntax (Python 3.12+), i.e.
    ``def f[T](...)``, which would cause a SyntaxError on Python 3.11.
    Parsing it here proves the version floor is sufficient and that static
    analysis tools (vulture, bandit) will not choke on it.
    """
    source = _read(SEARCH_ENGINE_SHARED)
    try:
        ast.parse(source, filename=str(SEARCH_ENGINE_SHARED))
    except SyntaxError as exc:
        raise AssertionError(
            f"search_engine_shared.py has a SyntaxError: {exc}"
        ) from exc
