"""Contract: bot.py must not import private symbols from src.runtime.graph.nodes.

Pins issue #2746 (REFACTOR: telegram_bot/bot.py imports private _BLOCKED_RESPONSE
from src.runtime graph node).

Adapter layer (telegram_bot/) must not reach into internal graph node
implementation details (private underscore-prefixed symbols).
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"


def _graph_node_private_imports(path: Path) -> list[str]:
    """Return list of private symbols imported from src.runtime.graph.nodes.*"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("src.runtime.graph.nodes")
        ):
            for alias in node.names:
                name = alias.name
                if name.startswith("_"):
                    violations.append(f"{node.module}.{name}")
    return violations


def test_bot_does_not_import_private_graph_node_symbols() -> None:
    """bot.py must not import private (_-prefixed) symbols from src.runtime.graph.nodes.*"""
    violations = _graph_node_private_imports(BOT_PATH)
    assert not violations, (
        f"#2746: bot.py imports private graph node symbols: {violations}. "
        "Expose needed constants via src.runtime.services or src.runtime.pipeline."
    )


def test_blocked_response_public_in_rag_core() -> None:
    """BLOCKED_RESPONSE must be importable from src.runtime.services.rag_core."""
    from src.runtime.services.rag_core import BLOCKED_RESPONSE

    assert isinstance(BLOCKED_RESPONSE, str)
    assert len(BLOCKED_RESPONSE) > 0
