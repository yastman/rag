"""Contract: bot.py must not import private symbols from runtime internals.

Pins issue #2746 (REFACTOR: telegram_bot/bot.py imports private _BLOCKED_RESPONSE
from a runtime node module) and #3207 (classify/guard moved to
``src.runtime.routing`` / ``src.runtime.safety``).

Adapter layer (telegram_bot/) must not reach into internal routing/safety
implementation details (private underscore-prefixed symbols). The historical
``src.runtime.graph.nodes`` prefix stays forbidden so the guard survives any
stray legacy imports.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BOT_PATH = REPO_ROOT / "telegram_bot" / "bot.py"

# Internal runtime module prefixes whose private symbols are off-limits to adapters.
_INTERNAL_PREFIXES = (
    "src.runtime.routing",
    "src.runtime.safety",
    "src.runtime.graph.nodes",
)


def _internal_private_imports(path: Path) -> list[str]:
    """Return list of private symbols imported from internal runtime modules."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith(_INTERNAL_PREFIXES)
        ):
            for alias in node.names:
                name = alias.name
                if name.startswith("_"):
                    violations.append(f"{node.module}.{name}")
    return violations


def test_bot_does_not_import_private_runtime_internals() -> None:
    """bot.py must not import private (_-prefixed) symbols from runtime internals."""
    violations = _internal_private_imports(BOT_PATH)
    assert not violations, (
        f"#2746/#3207: bot.py imports private runtime internals: {violations}. "
        "Expose needed constants via src.runtime.services or src.runtime.pipeline."
    )


def test_blocked_response_public_in_rag_core() -> None:
    """BLOCKED_RESPONSE must be importable from src.runtime.services.rag_core."""
    from src.runtime.services.rag_core import BLOCKED_RESPONSE

    assert isinstance(BLOCKED_RESPONSE, str)
    assert len(BLOCKED_RESPONSE) > 0
