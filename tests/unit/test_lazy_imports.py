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


def test_unified_cli_import_keeps_flow_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI import should not eagerly import flow/writer modules."""
    _clear_modules_safe(monkeypatch, ("src",))

    module = importlib.import_module("src.ingestion.unified.cli")

    assert module is not None
    assert "src.ingestion.unified.flow" not in sys.modules
    assert "src.ingestion.unified.qdrant_writer" not in sys.modules


@pytest.mark.parametrize(
    ("name", "owner"),
    [
        ("BGEM3Client", "src.services.bge_m3_client"),
        ("BGEM3SyncClient", "src.services.bge_m3_client"),
        ("ExpandedChunk", "src.runtime.services.small_to_big"),
        ("QdrantService", "src.runtime.services.qdrant"),
        ("SmallToBigService", "src.runtime.services.small_to_big"),
    ],
)
def test_telegram_services_exports_resolve_to_live_owners(name: str, owner: str) -> None:
    import telegram_bot.services as services

    assert name in services.__all__
    assert getattr(services, name) is getattr(importlib.import_module(owner), name)
