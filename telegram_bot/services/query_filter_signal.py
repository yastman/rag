from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_CITY_RE = re.compile(
    r"\b("
    r"несеб\w*"
    r"|варн\w*"
    r"|бургас\w*"
    r"|солнечн\w*\s+берег\w*"
    r"|свети\s+влас\w*"
    r"|свят\w+\s+влас\w*"
    r"|эленит\w*"
    r"|помори\w*"
    r"|созопол\w*"
    r"|софи\w*"
    r")\b",
    re.IGNORECASE,
)
_PRICE_RE = re.compile(r"\b(до|от|дешевле|дороже|меньше|больше)\s*\d", re.IGNORECASE)
_ROOMS_RE = re.compile(
    r"\b("
    r"студи\w*"
    r"|однушк\w*"
    r"|двушк\w*"
    r"|тр[её]шк\w*"
    r"|\d+[\s-]*комн\w*"
    r"|(?:одно|дв(?:у|ух)|тр[её]х|четыр[её]х|пяти)комнат\w*"
    r")\b",
    re.IGNORECASE,
)
_AREA_RE = re.compile(r"\b\d+\s*(м2|м²|кв)\b", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"\b(евро|€|eur|доллар|usd)\b", re.IGNORECASE)
_FLOOR_RE = re.compile(r"\b(?:\d+\s*этаж\w*|на\s+\d+)\b", re.IGNORECASE)
_DISTANCE_TO_SEA_RE = re.compile(
    r"\b(?:"
    r"перв\w+\s+лини\w+"
    r"|у\s+моря"
    r"|до\s+\d+\s*(?:м|метр\w*).*?(?:до\s+)?(?:моря|пляжа)"
    r"|не\s+дальше\s+\d+\s*(?:м|метр\w*)"
    r"|в\s+\d+\s*(?:м|метр\w*).*?от\s+(?:моря|пляжа)"
    r"|(?:моря|пляжа).*?\d+\s*(?:м|метр\w*)"
    r")\b",
    re.IGNORECASE,
)
_MAINTENANCE_RE = re.compile(
    r"\b(?:"
    r"(?:такс\w*\s+поддержк\w*|поддержк\w*)[^\d]{0,20}\d+"
    r"|(?:поддержк\w*|такс\w*).*?(?:до|меньше)\s+\d+"
    r"|(?:до|меньше)\s+\d+.*?(?:поддержк\w*|такс\w*)"
    r"|низк\w+\s+(?:поддержк\w*|такс\w*)"
    r"|такс\w*\s+\d+"
    r")\b",
    re.IGNORECASE,
)
_BATHROOMS_RE = re.compile(
    r"\b(?:\d+\s*санузл\w*|(?:один|одна|два|две|двумя|три)\s+сануз\w*)\b",
    re.IGNORECASE,
)
_FURNITURE_RE = re.compile(
    r"\b(?:с\s+мебелью|мебел\w*|меблирован\w*|обставлен\w*)\b",
    re.IGNORECASE,
)
_YEAR_ROUND_RE = re.compile(
    r"\b(?:круглогодич\w*|круглый\s+год|зимой\s+(?:можно|работает|жить)|year[- ]round)\b",
    re.IGNORECASE,
)


@dataclass(slots=True, frozen=True)
class QueryFilterSignal:
    is_filter_sensitive: bool
    reasons: tuple[str, ...]


def detect_filter_sensitive_query(query: str) -> QueryFilterSignal:
    reasons: list[str] = []
    if _CITY_RE.search(query):
        reasons.append("city")
    if _PRICE_RE.search(query):
        reasons.append("price")
    if _ROOMS_RE.search(query):
        reasons.append("rooms")
    if _AREA_RE.search(query):
        reasons.append("area")
    if _CURRENCY_RE.search(query):
        reasons.append("currency")
    if _FLOOR_RE.search(query):
        reasons.append("floor")
    if _DISTANCE_TO_SEA_RE.search(query):
        reasons.append("distance_to_sea")
    if _MAINTENANCE_RE.search(query):
        reasons.append("maintenance")
    if _BATHROOMS_RE.search(query):
        reasons.append("bathrooms")
    if _FURNITURE_RE.search(query):
        reasons.append("furniture")
    if _YEAR_ROUND_RE.search(query):
        reasons.append("year_round")
    return QueryFilterSignal(is_filter_sensitive=bool(reasons), reasons=tuple(reasons))


def build_filter_signature(filters: dict[str, Any] | None) -> str | None:
    if not isinstance(filters, dict) or not filters:
        return None
    parts: list[str] = []
    for key in sorted(filters):
        value = filters[key]
        if isinstance(value, dict):
            for nested_key in sorted(value):
                parts.append(f"{key}.{nested_key}={value[nested_key]}")
        else:
            parts.append(f"{key}={value}")
    return "|".join(parts) if parts else None
