"""Drift guard for #1948 slice 3 — content_loader migration to ``src/``.

Issue #1948 ("``src/api`` and ``mini_app`` import from ``telegram_bot``")
proposed migrating shared modules out of ``telegram_bot/`` so the layering
arrows go the right way. Phone-utils landed in PR #2018 (slice 1).
Observability re-export landed in PR #2020 (slice 2).

This contract pins **slice 3**: ``content_loader`` becomes a first-class
citizen under ``src/services/`` and ``telegram_bot/services/content_loader.py``
becomes a thin re-export shim so existing bot internals keep working unchanged.

Mini App is permanently archived — tests 4 and 5 (mini_app import assertions)
were removed.

Asserted invariants:

  1. ``src/services/content_loader.py`` exists and is a real Python module
     (not just an empty file).
  2. ``src/services/content_loader.py`` exposes the canonical public API:
     ``load_services_config``, ``get_service_card``, ``get_promotions``,
     ``get_entry_point_config``, ``get_phone_config``.
  3. ``telegram_bot/services/content_loader.py`` re-exports the same
     callables with object-identity (``is``-equal) — proves the bot path
     keeps the canonical implementation, not a copy.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_MODULE = REPO_ROOT / "src" / "services" / "content_loader.py"
SHIM_MODULE = REPO_ROOT / "telegram_bot" / "services" / "content_loader.py"

PUBLIC_API: tuple[str, ...] = (
    "load_services_config",
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
# 4. mini_app/api.py imports — REMOVED (Mini App permanently archived)
# 5. Runtime parity test — REMOVED (Mini App permanently archived)
# ---------------------------------------------------------------------------
