"""Shared apartment-related constants used by dialogs and extractors."""

from __future__ import annotations

from src.runtime.domain_defaults import DEMO_CITIES


# Filter-dialog city options: exactly the cities that exist in the demo seed
# (#3203). Offering a city with no listings would advertise an empty filter.
APARTMENT_CITY_OPTIONS: list[tuple[str, str]] = [(city, city) for city in DEMO_CITIES]

APARTMENT_CITY_NAMES: list[str] = [
    "Солнечный берег",
    "Свети Влас",
    "Элените",
    "Несебр",
    "Бургас",
    "Варна",
    "София",
    "Поморие",
    "Созополь",
]

APARTMENT_CITY_ALIASES: dict[str, str] = {
    "солнечный берег": "Солнечный берег",
    "солнечного берега": "Солнечный берег",
    "солнечном берегу": "Солнечный берег",
    "солнечному берегу": "Солнечный берег",
    "sunny beach": "Солнечный берег",
    "санни бич": "Солнечный берег",
    "свети влас": "Свети Влас",
    "свети власе": "Свети Влас",
    "свети власа": "Свети Влас",
    "святой влас": "Свети Влас",
    "святом власе": "Свети Влас",
    "святого власа": "Свети Влас",
    "элените": "Элените",
    "elenite": "Элените",
}

APARTMENT_CITY_ALIASES_SORTED = sorted(APARTMENT_CITY_ALIASES, key=len, reverse=True)
