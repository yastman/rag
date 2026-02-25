"""Load service/promotion content from YAML config (#628)."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml


_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_SUPPORTED_LOCALES = frozenset({"ru", "uk", "en"})


@functools.lru_cache(maxsize=4)
def _load_locale_config(locale: str) -> dict[str, Any]:
    """Load services_{locale}.yaml with fallback to services.yaml. Cached per locale."""
    candidates = [
        _CONFIG_DIR / f"services_{locale}.yaml",
        _CONFIG_DIR / "services.yaml",
        _CONFIG_DIR / "services_ru.yaml",
    ]
    for path in candidates:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"No services config found for locale '{locale}'")


def load_services_config(locale: str = "ru") -> dict[str, Any]:
    """Load services config for the given locale. Falls back to 'ru' for unknown locales."""
    normalized = locale if locale in _SUPPORTED_LOCALES else "ru"
    return _load_locale_config(normalized)


def get_service_card(service_key: str) -> dict[str, Any] | None:
    """Get single service config by key."""
    config = load_services_config()
    return config.get("services", {}).get(service_key)


def get_welcome_text(locale: str = "ru") -> str:
    """Get welcome message text for the given locale."""
    config = load_services_config(locale=locale)
    return config.get("welcome", {}).get("text", "Добро пожаловать!")


def get_services_menu_text(locale: str = "ru") -> str:
    """Get services submenu header text for the given locale."""
    config = load_services_config(locale=locale)
    return config.get("services_menu_text", "Выберите услугу:")


def get_menu_buttons(locale: str = "ru") -> dict[str, str]:
    """Get menu button mapping {action_id: button_text} for the given locale."""
    config = load_services_config(locale=locale)
    return config.get("menu", {})
