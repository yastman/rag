"""Contract: supervisor retry uses tenacity, not manual try/except (#1233).

The pre-tenacity version had ~180 lines of try/except boilerplate that
duplicated tenacity's ``retry_if_exception`` + ``stop_after_attempt`` +
``before_sleep`` pattern. tenacity is already a project dependency
(``telegram_bot/services/kommo_tokens.py``, ``telegram_bot/preflight.py``,
``telegram_bot/main.py``), so the supervisor retry path must use it too.

The two methods under contract:

* ``PropertyBot._astream_supervisor_with_recovery``
* ``PropertyBot._ainvoke_supervisor_with_recovery``

Both run the supervisor agent and, on a checkpointer runtime error, must
recreate the agent with a ``MemorySaver`` fallback and retry once — but
only for non-write-side roles (``client``), per #1233. That policy is
exactly ``retry_if_exception(_is_checkpointer_runtime_error)`` +
``stop_after_attempt(2)`` + a ``before_sleep`` callback that swaps the
agent.

This contract guards against a future contributor reintroducing manual
``try/except`` retry loops in either method.

Verified via Context7 (/jd/tenacity): ``AsyncRetrying`` + ``before_sleep``
is the documented async pattern for "do something between retries", e.g.
re-establishing connections or refreshing state.
Content was rephrased for compliance with licensing restrictions.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"


def _find_method(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _has_manual_checkpointer_retry_pattern(node: ast.AsyncFunctionDef) -> list[int]:
    """Find ``if not _is_checkpointer_runtime_error(exc): raise`` patterns."""
    bad: list[int] = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.UnaryOp) or not isinstance(sub.op, ast.Not):
            continue
        operand = sub.operand
        if (
            isinstance(operand, ast.Call)
            and isinstance(operand.func, ast.Name)
            and operand.func.id == "_is_checkpointer_runtime_error"
        ):
            bad.append(sub.lineno)
    return bad


def test_bot_py_imports_tenacity() -> None:
    """``telegram_bot/bot.py`` must import tenacity for the supervisor retry path."""
    src = BOT_PY.read_text(encoding="utf-8")
    assert "from tenacity import" in src or "import tenacity" in src, (
        "telegram_bot/bot.py must import tenacity for SDK-native retry policy "
        "(#1233). The project already depends on tenacity in kommo_tokens.py, "
        "preflight.py, and main.py."
    )


def test_supervisor_streaming_recovery_has_no_manual_checkpointer_retry() -> None:
    """``_astream_supervisor_with_recovery`` must delegate retry to tenacity (#1233)."""
    tree = ast.parse(BOT_PY.read_text(encoding="utf-8"), filename=str(BOT_PY))
    node = _find_method(tree, "_astream_supervisor_with_recovery")
    assert node is not None, (
        "_astream_supervisor_with_recovery must exist in telegram_bot/bot.py"
    )
    bad_lines = _has_manual_checkpointer_retry_pattern(node)
    assert not bad_lines, (
        f"_astream_supervisor_with_recovery contains manual "
        f"`if not _is_checkpointer_runtime_error(exc): raise` retry boilerplate at "
        f"line(s) {bad_lines}. Replace with tenacity ``AsyncRetrying`` /"
        f" ``retry_if_exception(_is_checkpointer_runtime_error)`` per #1233."
    )


def test_supervisor_invoke_recovery_has_no_manual_checkpointer_retry() -> None:
    """``_ainvoke_supervisor_with_recovery`` must delegate retry to tenacity (#1233)."""
    tree = ast.parse(BOT_PY.read_text(encoding="utf-8"), filename=str(BOT_PY))
    node = _find_method(tree, "_ainvoke_supervisor_with_recovery")
    assert node is not None, (
        "_ainvoke_supervisor_with_recovery must exist in telegram_bot/bot.py"
    )
    bad_lines = _has_manual_checkpointer_retry_pattern(node)
    assert not bad_lines, (
        f"_ainvoke_supervisor_with_recovery contains manual "
        f"`if not _is_checkpointer_runtime_error(exc): raise` retry boilerplate at "
        f"line(s) {bad_lines}. Replace with tenacity ``AsyncRetrying`` /"
        f" ``retry_if_exception(_is_checkpointer_runtime_error)`` per #1233."
    )
