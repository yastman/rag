"""Regression tests for lightweight package imports."""

from __future__ import annotations

import importlib
import sys


def _clear_modules(prefixes: tuple[str, ...]) -> None:
    for key in list(sys.modules.keys()):
        if key.startswith(prefixes):
            sys.modules.pop(key, None)


def test_src_import_is_lazy() -> None:
    """Importing src should not eagerly import heavy subpackages."""
    _clear_modules(("src",))

    import src

    assert src.__version__
    assert "src.core" not in sys.modules
    assert "src.retrieval" not in sys.modules
    assert "src.ingestion" not in sys.modules


def test_unified_config_import_is_lazy() -> None:
    """Importing unified config should not pull writer dependencies."""
    _clear_modules(("src",))

    module = importlib.import_module("src.ingestion.unified.config")
    cfg = module.UnifiedConfig()

    assert cfg is not None
    assert "src.ingestion.unified.qdrant_writer" not in sys.modules
    assert "src.ingestion.unified.targets.qdrant_hybrid_target" not in sys.modules
