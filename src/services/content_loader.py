"""Canonical home for service-content YAML loaders (#1948 slice 3).

Issue #1948 ("``src/api`` and ``mini_app`` import from ``telegram_bot``")
flagged that shared modules used by both the bot and the Mini App backend
sit under ``telegram_bot/``. This file is the canonical home for the
``services.yaml`` / ``mini_app.yaml`` loaders. The previous module at
``telegram_bot/services/content_loader.py`` is now a thin re-export shim
that points here, preserving the bot's existing import surface.

Layering rule (enforced by
``tests/contract/test_layering_no_telegram_bot_imports_contract.py``
in PR #2018 once that lands, and by
``tests/contract/test_issue_1948_content_loader_slice_contract.py``
right now):

  - ``mini_app/`` imports from ``src.services.content_loader``.
  - ``telegram_bot/`` internals may continue to use either path.

Filesystem caveat: the YAML payloads themselves still live under
``telegram_bot/config/`` because they are bot-specific UI/CRM content.
The canonical path is computed relative to the repository root so this
module does not import ``telegram_bot``. Moving the YAMLs out of
``telegram_bot/config/`` is out of scope for #1948 slice 3 and tracked
as a follow-up under #1948.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


# Resolve the bot's config directory relative to the repository root.
# ``src/services/content_loader.py`` → ``parents[2]`` is the repo root.
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "telegram_bot" / "config"


@functools.lru_cache(maxsize=1)
def load_services_config() -> dict[str, Any]:
    """Load services.yaml structured config. Cached."""
    path = _CONFIG_DIR / "services.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]
    raise FileNotFoundError("services.yaml not found")


def get_service_card(service_key: str) -> dict[str, Any] | None:
    """Get single service config by key."""
    config = load_services_config()
    return config.get("services", {}).get(service_key)  # type: ignore[no-any-return]


def get_promotions() -> list[dict[str, Any]]:
    """Get promotions list from config."""
    config = load_services_config()
    return config.get("promotions", [])  # type: ignore[no-any-return]


def get_entry_point_config(key: str) -> dict[str, Any] | None:
    """Get entry point config by key (viewing, manager)."""
    config = load_services_config()
    return config.get("entry_points", {}).get(key)  # type: ignore[no-any-return]


def get_phone_config(service_key: str) -> dict[str, Any] | None:
    """Get phone collector config — checks services first, then entry_points.

    Returns dict with crm_title, phone_prompt, phone_success keys.
    """
    svc = get_service_card(service_key)
    if svc:
        return svc
    return get_entry_point_config(service_key)


def load_mini_app_config() -> dict[str, Any]:
    """Load Mini App configuration (questions + experts) from YAML."""
    path = _CONFIG_DIR / "mini_app.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]
