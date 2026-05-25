"""Contract: bot streaming bridge stays SDK-native (LangGraph ``agent.astream(...)``).

ADR-0015 ("SDK-Native Baseline") records that the streaming bridge between
LangGraph and Telegram's ``sendMessageDraft`` API is implemented via the
SDK-native ``agent.astream(stream_mode=[...])`` API rather than a custom
polling abstraction. The audit issue (#1538) had the legacy
``services/draft_streamer.py`` listed as a tracked migration target; the
file was actually removed in an earlier refactor and the streaming path
moved to ``telegram_bot/_bot_streaming.py::_stream_agent_to_draft``.

This contract pins the SDK-native pattern so a regression that re-introduces
either ``DraftStreamer`` or a hand-rolled streaming loop fails CI loudly.

Refs ADR-0015, #1538.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMING_MODULE = REPO_ROOT / "telegram_bot" / "_bot_streaming.py"
LEGACY_DRAFT_STREAMER = REPO_ROOT / "telegram_bot" / "services" / "draft_streamer.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _has_function(tree: ast.Module, name: str) -> bool:
    """Return True iff a top-level (async) def named ``name`` exists."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return True
    return False


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def test_streaming_module_exists() -> None:
    """Sanity: the streaming module lives where we expect."""
    assert STREAMING_MODULE.is_file(), (
        f"Expected {STREAMING_MODULE.relative_to(REPO_ROOT)} to exist; "
        "the SDK-native streaming bridge lives there per ADR-0015."
    )


def test_stream_agent_to_draft_is_defined() -> None:
    """The canonical streaming helper must remain a top-level (async) def in this module."""
    tree = ast.parse(_source(STREAMING_MODULE))
    assert _has_function(tree, "_stream_agent_to_draft"), (
        "telegram_bot/_bot_streaming.py::_stream_agent_to_draft is the SDK-native "
        "streaming bridge between LangGraph and Telegram. ADR-0015 pins this; "
        "rename or relocation must be reflected in the ADR and this contract."
    )


def test_stream_agent_to_draft_uses_sdk_native_astream() -> None:
    """The helper must call ``<agent>.astream(...)`` — the LangGraph SDK streaming API.

    A regression that replaces this with a manual loop, ``ainvoke`` polling,
    or a custom ``DraftStreamer.run(...)`` wrapper would fail this assertion.
    """
    tree = ast.parse(_source(STREAMING_MODULE))
    fn = _function(tree, "_stream_agent_to_draft")
    assert fn is not None, "guarded by test_stream_agent_to_draft_is_defined"

    found_astream_call = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "astream":
            found_astream_call = True
            break

    assert found_astream_call, (
        "_stream_agent_to_draft must call <agent>.astream(...) — the SDK-native "
        "LangGraph streaming API (ADR-0015). A custom polling loop or wrapper "
        "is forbidden by the SDK-native baseline."
    )


def test_stream_agent_to_draft_passes_stream_mode_kwarg() -> None:
    """The helper must drive ``astream`` via the ``stream_mode=`` kwarg (SDK-native control).

    LangGraph's documented API for selecting which event types stream is
    ``agent.astream(payload, config=config, stream_mode=[...])``. This
    contract pins that pattern so the streaming path keeps using
    SDK-defined modes (``"messages"`` and ``"values"`` at the time of
    writing) instead of subscribing to every event and filtering manually.
    """
    source = _source(STREAMING_MODULE)
    # Single-line or multi-line astream() call with stream_mode=
    pattern = re.compile(r"\.astream\s*\(.*?stream_mode\s*=", re.DOTALL)
    assert pattern.search(source), (
        "_stream_agent_to_draft must invoke astream() with the stream_mode= "
        "keyword argument so streaming behaviour is controlled via the "
        "SDK-native API surface (ADR-0015)."
    )


def test_legacy_draft_streamer_module_is_absent() -> None:
    """``telegram_bot/services/draft_streamer.py`` was removed; it must stay removed.

    The audit issue #1538 listed ``DraftStreamer`` as a tracked migration
    target; the migration was completed before #1538 was triaged (the file
    no longer exists on dev). This pins the absence so re-introducing the
    legacy custom-streaming abstraction triggers a contract failure.
    """
    assert not LEGACY_DRAFT_STREAMER.exists(), (
        f"{LEGACY_DRAFT_STREAMER.relative_to(REPO_ROOT)} was removed in favour of "
        "the SDK-native streaming path in telegram_bot/_bot_streaming.py "
        "(ADR-0015). Re-introducing it would re-create the parallel custom "
        "streaming surface that the migration retired."
    )


def test_no_draft_streamer_class_anywhere_in_production() -> None:
    """No production module may declare ``class DraftStreamer``.

    Searches the entire production tree (``src/`` + ``telegram_bot/`` +
    ``mini_app/``) for a class definition matching the legacy abstraction.
    Tests are excluded — a fixture or a snapshot helper is allowed to use
    the name.
    """
    forbidden = re.compile(r"^\s*class\s+DraftStreamer\b", re.MULTILINE)
    production_roots = [
        REPO_ROOT / "src",
        REPO_ROOT / "telegram_bot",
        REPO_ROOT / "mini_app",
    ]
    excluded_parts = {".venv", "__pycache__", "node_modules", ".mypy_cache"}

    offenders: list[str] = []
    for root in production_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if excluded_parts.intersection(path.relative_to(REPO_ROOT).parts):
                continue
            text = path.read_text(encoding="utf-8")
            for match in forbidden.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"  {path.relative_to(REPO_ROOT)}:{line_no}")

    assert not offenders, (
        "Found a `class DraftStreamer` definition in production code. The "
        "SDK-native baseline (ADR-0015) requires direct use of "
        "`agent.astream(stream_mode=[...])` from LangGraph instead of a "
        "custom streaming wrapper. Files:\n" + "\n".join(offenders)
    )
