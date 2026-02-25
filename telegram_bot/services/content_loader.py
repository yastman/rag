"""Load service content from YAML config (#628)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml


_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@functools.lru_cache(maxsize=1)
def load_services_config() -> dict[str, Any]:
    """Load services.yaml structured config. Cached."""
    path = _CONFIG_DIR / "services.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    raise FileNotFoundError("services.yaml not found")


def get_service_card(service_key: str) -> dict[str, Any] | None:
    """Get single service config by key."""
    config = load_services_config()
    return config.get("services", {}).get(service_key)


def get_promotions() -> list[dict[str, Any]]:
    """Get promotions list from config."""
    config = load_services_config()
    return config.get("promotions", [])
