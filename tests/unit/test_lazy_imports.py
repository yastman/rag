"""Regression tests for lightweight package imports."""

from __future__ import annotations

import importlib
import sys

import pytest


def _clear_modules_safe(monkeypatch: pytest.MonkeyPatch, prefixes: tuple[str, ...]) -> None:
    """Remove modules matching prefixes using monkeypatch (auto-restored on teardown)."""
    for key in list(sys.modules.keys()):
        if key.startswith(prefixes):
            monkeypatch.delitem(sys.modules, key)


def test_src_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing src should not eagerly import heavy subpackages."""
    _clear_modules_safe(monkeypatch, ("src",))

    import src

    assert src.__version__
    assert "src.core" not in sys.modules
    assert "src.retrieval" not in sys.modules
    assert "src.ingestion" not in sys.modules


def test_unified_config_import_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing unified config should not pull writer dependencies."""
    _clear_modules_safe(monkeypatch, ("src",))

    module = importlib.import_module("src.ingestion.unified.config")
    cfg = module.UnifiedConfig()

    assert cfg is not None
    assert "src.ingestion.unified.qdrant_writer" not in sys.modules
    assert "src.ingestion.unified.targets.qdrant_hybrid_target" not in sys.modules
    assert "src.ingestion.unified.observability" not in sys.modules


def test_unified_cli_import_keeps_flow_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI import should not eagerly import flow/writer modules."""
    _clear_modules_safe(monkeypatch, ("src",))

    module = importlib.import_module("src.ingestion.unified.cli")

    assert module is not None
    assert "src.ingestion.unified.flow" not in sys.modules
    assert "src.ingestion.unified.qdrant_writer" not in sys.modules


@pytest.mark.parametrize(
    ("module_name", "attr_name", "target_module_name"),
    [
        ("src", "Settings", "src.config"),
        ("src.config", "SmallToBigMode", "src.config.constants"),
        ("src.contextualization", "ContextualizeProvider", "src.contextualization.base"),
        ("src.ingestion", "DoclingClient", "src.ingestion.docling_client"),
        ("src.ingestion.unified", "UnifiedConfig", "src.ingestion.unified.config"),
    ],
)
def test_pruned_package_exports_keep_deprecated_compatibility(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    attr_name: str,
    target_module_name: str,
) -> None:
    """Deprecated package exports should stay importable via lazy shims."""
    _clear_modules_safe(monkeypatch, ("src",))

    module = importlib.import_module(module_name)
    target_module = importlib.import_module(target_module_name)

    with pytest.deprecated_call(match="deprecated package export"):
        value = getattr(module, attr_name)

    assert value is getattr(target_module, attr_name)
    assert attr_name not in getattr(module, "__all__", ())


@pytest.mark.parametrize(
    ("import_stmt", "imported_name"),
    [
        ("from src import Settings", "Settings"),
        ("from src.config import SmallToBigMode", "SmallToBigMode"),
        ("from src.contextualization import ContextualizeProvider", "ContextualizeProvider"),
        ("from src.ingestion import DoclingClient", "DoclingClient"),
        ("from src.ingestion.unified import UnifiedConfig", "UnifiedConfig"),
    ],
)
def test_deprecated_package_exports_support_explicit_import(
    monkeypatch: pytest.MonkeyPatch,
    import_stmt: str,
    imported_name: str,
) -> None:
    """Explicit imports should continue to resolve deprecated package exports."""
    _clear_modules_safe(monkeypatch, ("src",))

    namespace: dict[str, object] = {}
    with pytest.deprecated_call(match="deprecated package export"):
        exec(import_stmt, namespace)

    assert imported_name in namespace
