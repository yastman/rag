"""Drift guard for #1265 Slice 1 PR-4 — _bot_streaming extract (post-#3218).

Issue #1265 published a 6-PR Slice 1 plan that extracts pure module-level
helpers out of ``telegram_bot/bot.py`` before any class-level decomposition.

PR-4 originally pinned three streaming helpers. #3218 removed
``_stream_agent_to_draft`` and ``_extract_stream_chunk_text`` (their only
runtime caller was the supervisor recovery wrapper deleted with the
imperative agent facade, #3216), leaving the live surface:

  - _new_draft_id — 31-bit draft id generator, still used by
    ``pipeline/supervisor.py::_send_core_response``.

Asserted invariants:

  1. ``telegram_bot/pipeline/streaming.py`` exists and is import-clean
     (stdlib only — no aiogram / langgraph / fastapi / langchain).
  2. ``_new_draft_id`` is exposed at module top and returns a positive
     31-bit signed int across many calls (bot's draft_id contract).
  3. The removed streaming helpers stay removed (see also
     ``test_streaming_sdk_native_contract.py``).
  4. ``bot.py`` defines ``_new_draft_id`` at most once (the wrapper).
  5. ``bot.py`` line count is strictly below the 4863 baseline.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.requires_extras


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_MODULE = REPO_ROOT / "telegram_bot" / "pipeline" / "streaming.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

LIVE_HELPERS: tuple[str, ...] = ("_new_draft_id",)
REMOVED_HELPERS: tuple[str, ...] = (
    "_stream_agent_to_draft",
    "_extract_stream_chunk_text",
)

FORBIDDEN_MODULE_LEVEL_IMPORTS: tuple[str, ...] = (
    "aiogram",
    "langgraph",
    "fastapi",
    "langchain",
    "redis",
    "qdrant_client",
)

BOT_PY_LINE_COUNT_CEILING = 4863


# ---------------------------------------------------------------------------
# Module existence + import hygiene
# ---------------------------------------------------------------------------


def test_bot_streaming_module_exists() -> None:
    assert NEW_MODULE.exists(), (
        f"#1265 Slice 1 PR-4: expected {NEW_MODULE.relative_to(REPO_ROOT)} "
        "to own the extracted streaming helpers."
    )


def test_bot_streaming_module_imports_are_clean() -> None:
    tree = ast.parse(NEW_MODULE.read_text())
    bad: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                bad.append(node.module or "")
    assert not bad, (
        f"pipeline/streaming.py module-level imports must avoid the bot stack; "
        f"found forbidden roots: {bad}"
    )


@pytest.mark.parametrize("helper", LIVE_HELPERS)
def test_bot_streaming_helper_exposed(helper: str) -> None:
    """Each live helper must be defined at module top-level."""
    tree = ast.parse(NEW_MODULE.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert helper in names, f"pipeline/streaming.{helper} must be defined at module top."


@pytest.mark.parametrize("helper", REMOVED_HELPERS)
def test_removed_streaming_helpers_stay_gone(helper: str) -> None:
    """#3218: the dead streaming facade must not regrow."""
    tree = ast.parse(NEW_MODULE.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert helper not in names, (
        f"pipeline/streaming.{helper} was removed in #3218 (no runtime consumer "
        "after the agent facade removal in #3216); do not reintroduce it."
    )


def test_agent_draft_interval_constant_stays_gone() -> None:
    """``_AGENT_DRAFT_INTERVAL`` belonged to the removed streaming loop."""
    from telegram_bot.pipeline import streaming as _bot_streaming

    assert not hasattr(_bot_streaming, "_AGENT_DRAFT_INTERVAL"), (
        "#3218: _AGENT_DRAFT_INTERVAL was removed with _stream_agent_to_draft."
    )


# ---------------------------------------------------------------------------
# _new_draft_id contract
# ---------------------------------------------------------------------------


def test_bot_streaming_new_draft_id_returns_positive_31bit_int() -> None:
    """Generator must always produce a positive value within signed-int32."""
    from telegram_bot.pipeline import streaming as _bot_streaming

    for _ in range(200):
        v = _bot_streaming._new_draft_id()
        assert isinstance(v, int)
        assert 1 <= v <= 2**31 - 1, f"draft id {v} outside [1, 2^31-1]"


def test_new_draft_id_wrapper_identity() -> None:
    """``bot._new_draft_id`` and ``_bot_streaming._new_draft_id`` produce
    same-shaped values — both within the documented draft-id range.
    """
    from telegram_bot import bot
    from telegram_bot.pipeline import streaming as _bot_streaming

    for _ in range(50):
        bv = bot._new_draft_id()
        cv = _bot_streaming._new_draft_id()
        assert 1 <= bv <= 2**31 - 1
        assert 1 <= cv <= 2**31 - 1


# ---------------------------------------------------------------------------
# bot.py shape — no duplicate definition + line-count ratchet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("helper", LIVE_HELPERS + REMOVED_HELPERS)
def test_bot_py_defines_streaming_helper_at_most_once(helper: str) -> None:
    """``bot.py`` must keep at most one ``def <helper>(...)``."""
    src = BOT_PY.read_text()
    pattern = re.compile(rf"^(async\s+def|def)\s+{re.escape(helper)}\(", re.MULTILINE)
    matches = pattern.findall(src)
    assert len(matches) <= 1, f"bot.py defines `{helper}` {len(matches)} times; expected at most 1."


def test_bot_py_streaming_line_count_below_ratchet() -> None:
    line_count = sum(1 for _ in BOT_PY.read_text().splitlines())
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"bot.py line count is {line_count}; #1265 Slice 1 PR-4 ratchet "
        f"requires < {BOT_PY_LINE_COUNT_CEILING}."
    )
