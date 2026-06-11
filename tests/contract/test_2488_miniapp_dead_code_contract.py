"""Contract for #2488 Mini App dead-code cleanup."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_miniapp_deprecated_get_kommo_client_removed() -> None:
    tree = ast.parse((ROOT / "mini_app" / "phone.py").read_text(encoding="utf-8"))
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

    assert "get_kommo_client" not in names
