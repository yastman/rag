***REMOVED*** tests/unit/services/test_draft_streamer_removed.py
"""Regression locks: the custom DraftStreamer abstraction must stay deleted (***REMOVED***1671).

`telegram_bot/services/draft_streamer.py` was a thin custom wrapper around
`bot.send_message_draft` + `bot.send_message`. The streaming consumer
(`_stream_agent_to_draft` in `bot.py`) already uses LangGraph's SDK-native
`agent.astream(..., stream_mode=["messages", "values"])`, so the class was
duplicate code with no SDK gap to fill.

These tests pin the post-deletion state:

1. The module file is gone.
2. Importing it (or its symbols) raises `ImportError`.
3. The `_new_draft_id` helper that was inside it now lives next to the
   sole runtime consumer in `telegram_bot.bot`, with the same shape:
   positive 31-bit integer, never reused trivially.
4. No production code references the deleted module.
5. The streaming consumer still calls `bot.send_message_draft(...)` directly
   (we did not regress to a different custom abstraction).
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_draft_streamer_module_file_is_gone() -> None:
    """`telegram_bot/services/draft_streamer.py` must not exist (***REMOVED***1671)."""
    candidate = REPO_ROOT / "telegram_bot" / "services" / "draft_streamer.py"
    assert not candidate.exists(), (
        f"DraftStreamer module re-introduced at {candidate}. The class is a custom "
        "wrapper for `bot.send_message_draft` / `bot.send_message`; per ***REMOVED***1671 the "
        "consumer in bot.py inlines those calls directly using the LangGraph SDK "
        "`stream_mode=['messages', 'values']` pattern."
    )


def test_draft_streamer_module_import_fails() -> None:
    """Direct module import must raise ImportError (***REMOVED***1671)."""
    with pytest.raises(ImportError):
        import telegram_bot.services.draft_streamer  ***REMOVED*** noqa: F401


def test_draft_streamer_class_import_fails() -> None:
    """Symbol-level import must raise ImportError (***REMOVED***1671)."""
    with pytest.raises(ImportError):
        from telegram_bot.services.draft_streamer import DraftStreamer  ***REMOVED*** noqa: F401


def test_new_draft_id_lives_in_bot_module() -> None:
    """`_new_draft_id` moved next to its sole consumer in `telegram_bot.bot` (***REMOVED***1671)."""
    from telegram_bot.bot import _new_draft_id

    assert callable(_new_draft_id)


def test_new_draft_id_returns_positive_31bit_int() -> None:
    """Shape contract preserved across the move (***REMOVED***1671)."""
    from telegram_bot.bot import _new_draft_id

    draft_id = _new_draft_id()
    assert 1 <= draft_id < 2**31


def test_no_production_references_to_draft_streamer_module() -> None:
    """No production module imports `telegram_bot.services.draft_streamer` (***REMOVED***1671).

    Tests are scanned separately; only `tests/` may legitimately mention the
    deleted module name (e.g. these regression locks). Production code must
    not depend on it.
    """
    bad_files: list[str] = []
    for py_file in REPO_ROOT.rglob("*.py"):
        rel = py_file.relative_to(REPO_ROOT)
        rel_str = str(rel)
        if rel_str.startswith(("tests/", ".venv/", "scripts/")):
            continue
        if rel.name in {"test_draft_streamer.py", "test_draft_streamer_removed.py"}:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if (
            "telegram_bot.services.draft_streamer" in text
            or " draft_streamer " in text
            or "from .draft_streamer" in text
        ):
            bad_files.append(rel_str)
    assert not bad_files, (
        f"Production code still references the deleted draft_streamer module: {bad_files}"
    )


def test_streaming_path_still_uses_send_message_draft_directly() -> None:
    """The consumer must keep calling `bot.send_message_draft(...)` directly (***REMOVED***1671).

    Guards against accidentally re-introducing a custom streamer class. The
    SDK path is `agent.astream(..., stream_mode=["messages", "values"])`
    plus `bot.send_message_draft(...)` — nothing in between.
    """
    bot_py = (REPO_ROOT / "telegram_bot" / "bot.py").read_text(encoding="utf-8")
    assert "bot.send_message_draft" in bot_py, (
        "Streaming path must call `bot.send_message_draft(...)` directly (***REMOVED***1671)."
    )
    assert "DraftStreamer" not in bot_py, (
        "`DraftStreamer` class is gone; do not reintroduce it (***REMOVED***1671)."
    )
