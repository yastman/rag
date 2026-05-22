"""Drift guard for #1265 Slice 1 PR-3 — _bot_error_classification extract.

Issue #1265 published a 6-PR Slice 1 plan that extracts pure module-level
helpers out of ``telegram_bot/bot.py`` before any class-level decomposition.

This contract pins **PR-3** (error classification helpers):

  - _is_post_pipeline_cleanup_error
  - _is_checkpointer_runtime_error

It mirrors the PR-1 / PR-2 contracts:

  1. ``telegram_bot/_bot_error_classification.py`` exists and its
     module-level imports are restricted to stdlib + an internal
     traceback-walk helper. No aiogram / langgraph / fastapi / langchain.
  2. Both helpers are exposed at module top.
  3. ``telegram_bot.bot.<helper>`` and
     ``telegram_bot._bot_error_classification.<helper>`` produce
     byte-for-byte identical boolean output on a representative set of
     ``Exception`` payloads — including post-Pregel cleanup errors,
     RedisVL semantic-cache errors, and checkpointer/storage errors.
  4. ``bot.py`` defines each helper at most once (no duplicate body).
  5. ``bot.py`` line count is strictly below the 4863 baseline this PR
     extracts from. This is a ratchet that tightens with every future
     slice (PR-4, PR-5, PR-6).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_MODULE = REPO_ROOT / "telegram_bot" / "_bot_error_classification.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

# Helpers extracted by Slice 1 PR-3.
HELPERS: tuple[str, ...] = (
    "_is_post_pipeline_cleanup_error",
    "_is_checkpointer_runtime_error",
)

# Forbidden module-level dependencies in the new helpers module.
# The helpers must stay aiogram/langgraph/fastapi/langchain-free so any
# tooling can import them without pulling the bot stack.
FORBIDDEN_MODULE_LEVEL_IMPORTS: tuple[str, ...] = (
    "aiogram",
    "langgraph",
    "fastapi",
    "langchain",
    "redis",
    "qdrant_client",
)

# Strict ratchet — bot.py must be smaller than the pre-extract baseline.
BOT_PY_LINE_COUNT_CEILING = 4863


# ---------------------------------------------------------------------------
# Module existence + import hygiene
# ---------------------------------------------------------------------------


def test_bot_error_classification_module_exists() -> None:
    assert NEW_MODULE.exists(), (
        f"#1265 Slice 1 PR-3: expected {NEW_MODULE.relative_to(REPO_ROOT)} "
        "to own the extracted error-classification helpers."
    )


def test_bot_error_classification_module_imports_are_clean() -> None:
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
        f"_bot_error_classification.py module-level imports must avoid the "
        f"bot stack; found forbidden roots: {bad}"
    )


@pytest.mark.parametrize("helper", HELPERS)
def test_helper_exposed(helper: str) -> None:
    """Each helper must be defined at module top-level."""
    tree = ast.parse(NEW_MODULE.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert helper in names, f"_bot_error_classification.{helper} must be defined at module top."


# ---------------------------------------------------------------------------
# Byte-for-byte parity
# ---------------------------------------------------------------------------


def _make_exc_with_message(message: str) -> Exception:
    return RuntimeError(message)


def _make_exc_with_traceback(message: str, fake_filename: str, fake_func: str):
    """Synthesize an Exception whose traceback frame matches given filename/func.

    Uses ``compile(...)`` with a custom ``filename`` so the frame's
    ``co_filename`` matches what the helpers grep for, without monkeypatching.
    """
    source = f"def {fake_func}():\n    raise RuntimeError({message!r})\n{fake_func}()\n"
    code = compile(source, fake_filename, "exec")
    try:
        exec(code, {})
    except RuntimeError as exc:
        return exc
    raise AssertionError("expected RuntimeError to be raised")


# Representative payloads — each tuple is (label, exception_factory).
PARITY_PAYLOADS: list[tuple[str, object]] = [
    ("plain_runtime", _make_exc_with_message("nothing special")),
    (
        "pregel_aexit_redis",
        _make_exc_with_message(
            "AsyncPregelLoop.__aexit__ failed: redis.ConnectionError consuming input failed"
        ),
    ),
    (
        "pregel_aexit_redisvl",
        _make_exc_with_message("PregelLoop.__aexit__ raised RedisVLError schema mismatch"),
    ),
    (
        "checkpointer_serialize",
        _make_exc_with_message(
            "checkpointer aput failed: msgpack serialization redis connection lost"
        ),
    ),
    (
        "post_pipeline_marker_only",
        _make_exc_with_message("checkpointer happened but no storage marker"),
    ),
    (
        "storage_marker_only",
        _make_exc_with_message("redis.ConnectionError reading"),
    ),
    (
        "pregel_traceback_aexit",
        _make_exc_with_traceback(
            "boom",
            "/site-packages/langgraph/pregel/loop.py",
            "__aexit__",
        ),
    ),
    (
        "checkpoint_traceback",
        _make_exc_with_traceback(
            "boom",
            "/site-packages/langgraph/checkpoint/redis.py",
            "aput",
        ),
    ),
]


@pytest.mark.parametrize("helper", HELPERS)
@pytest.mark.parametrize(
    ("label", "exc"),
    [(label, exc) for label, exc in PARITY_PAYLOADS],
    ids=[label for label, _ in PARITY_PAYLOADS],
)
def test_helper_byte_for_byte_parity(helper: str, label: str, exc: Exception) -> None:
    """``bot.<helper>(exc)`` and ``_bot_error_classification.<helper>(exc)``
    must produce identical results on every representative payload.
    """
    from telegram_bot import _bot_error_classification, bot

    bot_fn = getattr(bot, helper)
    new_fn = getattr(_bot_error_classification, helper)

    bot_result = bot_fn(exc)
    new_result = new_fn(exc)
    assert bot_result == new_result, (
        f"#1265 PR-3 parity break for {helper}({label!r}): "
        f"bot.{helper}={bot_result!r}, _bot_error_classification.{helper}={new_result!r}"
    )


# ---------------------------------------------------------------------------
# bot.py shape — no duplicate definition + line-count ratchet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("helper", HELPERS)
def test_bot_py_defines_helper_at_most_once(helper: str) -> None:
    """``bot.py`` must keep at most one ``def <helper>(...)``."""
    src = BOT_PY.read_text()
    pattern = re.compile(rf"^def {re.escape(helper)}\(", re.MULTILINE)
    matches = pattern.findall(src)
    assert len(matches) <= 1, (
        f"bot.py defines `def {helper}` {len(matches)} times; expected at most 1 "
        "(the thin wrapper that delegates to _bot_error_classification)."
    )


def test_bot_py_line_count_below_ratchet() -> None:
    """``bot.py`` must be strictly smaller than the 4863-line baseline."""
    line_count = sum(1 for _ in BOT_PY.read_text().splitlines())
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"bot.py line count is {line_count}; #1265 Slice 1 PR-3 ratchet "
        f"requires < {BOT_PY_LINE_COUNT_CEILING}. Future slices (PR-4..PR-6) "
        "must keep tightening this ratchet."
    )
