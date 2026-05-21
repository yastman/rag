"""SDK shape regression locks for ``instructor`` (closes #1672 / ADR-0008).

These contracts pin the project decision to:

1. Construct ``instructor`` clients **only** via
   ``instructor.from_openai(langfuse.openai.AsyncOpenAI(...))``. The
   ``instructor.from_provider("openai/...", async_client=True)`` shape silently
   strips the ``langfuse.openai`` auto-trace wrap and is forbidden in
   production code paths.

2. Defer adoption of ``create_partial`` / ``create_iterable`` streaming
   primitives until a real consumer (voice agent, Mini App live chat) ships.
   See ``docs/adr/0008-instructor-create-partial-deferred.md``.

If a future PR legitimately needs to relax either rule, update the ADR,
SDK registry entry, and these locks together — never silently.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_ROOTS = (
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
    REPO_ROOT / "mini_app",
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in PROD_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            # Exclude vendored / generated artefacts if any.
            if any(part in {".venv", "node_modules", "build", "dist"} for part in path.parts):
                continue
            files.append(path)
    return files


def _calls_in(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _is_attr_call(call: ast.Call, root: str, attr: str) -> bool:
    """Return True if ``call`` is ``<...>.<attr>(...)`` and root token is ``root``."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != attr:
        return False
    # Walk down to the leftmost Name token.
    node: ast.AST = func.value
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id == root


@pytest.mark.parametrize("path", _iter_python_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_instructor_from_provider_in_production(path: Path) -> None:
    """``instructor.from_provider(...)`` must not appear in production code.

    It builds its own OpenAI client and breaks ``langfuse.openai`` auto-trace.
    Use ``instructor.from_openai(langfuse.openai.AsyncOpenAI(...))`` instead.
    """
    source = path.read_text(encoding="utf-8")
    if "instructor" not in source:
        return  # Fast path: file does not touch instructor at all.

    tree = ast.parse(source, filename=str(path))
    offenders = [
        call for call in _calls_in(tree) if _is_attr_call(call, "instructor", "from_provider")
    ]
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: forbidden `instructor.from_provider(...)` call. "
        f"See docs/adr/0008-instructor-create-partial-deferred.md."
    )


@pytest.mark.parametrize("path", _iter_python_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_instructor_streaming_primitives_in_production(path: Path) -> None:
    """``create_partial`` / ``create_iterable`` are deferred per ADR-0008.

    A future PR adopting these MUST update ADR-0008 first; this test is
    intentionally a hard lock.
    """
    source = path.read_text(encoding="utf-8")
    if "create_partial" not in source and "create_iterable" not in source:
        return

    tree = ast.parse(source, filename=str(path))
    forbidden_attrs = {"create_partial", "create_iterable"}
    offenders: list[str] = []
    for call in _calls_in(tree):
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
            offenders.append(f"line {call.lineno}: .{func.attr}(...)")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: deferred instructor streaming primitive(s) "
        f"detected: {offenders}. Update docs/adr/0008-instructor-create-partial-deferred.md "
        f"before introducing partial/iterable streaming."
    )


def test_known_instructor_call_sites_use_from_openai() -> None:
    """The two known instructor consumers must use ``instructor.from_openai(...)``.

    Drift here means a service reverted to a non-langfuse-aware construction
    path. This is a positive lock complementing
    :func:`test_no_instructor_from_provider_in_production`.

    Note: ``telegram_bot/services/llm.py`` was removed in #1541 follow-up
    (no production callers; superseded by ``generate_response.py``).
    """
    expected = [
        REPO_ROOT / "telegram_bot" / "services" / "apartment_llm_extractor.py",
        REPO_ROOT / "telegram_bot" / "services" / "query_analyzer.py",
    ]
    for path in expected:
        assert path.exists(), f"expected instructor consumer missing: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        from_openai_calls = [
            call for call in _calls_in(tree) if _is_attr_call(call, "instructor", "from_openai")
        ]
        assert from_openai_calls, (
            f"{path.relative_to(REPO_ROOT)}: expected at least one "
            f"`instructor.from_openai(...)` call; got none. "
            f"See docs/adr/0008-instructor-create-partial-deferred.md."
        )
