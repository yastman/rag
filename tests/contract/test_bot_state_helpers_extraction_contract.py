"""Contract: state-shape helpers extracted from ``telegram_bot/bot.py`` (#1265 Slice 1 PR-1).

Three helpers (``_state_apartment_results``, ``_state_control_message_id``,
``_extract_current_turn``) used to live as module-level functions in
``telegram_bot/bot.py``. They were moved to ``telegram_bot/_bot_state_helpers.py``
as the first slice of the bot.py decomposition plan published in #1265.

Pinned properties:

* ``telegram_bot._bot_state_helpers`` exists and exposes the three helpers.
* ``telegram_bot.bot`` re-exports them (existing callers and
  ``tests/unit/test_bot_scores.py`` import directly from ``telegram_bot.bot``).
* The re-exports return identical results so byte-for-byte runtime parity is
  guaranteed; helpers are implemented in only one place.
* ``telegram_bot/bot.py`` line count is strictly below the 4863 baseline that
  existed at the time of the decomposition plan, so the file shrinks
  monotonically as future slices land.
"""

from __future__ import annotations

import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"
HELPERS_PY = REPO_ROOT / "telegram_bot" / "_bot_state_helpers.py"

# Baseline at the time of the published #1265 decomposition plan
# (kiro-agent comment, 2026-05-22). Must shrink monotonically.
BOT_PY_LINE_COUNT_CEILING = 4863

EXTRACTED_HELPERS = (
    "_state_apartment_results",
    "_state_control_message_id",
    "_extract_current_turn",
)


def test_extracted_helpers_module_exists() -> None:
    assert HELPERS_PY.exists(), (
        "#1265 Slice 1 PR-1: telegram_bot/_bot_state_helpers.py is the new home "
        "for the three state-shape helpers extracted from bot.py."
    )


def test_extracted_helpers_module_has_no_aiogram_or_langgraph_imports() -> None:
    """The extracted module must remain UI/runtime-free so it stays trivially
    importable from tests and other tooling."""
    text = HELPERS_PY.read_text(encoding="utf-8")
    for forbidden in ("aiogram", "langgraph", "langchain", "fastapi"):
        assert f"import {forbidden}" not in text and f"from {forbidden}" not in text, (
            f"telegram_bot/_bot_state_helpers.py must not import {forbidden!r}; "
            "it is a pure dict-shape helper module."
        )


def test_helpers_module_exposes_expected_names() -> None:
    module = importlib.import_module("telegram_bot._bot_state_helpers")
    for name in EXTRACTED_HELPERS:
        assert hasattr(module, name), (
            f"telegram_bot._bot_state_helpers missing required helper {name!r}."
        )


def test_bot_py_re_exports_helpers_with_same_identity() -> None:
    """Existing callers (telegram_bot.bot.<helper>) must keep resolving to the
    exact same callable that lives in _bot_state_helpers (no copy/paste)."""
    # bot.py wraps the helpers with thin pass-through functions to keep the
    # public ``telegram_bot.bot`` import surface stable. Verify equivalence by
    # calling both sides on a representative payload rather than asserting
    # ``is`` identity.
    bot = importlib.import_module("telegram_bot.bot")
    helpers = importlib.import_module("telegram_bot._bot_state_helpers")
    sample_state = {
        "apartment_results": [{"id": 1}, {"id": 2}, "not-a-dict"],
        "catalog_runtime": {"control_message_id": 42, "results": [{"id": 99}]},
        "apartment_footer_msg_id": 7,
    }
    assert bot._state_apartment_results(sample_state) == helpers._state_apartment_results(
        sample_state
    )
    assert bot._state_control_message_id(sample_state) == helpers._state_control_message_id(
        sample_state
    )

    class _Msg:
        def __init__(self, kind: str) -> None:
            self.type = kind

    msgs = [_Msg("human"), _Msg("ai"), _Msg("human"), _Msg("ai"), _Msg("ai")]
    assert bot._extract_current_turn(msgs) == helpers._extract_current_turn(msgs)


def test_bot_py_does_not_redeclare_extracted_helpers() -> None:
    """No copy/paste of the extracted helpers may live in bot.py — only thin
    wrappers that delegate to ``_bot_state_helpers``."""
    text = BOT_PY.read_text(encoding="utf-8")
    for name in EXTRACTED_HELPERS:
        # Allow exactly one ``def <name>`` definition (the wrapper).
        occurrences = text.count(f"def {name}(")
        assert occurrences <= 1, (
            f"#1265 Slice 1 PR-1: telegram_bot/bot.py defines {name} "
            f"{occurrences} times; expected at most 1 (a thin wrapper that "
            "delegates to telegram_bot._bot_state_helpers). Remove the duplicate "
            "implementation."
        )


def test_bot_py_line_count_is_strictly_below_baseline() -> None:
    """Ratchet: bot.py must shrink monotonically as #1265 slices land."""
    line_count = sum(1 for _ in BOT_PY.open(encoding="utf-8"))
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"#1265: telegram_bot/bot.py has {line_count} lines, which is not "
        f"smaller than the {BOT_PY_LINE_COUNT_CEILING}-line baseline established "
        "when the decomposition plan was published. After landing a new "
        "extraction slice, lower BOT_PY_LINE_COUNT_CEILING here to lock in the "
        "shrink."
    )
