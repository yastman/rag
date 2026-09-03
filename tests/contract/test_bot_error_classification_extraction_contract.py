"""Absence contract: LangGraph error-classification helpers stay deleted (#3218).

History: #1265 Slice 1 PR-3 extracted ``_is_post_pipeline_cleanup_error`` and
``_is_checkpointer_runtime_error`` from ``bot.py`` into
``telegram_bot/handlers/error_classification.py``. Both existed solely to
classify retryable LangGraph Pregel/checkpointer failures for the supervisor
recovery wrappers (``_ainvoke/_astream_supervisor_with_recovery``). The
recovery wrappers went with the imperative agent facade (#3216) and the
no-op checkpointer went in #3218, so the classifiers and their module were
deleted.

Bug class: dead-facade-regrowth
Canonical issue: #3218

This contract pins the deletion:

1. ``telegram_bot/handlers/error_classification.py`` is gone from the tree.
2. ``telegram_bot.bot`` no longer defines the classifier wrappers.
3. Importing the deleted module raises ``ImportError``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.requires_extras


REPO_ROOT = Path(__file__).resolve().parents[2]
NEW_MODULE = REPO_ROOT / "telegram_bot" / "handlers" / "error_classification.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

HELPERS: tuple[str, ...] = (
    "_is_post_pipeline_cleanup_error",
    "_is_checkpointer_runtime_error",
)


def test_error_classification_module_is_deleted() -> None:
    assert not NEW_MODULE.exists(), (
        f"#3218: {NEW_MODULE.relative_to(REPO_ROOT)} was deleted — there is no "
        "LangGraph checkpointer/Pregel surface left to classify. Do not "
        "reintroduce it without reintroducing a real consumer."
    )


def test_importing_error_classification_fails() -> None:
    """Importing the deleted module raises ImportError (import lock)."""
    import importlib

    try:
        importlib.import_module("telegram_bot.handlers.error_classification")
    except ImportError:
        return
    raise AssertionError(
        "#3218: telegram_bot.handlers.error_classification is importable again; "
        "the deleted retry-plumbing classifier regrew."
    )


@pytest.mark.parametrize("helper", HELPERS)
def test_bot_py_does_not_define_classifier(helper: str) -> None:
    """``bot.py`` must not define the removed classifier wrappers."""
    src = BOT_PY.read_text()
    pattern = re.compile(rf"^(async\s+def|def)\s+{re.escape(helper)}\(", re.MULTILINE)
    matches = pattern.findall(src)
    assert not matches, (
        f"bot.py defines `def {helper}` again; the checkpointer/Pregel retry "
        "classifiers were removed in #3218 and must stay removed."
    )
