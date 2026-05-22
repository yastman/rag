"""Load service content from YAML config (#628)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


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
