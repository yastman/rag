"""Scoping contract for LangGraph `Send` adoption (closes #1670 / ADR-0009).

These contracts pin two things:

1. There is exactly **one** SDK-native primitive for parallel fan-out inside
   the graph: ``langgraph.types.Send``. If a future PR adopts fan-out via a
   different mechanism (custom helper, ``asyncio.gather`` inside a graph
   node, etc.), this test fails fast and forces an ADR update.

2. Until a pilot ships, no graph code uses ``Send``. This is the "scoping,
   not adoption" lock from ADR-0009: the moment ``Send`` lands in
   ``telegram_bot/graph/`` or ``telegram_bot/agents/``, the pilot must also
   add a focused topology test under ``tests/unit/graph/`` and update
   ADR-0009 to "Adopted".

If a future PR legitimately needs to relax either rule, update the ADR
and these locks together — never silently.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
GRAPH_ROOTS = (
    REPO_ROOT / "telegram_bot" / "graph",
    REPO_ROOT / "telegram_bot" / "agents",
    REPO_ROOT / "src" / "graph",
)


def _iter_graph_files() -> list[Path]:
    files: list[Path] = []
    for root in GRAPH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in {".venv", "build", "dist"} for part in path.parts):
                continue
            files.append(path)
    return files


def _imports_from(tree: ast.AST, module: str) -> list[ast.ImportFrom]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == module
    ]


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


@pytest.mark.parametrize("path", _iter_graph_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_send_fanout_only_via_langgraph_types(path: Path) -> None:
    """If a graph file imports a ``Send`` symbol it must come from ``langgraph.types``.

    A custom ``Send`` helper from anywhere else in the project is forbidden
    — one canonical fan-out primitive only. See ADR-0009.
    """
    source = path.read_text(encoding="utf-8")
    if "Send" not in source:
        return  # Fast path.

    tree = ast.parse(source, filename=str(path))
    sends_imported = []
    for imp in (n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)):
        for alias in imp.names:
            if alias.name == "Send" or alias.asname == "Send":
                sends_imported.append((imp.module, alias.name, imp.lineno))

    bad = [
        (mod, name, lineno) for (mod, name, lineno) in sends_imported if mod != "langgraph.types"
    ]
    assert not bad, (
        f"{path.relative_to(REPO_ROOT)}: `Send` imported from a non-canonical "
        f"module {bad}. Only `from langgraph.types import Send` is allowed. "
        f"See docs/adr/0009-langgraph-send-fanout-scoping.md."
    )


def test_scoping_lock_send_not_yet_adopted() -> None:
    """ADR-0009 is currently *scoping*, not *adopted*.

    The first PR that introduces ``Send`` in graph code MUST also flip this
    test (replace with a topology assertion that the new fan-out exists)
    AND update ADR-0009 status to "Adopted".

    We assert the scoping invariant strictly: zero ``langgraph.types.Send``
    imports and zero ``Send(...)`` calls anywhere in the graph layer.
    """
    offenders: list[str] = []
    for path in _iter_graph_files():
        source = path.read_text(encoding="utf-8")
        if "Send" not in source:
            continue
        tree = ast.parse(source, filename=str(path))

        # Imports of Send from langgraph.types.
        for imp in _imports_from(tree, "langgraph.types"):
            for alias in imp.names:
                if alias.name == "Send":
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{imp.lineno} imports langgraph.types.Send"
                    )

        # Direct Send(...) calls (defense-in-depth in case Send is rebound).
        for call in _calls(tree):
            func = call.func
            if isinstance(func, ast.Name) and func.id == "Send":
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{call.lineno} calls Send(...)")

    assert not offenders, (
        "ADR-0009 is currently 'Scoping (no production adoption yet)'. "
        "The following graph-layer files already use `Send`:\n  - "
        + "\n  - ".join(offenders)
        + "\nIf this is the pilot landing, update "
        "docs/adr/0009-langgraph-send-fanout-scoping.md to status 'Accepted' "
        "and replace this scoping lock with a topology assertion that the "
        "new fan-out exists and is gated by the pilot's config flag."
    )
