"""Drift guard for #1948 slice 5 — scoring.py migration to ``src/``.

Issue #1948 ("``src/api`` and ``mini_app`` import from ``telegram_bot``")
proposed migrating shared modules out of ``telegram_bot/`` so layering
arrows go the right way. Slices 1..4 landed in PR #2018, #2020, #2024,
#2030.

This contract pins **slice 5**: the scoring helpers
(``write_pipeline_scores``, ``score``, ``write_crm_scores``,
``write_history_scores``) become first-class citizens under ``src/``.
``telegram_bot/scoring.py`` becomes a thin re-export shim so existing bot
internals keep working unchanged. (``compute_checkpointer_overhead_proxy_ms``
was removed with the no-op checkpointer in #3218.)

Asserted invariants:

  1. ``src/scoring.py`` exists and is non-empty.
  2. The canonical module imports do NOT reach into ``telegram_bot.*``
     at module scope — that is the whole point of the layering rule.
  3. The canonical module exposes the full public API
     (``score``, ``write_crm_scores``, ``write_history_scores``,
     ``write_pipeline_scores``).
  4. The ``telegram_bot/scoring.py`` shim re-exports every public
     callable with object-identity (``is``-equal).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL = REPO_ROOT / "src" / "scoring.py"
SHIM = REPO_ROOT / "telegram_bot" / "scoring.py"

PUBLIC_API: tuple[str, ...] = (
    "score",
    "write_crm_scores",
    "write_history_scores",
    "write_pipeline_scores",
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


def test_scoring_canonical_does_not_import_telegram_bot() -> None:
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
def test_telegram_bot_scoring_shim_re_exports_canonical(name: str) -> None:
    canonical = importlib.import_module("src.scoring")
    shim = importlib.import_module("telegram_bot.scoring")
    assert getattr(shim, name) is getattr(canonical, name), (
        f"telegram_bot.scoring.{name} must be the SAME object as "
        f"src.scoring.{name} (re-export shim, not a copy)."
    )


# ---------------------------------------------------------------------------
# 5. Behavioral contract — no-op writers and real compute helper
# ---------------------------------------------------------------------------


NOOP_SCORERS: tuple[str, ...] = (
    "score",
    "write_crm_scores",
    "write_history_scores",
    "write_pipeline_scores",
    "write_scores",
)


class _BrokenClient:
    """Sentinel that raises if a no-op mistakenly touches it."""

    def __getattr__(self, name: str) -> None:
        msg = f"No-op must not call client.{name} — tracing removed since #2844."
        raise AssertionError(msg)


@pytest.mark.parametrize("name", NOOP_SCORERS)
def test_scoring_noop_returns_none(name: str) -> None:
    """Every no-op writer must return ``None`` when called with typical args
    and must NOT call any client method on the provided ``lf`` object.
    """
    mod = importlib.import_module("src.scoring")
    fn = getattr(mod, name)

    broken = _BrokenClient()
    result = None  # sentinel
    if name == "score":
        result = fn(broken, "test-trace", name="test", value=1.0)
    elif name == "write_crm_scores":
        result = fn(broken, [], trace_id="test-trace")
    elif name == "write_history_scores":
        result = fn(broken, "test-trace", count=5, latency_ms=10.0)
    elif name == "write_pipeline_scores" or name == "write_scores":
        result = fn(broken, {}, trace_id="test-trace")

    assert result is None, f"{name} must return None, got {result!r}"
