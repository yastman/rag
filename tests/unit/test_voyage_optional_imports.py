# tests/unit/test_voyage_optional_imports.py
"""Regression lock: voyageai must not be imported in the live runtime (#2631).

After #2631, VoyageService is archived and no live code path imports voyageai.
These tests verify that voyageai does not appear in any live module.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Live modules that previously consumed Voyage — must now be clean.
DEFAULT_RUNTIME_VOYAGE_CONSUMERS = [
    "src.ingestion.unified.qdrant_writer",
]


def _module_path(dotted: str) -> Path:
    parts = dotted.split(".")
    candidate = REPO_ROOT.joinpath(*parts).with_suffix(".py")
    if candidate.exists():
        return candidate
    pkg = REPO_ROOT.joinpath(*parts) / "__init__.py"
    if pkg.exists():
        return pkg
    raise FileNotFoundError(f"cannot locate source for {dotted}")


def _voyage_symbols_in_source(source: str) -> list[str]:
    """Return any voyageai-related imports found at any scope in the source."""
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "voyage" in alias.name.lower():
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {a.name for a in node.names}
            if "voyage" in module.lower():
                bad.append(f"from {module} import {sorted(names)}")
            if any("voyage" in n.lower() for n in names) and "src.services" in module:
                bad.append(
                    f"from {module} import {sorted(n for n in names if 'voyage' in n.lower())}"
                )
    return bad


def test_qdrant_writer_has_no_voyage_reference() -> None:
    """qdrant_writer.py must have no Voyage import at any scope (#2631)."""
    src_path = _module_path("src.ingestion.unified.qdrant_writer")
    bad = _voyage_symbols_in_source(src_path.read_text(encoding="utf-8"))
    assert not bad, (
        f"qdrant_writer.py still references voyage: {bad}. "
        "Voyage path was removed in #2631; BGE-M3 is the sole embedding path."
    )


def test_services_init_has_no_voyage_service() -> None:
    """src/services/__init__.py must not export VoyageService (#2631)."""
    src_path = _module_path("src.services")
    source = src_path.read_text(encoding="utf-8")
    assert "VoyageService" not in source, (
        "src/services/__init__.py still references VoyageService (#2631)."
    )


def test_telegram_bot_services_init_has_no_voyage_service() -> None:
    """telegram_bot/services/__init__.py must not export VoyageService (#2631)."""
    src_path = REPO_ROOT / "telegram_bot" / "services" / "__init__.py"
    source = src_path.read_text(encoding="utf-8")
    assert "VoyageService" not in source, (
        "telegram_bot/services/__init__.py still references VoyageService (#2631)."
    )


def test_default_bot_runtime_imports_skip_voyageai() -> None:
    """Runtime lock: importing telegram_bot.services does not pull in voyageai."""
    sys.modules.pop("voyageai", None)
    importlib.import_module("telegram_bot.services")
    assert "voyageai" not in sys.modules, (
        "Importing telegram_bot.services pulled in voyageai (#2631). "
        "Voyage path was removed; voyageai must not be loaded."
    )
