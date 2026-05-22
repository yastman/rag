"""Drift guard for #1948 slice 5 — scoring.py migration to ``src/``.

Issue #1948 ("``src/api`` and ``mini_app`` import from ``telegram_bot``")
proposed migrating shared modules out of ``telegram_bot/`` so layering
arrows go the right way. Slices 1..4 landed in PR #2018, #2020, #2024,
#2030.

This contract pins **slice 5**: the Langfuse scoring helpers
(``write_langfuse_scores``, ``score``, ``write_crm_scores``,
``write_history_scores``, ``compute_checkpointer_overhead_proxy_ms``)
become first-class citizens under ``src/`` and ``src/api/main.py``
imports them directly from there. ``telegram_bot/scoring.py`` becomes
a thin re-export shim so existing bot internals
(``telegram_bot/agents/rag_tool.py``, ``telegram_bot/handlers/command_handlers.py``,
``telegram_bot/pipelines/client.py``, ``telegram_bot/bot.py``) keep working
unchanged.

Asserted invariants:

  1. ``src/scoring.py`` exists and is non-empty.
  2. The canonical module imports do NOT reach into ``telegram_bot.*``
     at module scope — that is the whole point of the layering rule.
  3. The canonical module exposes the full public API
     (``compute_checkpointer_overhead_proxy_ms``, ``score``,
     ``write_crm_scores``, ``write_history_scores``,
     ``write_langfuse_scores``).
  4. The ``telegram_bot/scoring.py`` shim re-exports every public
     callable with object-identity (``is``-equal).
  5. ``src/api/main.py`` imports ``write_langfuse_scores`` from
     ``src.scoring`` (not from ``telegram_bot.scoring``).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL = REPO_ROOT / "src" / "scoring.py"
SHIM = REPO_ROOT / "telegram_bot" / "scoring.py"
RAG_API_MAIN = REPO_ROOT / "src" / "api" / "main.py"

PUBLIC_API: tuple[str, ...] = (
    "compute_checkpointer_overhead_proxy_ms",
    "score",
    "write_crm_scores",
    "write_history_scores",
    "write_langfuse_scores",
)


def _ast_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


# ---------------------------------------------------------------------------
# 1. Canonical home exists
# ---------------------------------------------------------------------------


def test_canonical_scoring_exists() -> None:
    assert CANONICAL.exists(), (
        f"#1948 slice 5: expected {CANONICAL.relative_to(REPO_ROOT)} to be "
        "the canonical home for Langfuse scoring helpers."
    )
    assert CANONICAL.read_text().strip(), f"{CANONICAL.relative_to(REPO_ROOT)} must not be empty."


# ---------------------------------------------------------------------------
# 2. Canonical does not depend on telegram_bot
# ---------------------------------------------------------------------------


def test_canonical_does_not_import_telegram_bot() -> None:
    """src/scoring.py must not import from telegram_bot.* at module scope —
    that is the layering rule #1948 enforces.
    """
    bad = [mod for mod in _ast_imports(CANONICAL) if mod.split(".")[0] == "telegram_bot"]
    assert not bad, (
        f"src/scoring.py module-level imports must not reach into "
        f"telegram_bot.* (#1948 layering rule); found: {bad}"
    )


# ---------------------------------------------------------------------------
# 3. Canonical public API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PUBLIC_API)
def test_canonical_exposes_public_api(name: str) -> None:
    canonical = importlib.import_module("src.scoring")
    assert hasattr(canonical, name), f"src.scoring.{name} missing — public API regression."
    assert callable(getattr(canonical, name)), f"src.scoring.{name} must be callable."


# ---------------------------------------------------------------------------
# 4. telegram_bot shim keeps object-identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PUBLIC_API)
def test_telegram_bot_shim_re_exports_canonical(name: str) -> None:
    canonical = importlib.import_module("src.scoring")
    shim = importlib.import_module("telegram_bot.scoring")
    assert getattr(shim, name) is getattr(canonical, name), (
        f"telegram_bot.scoring.{name} must be the SAME object as "
        f"src.scoring.{name} (re-export shim, not a copy)."
    )


# ---------------------------------------------------------------------------
# 5. src/api/main.py imports from src/, not telegram_bot/
# ---------------------------------------------------------------------------


def test_rag_api_main_imports_scoring_from_src() -> None:
    """src/api/main.py must not contain any ``telegram_bot.scoring`` references —
    including the lazy ``from telegram_bot.scoring import write_langfuse_scores``
    inside ``_run_rag_pipeline``.
    """
    src = RAG_API_MAIN.read_text()
    assert "from src.scoring import" in src, (
        f"#1948 slice 5: {RAG_API_MAIN.relative_to(REPO_ROOT)} must import from src.scoring."
    )
    assert "from telegram_bot.scoring import" not in src, (
        f"#1948 slice 5 regression: {RAG_API_MAIN.relative_to(REPO_ROOT)} "
        "must not import from telegram_bot.scoring anymore."
    )
