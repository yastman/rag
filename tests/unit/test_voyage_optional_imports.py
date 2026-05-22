# tests/unit/test_voyage_optional_imports.py
"""Regression locks: voyageai must remain optional (#1773).

These tests prove that the default bot/retrieval/ingestion runtime does NOT
import `voyageai` at module load time. Voyage is an optional extra; importing
it eagerly under Python 3.14 breaks base test collection (`voyageai` ships
Pydantic V1 models incompatible with 3.14 — see issue body).

The protection works in two layers:
  1. Source-level: AST scan for top-level `import voyageai` / `from voyageai`
     in every default-runtime module that consumes Voyage. This catches the
     regression even when `voyageai` happens to be installed in CI.
  2. Runtime-level: import the module in a sandboxed `sys.modules` and assert
     `voyageai` did not get pulled in transitively.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# Modules that must NOT import voyageai at module load time. Each is on the
# default runtime/ingestion path; voyage usage inside them must be lazy.
DEFAULT_RUNTIME_VOYAGE_CONSUMERS = [
    "src.ingestion.unified.qdrant_writer",
    "src.ingestion.cocoindex_flow",
    "src.models.contextualized_embedding",
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


def _toplevel_imports(source: str) -> set[str]:
    """Return the set of fully-qualified module names imported at module top
    level (i.e. ignoring imports nested inside functions, methods, or
    conditional `if/else` blocks at deeper scope)."""
    tree = ast.parse(source)
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def _toplevel_voyage_symbols(source: str) -> list[str]:
    """Return top-level imports that pull voyageai directly or transitively.

    Catches both `import voyageai` and `from telegram_bot.services import
    VoyageService`-style transitive triggers (the lazy `__getattr__` in
    `telegram_bot/services/__init__.py` resolves at the from-import site,
    so the import is *not* deferred from the consumer's perspective).
    """
    tree = ast.parse(source)
    bad: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "voyageai":
                    bad.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {a.name for a in node.names}
            if module.split(".")[0] == "voyageai":
                bad.append(f"from {module} import {sorted(names)}")
            if module == "telegram_bot.services" and "VoyageService" in names:
                bad.append("from telegram_bot.services import VoyageService")
            if module == "telegram_bot.services.voyage":
                bad.append(f"from {module} import {sorted(names)}")
    return bad


@pytest.mark.parametrize("dotted", DEFAULT_RUNTIME_VOYAGE_CONSUMERS)
def test_module_has_no_toplevel_voyage_import(dotted: str) -> None:
    """Static lock: no top-level Voyage import in default-runtime consumers.

    Regression for #1773: if a future change reintroduces a top-level
    `import voyageai`, `from voyageai import ...`, or
    `from telegram_bot.services import VoyageService` in any of these
    modules, base test collection breaks under Python 3.14 even though the
    runtime path itself never needs Voyage.
    """
    src_path = _module_path(dotted)
    bad = _toplevel_voyage_symbols(src_path.read_text(encoding="utf-8"))
    assert not bad, (
        f"{dotted} has top-level Voyage imports {bad} at {src_path}; "
        "Voyage is an optional extra (#1773). Move the import inside the "
        "function/method that actually instantiates a Voyage client."
    )


def test_default_bot_runtime_imports_skip_voyageai() -> None:
    """Runtime lock: importing telegram_bot does not pull in voyageai.

    `telegram_bot/services/__init__.py` already uses lazy `__getattr__`, so
    `import telegram_bot.services` should not trigger voyageai. Make that
    contract explicit via a regression test.
    """
    sys.modules.pop("voyageai", None)
    importlib.import_module("telegram_bot.services")
    assert "voyageai" not in sys.modules, (
        "Importing telegram_bot.services pulled in voyageai. Voyage is "
        "optional (#1773); access VoyageService only via attribute lookup "
        "from a callsite that needs it."
    )


def test_voyage_extra_declared_in_root_pyproject() -> None:
    """Root pyproject must expose `voyage` as an optional extra (not base)."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # voyageai must not appear in the [project] dependencies block.
    deps_block = pyproject.split("[project.optional-dependencies]", 1)[0]
    assert "voyageai" not in deps_block, (
        "voyageai is back in base [project.dependencies] (#1773 regression)."
    )
    # And it must appear in the [project.optional-dependencies] section
    # under a `voyage` extra.
    optional_block = pyproject.split("[project.optional-dependencies]", 1)[1]
    assert "voyage = [" in optional_block, "voyage extra missing from pyproject.toml"
    assert "voyageai" in optional_block


def test_voyage_extra_declared_in_telegram_bot_pyproject() -> None:
    """telegram_bot pyproject must expose voyage as an optional extra."""
    pyproject = (REPO_ROOT / "telegram_bot" / "pyproject.toml").read_text(encoding="utf-8")
    deps_block = pyproject.split("[project.optional-dependencies]", 1)[0]
    assert "voyageai" not in deps_block, (
        "voyageai is back in telegram_bot base dependencies (#1773 regression)."
    )
    optional_block = pyproject.split("[project.optional-dependencies]", 1)[1]
    assert "voyage = [" in optional_block
    assert "voyageai" in optional_block
