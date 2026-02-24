"""Load service/promotion content from YAML config (#628)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml


_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


@functools.lru_cache(maxsize=1)
def load_services_config() -> dict[str, Any]:
    """Load services.yaml config. Cached after first call."""
    path = _CONFIG_DIR / "services.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_service_card(service_key: str) -> dict[str, Any] | None:
    """Get single service config by key."""
    config = load_services_config()
    return config.get("services", {}).get(service_key)


def get_welcome_text() -> str:
    """Get welcome message text."""
    config = load_services_config()
    return config.get("welcome", {}).get("text", "Добро пожаловать!")


def get_services_menu_text() -> str:
    """Get services submenu header text."""
    config = load_services_config()
    return config.get("services_menu_text", "Выберите услугу:")
