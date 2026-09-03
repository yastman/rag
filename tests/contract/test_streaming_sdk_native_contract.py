"""Contract: the agent streaming facade stays deleted; no custom streamer regrows (#3218).

History: ADR-0015 ("SDK-Native Baseline") pinned the LangGraph→Telegram
streaming bridge to the SDK-native ``agent.astream(stream_mode=[...])`` API in
``telegram_bot/pipeline/streaming.py::_stream_agent_to_draft``, explicitly
forbidding a custom ``DraftStreamer`` abstraction (legacy
``services/draft_streamer.py``, removed in #1671).

The streaming consumer's only runtime caller was the supervisor recovery
wrapper deleted with the imperative agent facade (#3216); #3218 removed the
facade itself. Q&A responses are sent once via ``send_message`` — there is no
token-level drafting and no ``agent.astream`` anywhere in production.

This contract pins the current state so a regression re-introducing either
``DraftStreamer``, a hand-rolled streaming loop, or the dead
``_stream_agent_to_draft`` facade fails CI loudly.

Refs ADR-0015, #1538, #1671, #3216, #3218.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STREAMING_MODULE = REPO_ROOT / "telegram_bot" / "pipeline" / "streaming.py"
LEGACY_DRAFT_STREAMER = REPO_ROOT / "telegram_bot" / "services" / "draft_streamer.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _production_python_files() -> list[Path]:
    """All .py files under production roots, noise dirs pruned."""
    roots = [REPO_ROOT / "src", REPO_ROOT / "telegram_bot"]
    noise = {".venv", "__pycache__", "node_modules", ".mypy_cache"}
    files: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if noise.intersection(path.relative_to(REPO_ROOT).parts):
                continue
            files.append(path)
    return files


def test_streaming_module_exists() -> None:
    """Sanity: the streaming module still hosts the live draft-id helper."""
    assert STREAMING_MODULE.is_file(), (
        f"Expected {STREAMING_MODULE.relative_to(REPO_ROOT)} to exist; "
        "``_new_draft_id`` lives there for the one-shot draft finalize path."
    )


def test_stream_agent_to_draft_is_gone() -> None:
    """``_stream_agent_to_draft`` was removed in #3218 and must stay removed.

    Its only runtime caller was the supervisor recovery wrapper deleted with
    the imperative agent facade (#3216); keeping the helper around implied a
    token-streaming agent path that no longer exists.
    """
    tree = ast.parse(_source(STREAMING_MODULE))
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert "_stream_agent_to_draft" not in names, (
        "telegram_bot/pipeline/streaming.py must not define _stream_agent_to_draft "
        "(#3218): there is no agent astream consumer left. Re-introduce it only "
        "together with a real streaming consumer and an ADR-0015 update."
    )


def test_no_stream_agent_to_draft_anywhere_in_production() -> None:
    """No production module may define ``_stream_agent_to_draft``."""
    pattern = re.compile(r"^\s*(async\s+)?def\s+_stream_agent_to_draft\b", re.MULTILINE)
    offenders = [path for path in _production_python_files() if pattern.search(_source(path))]
    assert not offenders, (
        "Found `_stream_agent_to_draft` definitions in production code (#3218 "
        "removed the dead streaming facade). Files: "
        + ", ".join(p.relative_to(REPO_ROOT).as_posix() for p in offenders)
    )


def test_no_astream_calls_in_production() -> None:
    """No production module may call ``.astream(...)``.

    The LangGraph agent is gone (#3216/#3218); an ``astream`` call without a
    streaming consumer contract would be dead or speculative code.
    """
    pattern = re.compile(r"\.astream\s*\(")
    offenders = [path for path in _production_python_files() if pattern.search(_source(path))]
    assert not offenders, (
        "Found `.astream(` calls in production code — the LangGraph agent "
        "streaming path was removed (#3216, #3218). Files: "
        + ", ".join(p.relative_to(REPO_ROOT).as_posix() for p in offenders)
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
        "the SDK-native streaming path (ADR-0015) and then the whole streaming "
        "facade was removed in #3218. Re-introducing it would re-create a "
        "parallel custom streaming surface with no consumer."
    )


def test_no_draft_streamer_class_anywhere_in_production() -> None:
    """No production module may declare ``class DraftStreamer``.

    Searches the production tree (``src/`` + ``telegram_bot/``) for a class
    definition matching the legacy abstraction.
    Tests are excluded — a fixture or a snapshot helper is allowed to use
    the name.
    """
    forbidden = re.compile(r"^\s*class\s+DraftStreamer\b", re.MULTILINE)
    offenders: list[str] = []
    for path in _production_python_files():
        text = _source(path)
        for match in forbidden.finditer(text):
            line_no = text[: match.start()].count("\n") + 1
            offenders.append(f"  {path.relative_to(REPO_ROOT)}:{line_no}")

    assert not offenders, (
        "Found a `class DraftStreamer` definition in production code. The "
        "streaming facade was removed in #3218; do not reintroduce a custom "
        "streaming wrapper. Files:\n" + "\n".join(offenders)
    )
