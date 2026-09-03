"""Core test conftest — install optional-dep stubs at configure time.

Keeps src.core.pipeline importable in CI without optional extras (pymupdf).
Uses pytest_configure/pytest_unconfigure for proper cleanup (#611).
The Docling stubs were removed together with the converter stack (#3235).
"""

import sys
from types import ModuleType


_INJECTED_MODULES: list[str] = []


def pytest_configure(config):
    """Install lightweight stubs for optional heavy deps before collection."""
    stubs = {
        "pymupdf": ModuleType("pymupdf"),
    }
    for name, mod in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = mod
            _INJECTED_MODULES.append(name)


def pytest_unconfigure(config):
    """Remove stubs we injected (leave pre-existing modules alone)."""
    for name in reversed(_INJECTED_MODULES):
        sys.modules.pop(name, None)
    _INJECTED_MODULES.clear()
