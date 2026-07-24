"""Contract: observability helpers extracted from ``telegram_bot/bot.py`` (#1265 Slice 1 PR-2).

``_build_trace_metadata`` was moved from ``telegram_bot/bot.py`` into
``telegram_bot/_bot_observability.py``, then homed to
``telegram_bot/observability/bot_observability.py`` (card_2a71ec058138).

``_write_voice_error_scores`` was removed in #2942 when the voice handlers and
their Langfuse score paths were deleted from the bot.

Pinned properties:

* ``telegram_bot.observability.bot_observability`` exists and exposes ``_build_trace_metadata``.
* The module avoids aiogram / langgraph / fastapi imports so it stays
  cheap to import in tests.
* ``telegram_bot.bot`` re-exports ``_build_trace_metadata`` via a thin wrapper.
* ``telegram_bot/bot.py`` line count is strictly below the 4846-line
  baseline established by Slice 1 PR-1, locking in the shrink.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


pytestmark = pytest.mark.requires_extras


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"
HELPERS_PY = REPO_ROOT / "telegram_bot" / "observability" / "bot_observability.py"

# Baseline carried forward from #1265 Slice 1 PR-1 (refactor/1265-bot-state-helpers-extract).
# Each subsequent slice in the published plan must ratchet this number down.
BOT_PY_LINE_COUNT_CEILING = 4846


def test_bot_observability_helpers_module_exists() -> None:
    assert HELPERS_PY.exists(), (
        "card_2a71ec058138: telegram_bot/observability/bot_observability.py is the new home "
        "for _build_trace_metadata (homed from _bot_observability.py)."
    )


def test_extracted_helpers_module_has_no_aiogram_or_fastapi_imports() -> None:
    """The extracted module must remain transport/runtime-free so it stays
    trivially importable from tests."""
    text = HELPERS_PY.read_text(encoding="utf-8")
    for forbidden in ("aiogram", "langgraph", "langchain", "fastapi"):
        assert f"import {forbidden}" not in text and f"from {forbidden}" not in text, (
            f"telegram_bot/observability/bot_observability.py must not import {forbidden!r}; "
            "it is a pure observability dict/score helper module."
        )


def test_bot_observability_module_exposes_build_trace_metadata() -> None:
    module = importlib.import_module("telegram_bot.observability.bot_observability")
    assert hasattr(module, "_build_trace_metadata"), (
        "telegram_bot.observability.bot_observability missing required helper '_build_trace_metadata'."
    )


def test_bot_py_re_exports_build_trace_metadata_with_runtime_parity() -> None:
    """telegram_bot.bot._build_trace_metadata must produce identical output to
    the canonical implementation in observability.bot_observability."""
    bot = importlib.import_module("telegram_bot.bot")
    helpers = importlib.import_module("telegram_bot.observability.bot_observability")

    sample_state = {
        "input_type": "text",
        "query_type": "GENERAL",
        "topic_hint": "buy",
        "grounding_mode": "strict",
        "grade_confidence": 0.42,
        "pipeline_wall_ms": 1200.5,
        "pre_agent_ms": 250.0,
        "e2e_latency_ms": 1230.0,
        "cache_hit": False,
        "search_results_count": 3,
        "rerank_applied": True,
        "llm_provider_model": "gpt-4",
        "llm_ttft_ms": 90.0,
        "messages": ["m1", "m2", "m3"],
    }
    assert bot._build_trace_metadata(sample_state) == helpers._build_trace_metadata(sample_state)
    # Empty input must also produce identical defaults.
    assert bot._build_trace_metadata({}) == helpers._build_trace_metadata({})


def test_bot_py_does_not_redeclare_build_trace_metadata() -> None:
    """No copy/paste of the extracted helper may live in bot.py — only a thin
    wrapper that delegates to ``observability.bot_observability``."""
    text = BOT_PY.read_text(encoding="utf-8")
    occurrences = text.count("def _build_trace_metadata(")
    assert occurrences <= 1, (
        f"card_2a71ec058138: telegram_bot/bot.py defines _build_trace_metadata "
        f"{occurrences} times; expected at most 1 (a thin wrapper). Remove the duplicate."
    )


def test_bot_py_line_count_is_strictly_below_pr1_baseline() -> None:
    """Ratchet: bot.py must shrink monotonically as #1265 slices land."""
    line_count = sum(1 for _ in BOT_PY.open(encoding="utf-8"))
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"#1265: telegram_bot/bot.py has {line_count} lines, which is not "
        f"smaller than the {BOT_PY_LINE_COUNT_CEILING}-line baseline established "
        "by Slice 1 PR-1 (refactor/1265-bot-state-helpers-extract). After "
        "landing a new extraction slice, lower BOT_PY_LINE_COUNT_CEILING here "
        "to lock in the shrink."
    )
