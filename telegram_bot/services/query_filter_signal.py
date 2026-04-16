from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_CITY_RE = re.compile(r"\b(несеб\w*|варн\w*|бургас\w*|солнечн\w*\s+берег\w*)\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"\b(до|от|дешевле|дороже|меньше|больше)\s*\d", re.IGNORECASE)
_ROOMS_RE = re.compile(r"\b(студия|однушк|двушк|тр[её]шк|\d+\s*комн)\b", re.IGNORECASE)
_AREA_RE = re.compile(r"\b\d+\s*(м2|м²|кв)\b", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"\b(евро|€|eur|доллар|usd)\b", re.IGNORECASE)


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
