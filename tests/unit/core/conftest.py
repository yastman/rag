"""Core test conftest — install optional-dep stubs at configure time.

Keeps src.core.pipeline importable in CI without ingest extras (pymupdf, docling).
Uses pytest_configure/pytest_unconfigure for proper cleanup (#611).
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock


_INJECTED_MODULES: list[str] = []


def pytest_configure(config):
    """Install lightweight stubs for optional heavy deps before collection."""
    stubs = {
        "pymupdf": ModuleType("pymupdf"),
        "docling": ModuleType("docling"),
        "docling.document_converter": ModuleType("docling.document_converter"),
    }
    for name, mod in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = mod
            _INJECTED_MODULES.append(name)

    # Wire docling.document_converter.DocumentConverter mock
    converter_mod = sys.modules["docling.document_converter"]
    converter_mod.DocumentConverter = MagicMock  # type: ignore[attr-defined]
    sys.modules["docling"].document_converter = converter_mod  # type: ignore[attr-defined]


def pytest_unconfigure(config):
    """Remove stubs we injected (leave pre-existing modules alone)."""
    for name in reversed(_INJECTED_MODULES):
        sys.modules.pop(name, None)
    _INJECTED_MODULES.clear()
