"""Drift guard for #1948 slice 3 — content_loader migration to ``src/``.

Issue #1948 ("``src/api`` and ``mini_app`` import from ``telegram_bot``")
proposed migrating shared modules out of ``telegram_bot/`` so the layering
arrows go the right way. Phone-utils landed in PR #2018 (slice 1).
Observability re-export landed in PR #2020 (slice 2).

This contract pins **slice 3**: ``content_loader`` becomes a first-class
citizen under ``src/services/`` and ``mini_app/api.py`` imports from there.
``telegram_bot/services/content_loader.py`` becomes a thin re-export shim
so existing bot internals keep working unchanged.

Asserted invariants:

  1. ``src/services/content_loader.py`` exists and is a real Python module
     (not just an empty file).
  2. ``src/services/content_loader.py`` exposes the canonical public API:
     ``load_services_config``, ``load_mini_app_config``, ``get_service_card``,
     ``get_promotions``, ``get_entry_point_config``, ``get_phone_config``.
  3. ``telegram_bot/services/content_loader.py`` re-exports the same
     callables with object-identity (``is``-equal) — proves the bot path
     keeps the canonical implementation, not a copy.
  4. ``mini_app/api.py`` imports ``load_mini_app_config`` from
     ``src.services.content_loader`` (no ``telegram_bot.services.content_loader``
     import in mini_app).
  5. The canonical loader and the shim each load the same YAML payload
     when the canonical config directory is present.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_MODULE = REPO_ROOT / "src" / "services" / "content_loader.py"
SHIM_MODULE = REPO_ROOT / "telegram_bot" / "services" / "content_loader.py"
MINI_APP_API = REPO_ROOT / "mini_app" / "api.py"

PUBLIC_API: tuple[str, ...] = (
    "load_services_config",
    "load_mini_app_config",
    "get_service_card",
    "get_promotions",
    "get_entry_point_config",
    "get_phone_config",
)


# ---------------------------------------------------------------------------
# 1. Canonical home exists
# ---------------------------------------------------------------------------


def test_canonical_content_loader_exists() -> None:
    assert SRC_MODULE.exists(), (
        f"#1948 slice 3: expected {SRC_MODULE.relative_to(REPO_ROOT)} to be the "
        "canonical home for content loading."
    )
    assert SRC_MODULE.read_text().strip(), f"{SRC_MODULE.relative_to(REPO_ROOT)} must not be empty."


# ---------------------------------------------------------------------------
# 2. Canonical API surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PUBLIC_API)
def test_canonical_module_exposes_public_api(name: str) -> None:
    canonical = importlib.import_module("src.services.content_loader")
    assert hasattr(canonical, name), (
        f"src.services.content_loader.{name} missing — "
        "this is part of the #1948 slice-3 public API."
    )
    assert callable(getattr(canonical, name)), (
        f"src.services.content_loader.{name} must be callable."
    )


# ---------------------------------------------------------------------------
# 3. telegram_bot shim keeps object-identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PUBLIC_API)
def test_telegram_bot_shim_re_exports_canonical(name: str) -> None:
    canonical = importlib.import_module("src.services.content_loader")
    shim = importlib.import_module("telegram_bot.services.content_loader")
    assert getattr(shim, name) is getattr(canonical, name), (
        f"telegram_bot.services.content_loader.{name} must be the SAME object as "
        f"src.services.content_loader.{name} (re-export shim, not a copy)."
    )


# ---------------------------------------------------------------------------
# 4. mini_app/api.py imports from src/, not telegram_bot/
# ---------------------------------------------------------------------------


def _ast_import_modules(path: Path) -> list[str]:
    """Return all dotted module paths imported by ``path`` (top + ImportFrom)."""
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


def test_mini_app_api_imports_content_loader_from_src() -> None:
    imports = _ast_import_modules(MINI_APP_API)
    assert "src.services.content_loader" in imports, (
        f"#1948 slice 3: {MINI_APP_API.relative_to(REPO_ROOT)} must import "
        "load_mini_app_config from src.services.content_loader."
    )
    assert "telegram_bot.services.content_loader" not in imports, (
        f"#1948 slice 3 regression: {MINI_APP_API.relative_to(REPO_ROOT)} "
        "must not import telegram_bot.services.content_loader anymore."
    )


# ---------------------------------------------------------------------------
# 5. Runtime parity — both routes load the same payload
# ---------------------------------------------------------------------------


def test_canonical_and_shim_load_same_yaml_payload(tmp_path) -> None:
    """``load_services_config`` returns the cached canonical dict via either path."""
    canonical = importlib.import_module("src.services.content_loader")
    shim = importlib.import_module("telegram_bot.services.content_loader")

    # Skip cleanly if the on-repo YAML is missing in this checkout.
    services_yaml = REPO_ROOT / "telegram_bot" / "config" / "services.yaml"
    if not services_yaml.exists():
        pytest.skip("telegram_bot/config/services.yaml not present in this checkout")

    # Clear lru_cache so the first call goes through, then prove the second
    # call (via the shim) returns the same object identity.
    canonical.load_services_config.cache_clear()
    first = canonical.load_services_config()
    second = shim.load_services_config()
    assert first is second, (
        "#1948 slice 3: shim and canonical must share the same lru_cached return."
    )
