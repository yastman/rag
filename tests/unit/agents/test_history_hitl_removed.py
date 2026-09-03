# tests/unit/agents/test_history_hitl_removed.py
"""Regression locks: the dormant LangGraph history/HITL island stays deleted (#3211).

``telegram_bot/agents/history_graph/**`` and ``telegram_bot/agents/hitl.py``
formed an unreachable island with test-only callers: the live human handoff is
implemented by aiogram handlers/state/forum relay, and the LangGraph-based
``hitl_guard``/``interrupt`` flow was explicitly obsolete (#2843 stubbed the
callback; #3211 removed the module and the stale ``hitl:`` registration).

These tests pin the post-deletion state:

1. The module files are gone.
2. Importing them raises ``ImportError``.
3. No production code references the deleted modules, so the island cannot
   silently regrow.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
_NOISE_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".worktrees",
        ".git",
    }
)

_PRODUCTION_SOURCE_ROOTS: tuple[str, ...] = ("telegram_bot", "src")

_BANNED_TOKENS: tuple[str, ...] = (
    "telegram_bot.agents.history_graph",
    "telegram_bot.agents.hitl",
    "from .history_graph",
    "from .hitl",
    "from .agents.hitl",
)


def _iter_production_python_files(repo_root: Path):
    """Yield .py files under known production roots, pruning noise dirs early."""
    for source_root in _PRODUCTION_SOURCE_ROOTS:
        root = repo_root / source_root
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in __import__("os").walk(root):
            dirnames[:] = [d for d in dirnames if d not in _NOISE_PARTS]
            for fname in filenames:
                if fname.endswith(".py"):
                    yield Path(dirpath) / fname


def _scan_production_for_island_references(repo_root: Path) -> list[str]:
    """Return repo-relative paths of production files referencing the island."""
    bad: list[str] = []
    for py_file in _iter_production_python_files(repo_root):
        rel = py_file.relative_to(repo_root)
        if rel.name == "test_history_hitl_removed.py":
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(token in text for token in _BANNED_TOKENS):
            bad.append(str(rel))
    return bad


def test_history_graph_package_is_gone() -> None:
    """``telegram_bot/agents/history_graph/`` must not exist (#3211)."""
    candidate = REPO_ROOT / "telegram_bot" / "agents" / "history_graph"
    assert not candidate.exists(), (
        f"LangGraph history island re-introduced at {candidate}. The live human "
        "handoff is implemented by aiogram handlers/state/forum relay; do not "
        "re-add a LangGraph history sub-graph (#3211)."
    )


def test_hitl_module_is_gone() -> None:
    """``telegram_bot/agents/hitl.py`` must not exist (#3211)."""
    candidate = REPO_ROOT / "telegram_bot" / "agents" / "hitl.py"
    assert not candidate.exists(), (
        f"HITL module re-introduced at {candidate}. The stale LangGraph "
        "interrupt-based flow has no live callers; the real manager handoff "
        "lives in the aiogram handlers (#3211)."
    )


@pytest.mark.parametrize(
    "module",
    [
        "telegram_bot.agents.history_graph.graph",
        "telegram_bot.agents.history_graph.nodes",
        "telegram_bot.agents.history_graph.state",
        "telegram_bot.agents.hitl",
    ],
)
def test_island_imports_fail(module: str) -> None:
    """Importing the deleted modules must raise ImportError (#3211)."""
    with pytest.raises(ImportError):
        importlib.import_module(module)


def test_no_production_references_to_history_or_hitl_island() -> None:
    """No production module references the deleted island (#3211)."""
    bad_files = _scan_production_for_island_references(REPO_ROOT)
    assert not bad_files, (
        f"Production code still references the deleted history/HITL island: {bad_files}"
    )
