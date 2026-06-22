"""Canonical home for service-content YAML loaders (#1948 slice 3, #2747).

Issue #1948 flagged that shared modules used by both the bot and other
surfaces sat under ``telegram_bot/``. This file is the canonical home for the
``services.yaml`` loader. The previous module at
``telegram_bot/services/content_loader.py`` is now a thin re-export shim
that points here, preserving the bot's existing import surface.

Layering rule (enforced by
``tests/contract/test_layering_no_telegram_bot_imports_contract.py``
and ``tests/contract/test_content_loader_path_contract.py``):

  - ``telegram_bot/`` internals may continue to use either path.

YAML payloads live under ``src/config/`` (#2747) so this shared module
does not depend on the Telegram adapter's directory layout.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


# ``src/services/content_loader.py`` → ``parents[2]`` is the repo root.
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "src" / "config"


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

    Returns dict with phone_prompt, phone_success keys.
    """
    svc = get_service_card(service_key)
    if svc:
        return svc
    return get_entry_point_config(service_key)
