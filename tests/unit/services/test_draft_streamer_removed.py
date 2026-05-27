# tests/unit/services/test_draft_streamer_removed.py
"""Regression locks: the custom DraftStreamer abstraction must stay deleted (#1671).

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
_NOISE_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".worktrees",
        ".git",
    }
)

# Production source roots scanned for draft_streamer references (#2198).
# Bounded list — adding ``REPO_ROOT.rglob('*.py')`` walks .venv, worktrees,
# and caches before filtering, which exceeds the 30s pytest-timeout on
# local checkouts.
_PRODUCTION_SOURCE_ROOTS: tuple[str, ...] = ("telegram_bot", "src")

_BANNED_TOKENS: tuple[str, ...] = (
    "telegram_bot.services.draft_streamer",
    " draft_streamer ",
    "from .draft_streamer",
)


def _iter_production_python_files(repo_root: Path):
    """Yield .py files under known production source roots, pruning noise
    directories at the directory level (not after rglob)."""
    for source_root in _PRODUCTION_SOURCE_ROOTS:
        root = repo_root / source_root
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in __import__("os").walk(root):
            # Prune noise dirs in-place so os.walk stops descending.
            dirnames[:] = [d for d in dirnames if d not in _NOISE_PARTS]
            for fname in filenames:
                if fname.endswith(".py"):
                    yield Path(dirpath) / fname


def _scan_production_for_draft_streamer_references(repo_root: Path) -> list[str]:
    """Return repo-relative paths of production files referencing the
    deleted ``telegram_bot.services.draft_streamer`` module.

    Bounded scanner (#2198): only walks ``_PRODUCTION_SOURCE_ROOTS`` and
    prunes ``_NOISE_PARTS`` at the directory level. Test/script files
    are not scanned because they may legitimately mention the deleted
    module name.
    """
    bad: list[str] = []
    for py_file in _iter_production_python_files(repo_root):
        rel = py_file.relative_to(repo_root)
        if rel.name in {"test_draft_streamer.py", "test_draft_streamer_removed.py"}:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(token in text for token in _BANNED_TOKENS):
            bad.append(str(rel))
    return bad


def test_draft_streamer_module_file_is_gone() -> None:
    """`telegram_bot/services/draft_streamer.py` must not exist (#1671)."""
    candidate = REPO_ROOT / "telegram_bot" / "services" / "draft_streamer.py"
    assert not candidate.exists(), (
        f"DraftStreamer module re-introduced at {candidate}. The class is a custom "
        "wrapper for `bot.send_message_draft` / `bot.send_message`; per #1671 the "
        "consumer in bot.py inlines those calls directly using the LangGraph SDK "
        "`stream_mode=['messages', 'values']` pattern."
    )


def test_draft_streamer_module_import_fails() -> None:
    """Direct module import must raise ImportError (#1671)."""
    with pytest.raises(ImportError):
        import telegram_bot.services.draft_streamer  # noqa: F401


def test_draft_streamer_class_import_fails() -> None:
    """Symbol-level import must raise ImportError (#1671)."""
    with pytest.raises(ImportError):
        from telegram_bot.services.draft_streamer import DraftStreamer  # noqa: F401


def test_new_draft_id_lives_in_bot_module() -> None:
    """`_new_draft_id` moved next to its sole consumer in `telegram_bot.bot` (#1671)."""
    from telegram_bot.bot import _new_draft_id

    assert callable(_new_draft_id)


def test_new_draft_id_returns_positive_31bit_int() -> None:
    """Shape contract preserved across the move (#1671)."""
    from telegram_bot.bot import _new_draft_id

    draft_id = _new_draft_id()
    assert 1 <= draft_id < 2**31


def test_no_production_references_to_draft_streamer_module() -> None:
    """No production module imports `telegram_bot.services.draft_streamer` (#1671).

    Bounded to known production source roots (#2198) so a local checkout
    with .venv / worktrees / caches present cannot exceed the pytest-timeout.
    Tests and scripts are scanned separately; only production code under
    ``telegram_bot/`` and ``src/`` is checked here.
    """
    bad_files = _scan_production_for_draft_streamer_references(REPO_ROOT)
    assert not bad_files, (
        f"Production code still references the deleted draft_streamer module: {bad_files}"
    )


def test_production_reference_scanner_excludes_noise_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "telegram_bot").mkdir()
    (tmp_path / "telegram_bot" / "bot.py").write_text("# clean production\n", encoding="utf-8")
    for part in _NOISE_PARTS:
        noise_file = tmp_path / part / "stale.py"
        noise_file.parent.mkdir(parents=True, exist_ok=True)
        noise_file.write_text("import telegram_bot.services.draft_streamer\n", encoding="utf-8")

    refs = _scan_production_for_draft_streamer_references(tmp_path)
    assert refs == [], f"scanner descended into noise dirs: {refs}"


def test_streaming_path_still_uses_send_message_draft_directly() -> None:
    """The consumer must keep calling `bot.send_message_draft(...)` directly (#1671).

    Guards against accidentally re-introducing a custom streamer class. The
    SDK path is `agent.astream(..., stream_mode=["messages", "values"])`
    plus `bot.send_message_draft(...)` — nothing in between.
    """
    bot_py = (REPO_ROOT / "telegram_bot" / "bot.py").read_text(encoding="utf-8")
    assert "bot.send_message_draft" in bot_py, (
        "Streaming path must call `bot.send_message_draft(...)` directly (#1671)."
    )
    assert "DraftStreamer" not in bot_py, (
        "`DraftStreamer` class is gone; do not reintroduce it (#1671)."
    )
