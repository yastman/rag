"""Contract: observability helpers extracted from ``telegram_bot/bot.py`` (#1265 Slice 1 PR-2).

Two helpers used by both the text and voice handlers were moved from
``telegram_bot/bot.py`` into ``telegram_bot/_bot_observability.py``:

* ``_build_trace_metadata`` — pure dict transform that flattens per-query
  graph state into the metadata payload Langfuse expects.
* ``_write_voice_error_scores`` — writes a minimal Langfuse score set on
  voice early-exit paths (transcription empty / recursion limit / pipeline
  failure) so dashboards always have ``input_type=voice`` plus an error
  reason.

Pinned properties (mirror of #1265 Slice 1 PR-1):

* ``telegram_bot._bot_observability`` exists and exposes both helpers.
* The module avoids aiogram / langgraph / fastapi imports so it stays
  cheap to import in tests.
* ``telegram_bot.bot`` re-exports both helpers via thin wrappers that
  delegate to the new module — runtime parity is byte-for-byte.
* ``telegram_bot/bot.py`` defines each helper at most once (no duplicate
  copy of the implementation).
* ``telegram_bot/bot.py`` line count is strictly below the 4846-line
  baseline established by Slice 1 PR-1, locking in the shrink.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"
HELPERS_PY = REPO_ROOT / "telegram_bot" / "_bot_observability.py"

# Baseline carried forward from #1265 Slice 1 PR-1 (refactor/1265-bot-state-helpers-extract).
# Each subsequent slice in the published plan must ratchet this number down.
BOT_PY_LINE_COUNT_CEILING = 4846

EXTRACTED_HELPERS = (
    "_build_trace_metadata",
    "_write_voice_error_scores",
)


def test_extracted_helpers_module_exists() -> None:
    assert HELPERS_PY.exists(), (
        "#1265 Slice 1 PR-2: telegram_bot/_bot_observability.py is the new home "
        "for _build_trace_metadata and _write_voice_error_scores."
    )


def test_extracted_helpers_module_has_no_aiogram_or_fastapi_imports() -> None:
    """The extracted module must remain transport/runtime-free so it stays
    trivially importable from tests."""
    text = HELPERS_PY.read_text(encoding="utf-8")
    for forbidden in ("aiogram", "langgraph", "langchain", "fastapi"):
        assert f"import {forbidden}" not in text and f"from {forbidden}" not in text, (
            f"telegram_bot/_bot_observability.py must not import {forbidden!r}; "
            "it is a pure observability dict/score helper module."
        )


def test_helpers_module_exposes_expected_names() -> None:
    module = importlib.import_module("telegram_bot._bot_observability")
    for name in EXTRACTED_HELPERS:
        assert hasattr(module, name), (
            f"telegram_bot._bot_observability missing required helper {name!r}."
        )


def test_bot_py_re_exports_build_trace_metadata_with_runtime_parity() -> None:
    """telegram_bot.bot._build_trace_metadata must produce identical output to
    the canonical implementation in _bot_observability."""
    bot = importlib.import_module("telegram_bot.bot")
    helpers = importlib.import_module("telegram_bot._bot_observability")

    sample_state = {
        "input_type": "voice",
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
        "stt_duration_ms": 700.0,
    }
    assert bot._build_trace_metadata(sample_state) == helpers._build_trace_metadata(sample_state)
    # Empty input must also produce identical defaults.
    assert bot._build_trace_metadata({}) == helpers._build_trace_metadata({})


def test_bot_py_re_exports_write_voice_error_scores_with_runtime_parity() -> None:
    """telegram_bot.bot._write_voice_error_scores must call the same Langfuse
    surface as the canonical implementation."""
    bot = importlib.import_module("telegram_bot.bot")
    helpers = importlib.import_module("telegram_bot._bot_observability")

    lf_via_bot = MagicMock()
    lf_via_helpers = MagicMock()
    bot._write_voice_error_scores(
        lf_via_bot,
        trace_id="trace-xyz",
        voice_duration_s=4.5,
        error_reason="recursion_limit",
    )
    helpers._write_voice_error_scores(
        lf_via_helpers,
        trace_id="trace-xyz",
        voice_duration_s=4.5,
        error_reason="recursion_limit",
    )
    # Both wrappers should produce the same number of create_score calls with
    # the same kwargs (order matters because the helper writes them in a fixed
    # sequence: input_type, voice_error_reason, voice_duration_s).
    assert lf_via_bot.create_score.call_args_list == lf_via_helpers.create_score.call_args_list


def test_bot_py_does_not_redeclare_extracted_helpers() -> None:
    """No copy/paste of the extracted helpers may live in bot.py — only thin
    wrappers that delegate to ``_bot_observability``."""
    text = BOT_PY.read_text(encoding="utf-8")
    for name in EXTRACTED_HELPERS:
        occurrences = text.count(f"def {name}(")
        assert occurrences <= 1, (
            f"#1265 Slice 1 PR-2: telegram_bot/bot.py defines {name} "
            f"{occurrences} times; expected at most 1 (a thin wrapper that "
            "delegates to telegram_bot._bot_observability). Remove the duplicate "
            "implementation."
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
