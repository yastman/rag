# telegram_bot/services/apartment_filter_extractor.py
"""Apartment-specific filter extraction from natural language queries (0 LLM calls)."""

from __future__ import annotations

import re
from typing import Any

from src.models.apartment import ApartmentQueryParseResult, compute_confidence
from telegram_bot.constants.apartment_constants import (
    APARTMENT_CITY_ALIASES,
    APARTMENT_CITY_ALIASES_SORTED,
    APARTMENT_CITY_NAMES,
)
from telegram_bot.services.base_filter_extractor import BaseFilterExtractor


# All canonical complex names plus RU/EN short aliases — sorted longest-first for greedy match
_COMPLEX_ALIASES: dict[str, str] = {
    # EN canonical
    "premier fort beach": "Premier Fort Beach",
    "prestige fort beach": "Prestige Fort Beach",
    "panorama fort beach": "Panorama Fort Beach",
    "marina view fort beach": "Marina View Fort Beach",
    "messambria fort beach": "Messambria Fort Beach",
    "imperial fort club": "Imperial Fort Club",
    "crown fort club": "Crown Fort Club",
    "green fort suites": "Green Fort Suites",
    "premier fort suites": "Premier Fort Suites",
    "nessebar fort residence": "Nessebar Fort Residence",
    # RU short aliases
    "премьер форт бич": "Premier Fort Beach",
    "премьер форт": "Premier Fort Beach",
    "в премьере": "Premier Fort Beach",
    "престиж форт": "Prestige Fort Beach",
    "в престиже": "Prestige Fort Beach",
    "панорама форт": "Panorama Fort Beach",
    "марина вью": "Marina View Fort Beach",
    "мессамбрия": "Messambria Fort Beach",
    "империал форт": "Imperial Fort Club",
    "кроун форт": "Crown Fort Club",
    "грин форт": "Green Fort Suites",
    "гринфорт": "Green Fort Suites",
    "премьер форт сьютс": "Premier Fort Suites",
    "несебр форт": "Nessebar Fort Residence",
}

_COMPLEX_ALIASES_SORTED = sorted(_COMPLEX_ALIASES, key=len, reverse=True)


class ApartmentFilterExtractor(BaseFilterExtractor):
    """Extract apartment filters from natural language (regex-only, 0 LLM calls)."""

    def parse(self, query: str) -> ApartmentQueryParseResult:
        """Parse query into ApartmentQueryParseResult with confidence score."""
        q = query.lower()
        consumed: list[tuple[int, int]] = []

        rooms = self._extract_rooms(q, consumed)
        min_price, max_price = self._extract_price(q, consumed)
        min_area, max_area = self._extract_area(q, consumed)
        min_floor, max_floor = self._extract_floor(q, consumed)
        complex_name = self._extract_complex(q, consumed)
        view_tags = self._extract_view(q, consumed)
        city = self._extract_city(q, consumed)

        conflicts: list[str] = []
        if min_price is not None and max_price is not None and min_price > max_price:
            conflicts.append("price_conflict:min>max")

        result = ApartmentQueryParseResult(
            rooms=rooms,
            min_price_eur=min_price,
            max_price_eur=max_price,
            min_area_m2=min_area,
            max_area_m2=max_area,
            min_floor=min_floor,
            max_floor=max_floor,
            city=city,
            complex_name=complex_name,
            view_tags=view_tags,
            semantic_query=self._build_semantic_query(query, consumed),
            conflicts=conflicts,
            raw_query=query,
        )
        return compute_confidence(result)

    # --- Rooms ---

    def _extract_rooms(self, text: str, consumed: list[tuple[int, int]]) -> int | None:
        """Extract rooms count.

        Data uses total rooms (bedrooms + living room):
        studio=0/1, 1-bed=2, 2-bed=3, 3-bed=4.
        User slang: "двушка"=2 bedrooms=rooms 3, "трёшка"=3 bedrooms=rooms 4.
        """
        # Slang → rooms (total rooms in Qdrant data)
        _slang: list[tuple[str, int]] = [
            (r"двушка", 3),
            (r"трёшка|трешка", 4),
            (r"студия", 1),
        ]
        for pat, val in _slang:
            m = re.search(pat, text)
            if m:
                consumed.append(m.span())
                return val

        # "N спален/спальни" → rooms = N + 1 (bedrooms + living room)
        m = re.search(r"(\d+)\s*спальн", text)
        if m:
            consumed.append(m.span())
            return int(m.group(1)) + 1

        # "N комнат" → rooms = N (direct)
        m = re.search(r"(\d+)\s*комнат", text)
        if m:
            consumed.append(m.span())
            return int(m.group(1))

        # "двухкомнатная" etc → total rooms (direct)
        _num_map = {"одно": 1, "дву": 2, "трех": 3, "трёх": 3, "четырех": 4, "пяти": 5}
        m = re.search(r"(одно|дву|трех|трёх|четырех|пяти)комнатн", text)
        if m:
            consumed.append(m.span())
            g = m.group(1)
            for word, num in _num_map.items():
                if g.startswith(word):
                    return num
        return None

    # --- Price ---

    def _extract_price(
        self, text: str, consumed: list[tuple[int, int]]
    ) -> tuple[float | None, float | None]:
        # Range first: "от 100к до 300к" / "от 100000 до 300000 евро"
        # Guard against area/floor phrases like "от 60 до 120 м²".
        m = re.search(r"от\s+(\d[\d\s]*к?)\s+до\s+(\d[\d\s]*к?)\s*(евро|€|eur)?", text)
        if m:
            mn_raw = m.group(1)
            mx_raw = m.group(2)
            mn = self._parse_number(mn_raw)
            mx = self._parse_number(mx_raw)
            has_currency = bool(m.group(3))
            has_k_suffix = "к" in mn_raw.lower() or "к" in mx_raw.lower()
            if mn and mx and (has_currency or has_k_suffix or mn >= 1000 or mx >= 1000):
                consumed.append(m.span())
                return (float(mn), float(mx))

        min_p: float | None = None
        max_p: float | None = None

        # Max price
        for pat in [
            r"до\s+(\d[\d\s]*к?)\s*(?:евро|€|eur)?",
            r"дешевле\s+(\d[\d\s]*к?)",
            r"меньше\s+(\d[\d\s]*к?)",
            r"не\s+дороже\s+(\d[\d\s]*к?)",
        ]:
            m2 = re.search(pat, text)
            if m2:
                val = self._parse_number(m2.group(1))
                # Prices are always >= 1000 EUR; guard against area "до 80 м²" false-matches
                if val and val >= 1000:
                    consumed.append(m2.span())
                    max_p = float(val)
                    break

        # Min price
        for pat in [
            r"от\s+(\d[\d\s]*к?)\s*(?:евро|€|eur)?",
            r"дороже\s+(\d[\d\s]*к?)",
            r"больше\s+(\d[\d\s]*к?)",
        ]:
            m3 = re.search(pat, text)
            if m3:
                val = self._parse_number(m3.group(1))
                if val and val >= 1000:
                    consumed.append(m3.span())
                    min_p = float(val)
                    break

        return (min_p, max_p)

    # --- Area ---

    def _extract_area(
        self, text: str, consumed: list[tuple[int, int]]
    ) -> tuple[float | None, float | None]:
        # Range: "от 60 до 120 м²"
        m = re.search(r"от\s+(\d+)\s+до\s+(\d+)\s*(?:м²|м2|кв\.?м?)", text)
        if m:
            consumed.append(m.span())
            return (float(m.group(1)), float(m.group(2)))

        min_a: float | None = None
        max_a: float | None = None

        m2 = re.search(r"от\s+(\d+)\s*(?:м²|м2|кв\.?м?)", text)
        if m2:
            consumed.append(m2.span())
            min_a = float(m2.group(1))

        m3 = re.search(r"до\s+(\d+)\s*(?:м²|м2|кв\.?м?)", text)
        if m3:
            consumed.append(m3.span())
            max_a = float(m3.group(1))

        return (min_a, max_a)

    # --- Floor ---

    def _extract_floor(
        self, text: str, consumed: list[tuple[int, int]]
    ) -> tuple[int | None, int | None]:
        m = re.search(r"не\s+выше\s+(\d+)\s*этаж", text)
        if m:
            consumed.append(m.span())
            return (None, int(m.group(1)))

        m2 = re.search(r"от\s+(\d+)\s*этаж", text)
        if m2:
            consumed.append(m2.span())
            return (int(m2.group(1)), None)

        m3 = re.search(r"высокий\s+этаж", text)
        if m3:
            consumed.append(m3.span())
            return (4, None)

        # Exact floor: "3 этаж"
        m4 = re.search(r"(\d+)\s*этаж", text)
        if m4:
            consumed.append(m4.span())
            n = int(m4.group(1))
            return (n, n)

        return (None, None)

    # --- Complex name ---

    def _extract_complex(self, text: str, consumed: list[tuple[int, int]]) -> str | None:
        for alias in _COMPLEX_ALIASES_SORTED:
            if alias in text:
                start = text.index(alias)
                consumed.append((start, start + len(alias)))
                return _COMPLEX_ALIASES[alias]
        return None

    # --- View ---

    def _extract_view(self, text: str, consumed: list[tuple[int, int]]) -> list[str]:
        view_patterns: list[tuple[str, list[str]]] = [
            (r"панорама\s+моря|sea\s+panorama", ["sea", "panorama"]),
            (r"с\s+видом\s+на\s+море|вид\s+на\s+море|sea\s+view|морской\s+вид", ["sea"]),
            (r"у\s+бассейна|вид\s+на\s+бассейн|pool\s+view", ["pool"]),
            (r"вид\s+на\s+сад|garden\s+view", ["garden"]),
            (r"вид\s+на\s+лес|forest\s+view", ["forest"]),
        ]
        for pat, tags in view_patterns:
            m = re.search(pat, text)
            if m:
                consumed.append(m.span())
                return tags
        return []

    # --- City ---

    def _extract_city(self, text: str, consumed: list[tuple[int, int]]) -> str | None:
        for alias in APARTMENT_CITY_ALIASES_SORTED:
            if alias in text:
                start = text.index(alias)
                consumed.append((start, start + len(alias)))
                return APARTMENT_CITY_ALIASES[alias]
        return None

    # --- Legacy dict-format extraction (replaces FilterExtractor) ---

    def extract_filters(self, query: str) -> dict[str, Any]:
        """Extract structured filters from natural language query, returning a dict.

        This is the legacy interface previously provided by FilterExtractor.
        Retained for callers that need a plain dict (e.g. pre-agent semantic cache path).
        """
        filters: dict[str, Any] = {}

        price_filter = self._extract_price_dict(query)
        if price_filter:
            filters["price"] = price_filter

        rooms = self._extract_rooms_dict(query)
        if rooms is not None:
            filters["rooms"] = rooms

        city = self._extract_city_with_names(query)
        if city:
            filters["city"] = city

        area_filter = self._extract_area_dict(query)
        if area_filter:
            filters["area"] = area_filter

        floor = self._extract_floor_dict(query)
        if floor is not None:
            filters["floor"] = floor

        distance_filter = self._extract_distance_to_sea(query)
        if distance_filter:
            filters["distance_to_sea"] = distance_filter

        maintenance_filter = self._extract_maintenance(query)
        if maintenance_filter:
            filters["maintenance"] = maintenance_filter

        bathrooms = self._extract_bathrooms(query)
        if bathrooms is not None:
            filters["bathrooms"] = bathrooms

        furnished = self._extract_furnished(query)
        if furnished is not None:
            filters["furnished"] = furnished

        year_round = self._extract_year_round(query)
        if year_round:
            filters["year_round"] = year_round

        return filters

    def _extract_rooms_dict(self, query: str) -> int | None:
        """Extract rooms for legacy dict-format path (supports hyphen notation like '2-комнатная')."""
        q = query.lower()
        num_map = {"одно": 1, "дву": 2, "трех": 3, "четырех": 4, "пяти": 5, "студия": 1}
        patterns = [
            r"(\d+)[\s-]*комнат",
            r"(одно|дву|трех|четырех|пяти)комнатн",
            r"студия",
        ]
        for pat in patterns:
            m = re.search(pat, q)
            if m:
                rooms_str = m.group(1) if m.lastindex else m.group(0)
                if rooms_str.isdigit():
                    return int(rooms_str)
                for word, num in num_map.items():
                    if word in rooms_str:
                        return num
        return None

    def _extract_price_dict(self, query: str) -> dict[str, int] | None:
        """Extract price filter returning legacy dict format {"lt": N} etc."""
        q = query.lower()
        m = re.search(r"от\s+(\d+[\s\d]*к?)\s+до\s+(\d+[\s\d]*к?)", q)
        if m:
            mn = self._parse_number(m.group(1))
            mx = self._parse_number(m.group(2))
            if mn and mx:
                return {"gte": mn, "lte": mx}
        for pat in [
            r"дешевле\s+(\d+[\s\d]*к?)",
            r"до\s+(\d+[\s\d]*к?)",
            r"меньше\s+(\d+[\s\d]*к?)",
            r"<\s*(\d+[\s\d]*к?)",
            r"не\s+дороже\s+(\d+[\s\d]*к?)",
        ]:
            m2 = re.search(pat, q)
            if m2:
                val = self._parse_number(m2.group(1))
                if val:
                    return {"lt": val}
        for pat in [
            r"дороже\s+(\d+[\s\d]*к?)",
            r"от\s+(\d+[\s\d]*к?)",
            r"больше\s+(\d+[\s\d]*к?)",
            r">\s*(\d+[\s\d]*к?)",
        ]:
            m3 = re.search(pat, q)
            if m3:
                val = self._parse_number(m3.group(1))
                if val:
                    return {"gt": val}
        return None

    def _extract_area_dict(self, query: str) -> dict[str, int] | None:
        """Extract area filter returning legacy dict format."""
        q = query.lower()
        for pat in [
            r"больше\s+(\d+)\s*(?:м|кв)",
            r"от\s+(\d+)\s*(?:м|кв)",
            r"меньше\s+(\d+)\s*(?:м|кв)",
            r"до\s+(\d+)\s*(?:м|кв)",
        ]:
            m = re.search(pat, q)
            if m:
                area = int(m.group(1))
                return {"gte": area} if ("больше" in pat or "от" in pat) else {"lte": area}
        return None

    def _extract_floor_dict(self, query: str) -> int | None:
        """Extract floor filter returning a single int."""
        q = query.lower()
        for pat in [r"(\d+)\s*этаж", r"на\s+(\d+)"]:
            m = re.search(pat, q)
            if m:
                return int(m.group(1))
        return None

    def _extract_distance_to_sea(self, query: str) -> dict[str, int] | None:
        """Extract distance to sea filter."""
        q = query.lower()
        if re.search(r"первая\s+линия", q):
            return {"lte": 200}
        if re.search(r"у\s+моря", q):
            return {"lte": 200}
        for pat in [
            r"до\s+(\d+)\s*(?:м|метр).*?(?:до\s+)?(?:моря|пляжа)",
            r"не\s+дальше\s+(\d+)\s*(?:м|метр)",
            r"в\s+(\d+)\s*(?:м|метр).*?от\s+(?:моря|пляжа)",
            r"(?:моря|пляжа).*?(\d+)\s*(?:м|метр)",
        ]:
            m = re.search(pat, q)
            if m:
                try:
                    return {"lte": int(m.group(1))}
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_maintenance(self, query: str) -> dict[str, float] | None:
        """Extract maintenance cost filter."""
        q = query.lower()
        for pat in [
            r"(?:поддержка|такса).*?(?:до|меньше)\s+(\d+)",
            r"(?:до|меньше)\s+(\d+).*?(?:поддержка|такса)",
            r"низкая\s+(?:поддержка|такса)",
        ]:
            m = re.search(pat, q)
            if m:
                if "низкая" in pat:
                    return {"lte": 12.0}
                try:
                    return {"lte": float(m.group(1))}
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_bathrooms(self, query: str) -> int | None:
        """Extract number of bathrooms."""
        q = query.lower()
        num_map = {"один": 1, "два": 2, "три": 3}
        for pat in [
            r"(\d+)\s*санузл",
            r"(один|два|три)\s+санузл",
            r"(один|два|три)\s+санузел",
        ]:
            m = re.search(pat, q)
            if m:
                val = m.group(1)
                return int(val) if val.isdigit() else num_map.get(val)
        return None

    def _extract_furnished(self, query: str) -> bool | None:
        """Extract furnished requirement."""
        q = query.lower()
        for pat in [r"без\s+мебели", r"немеблирован"]:
            if re.search(pat, q):
                return False
        for pat in [r"с\s+мебелью", r"меблирован", r"с\s+мебель", r"обставлен"]:
            if re.search(pat, q):
                return True
        return None

    def _extract_year_round(self, query: str) -> str | None:
        """Extract year-round requirement."""
        q = query.lower()
        for pat in [r"круглогодичн", r"круглый\s+год", r"зимой\s+(?:можно|работает)"]:
            if re.search(pat, q):
                return "Да"
        return None

    # Also expose city extraction via APARTMENT_CITY_NAMES fallback (legacy path)
    def _extract_city_with_names(self, query: str) -> str | None:
        """Extract city using both aliases and canonical APARTMENT_CITY_NAMES."""
        q = query.lower()
        for alias in APARTMENT_CITY_ALIASES_SORTED:
            if alias in q:
                return APARTMENT_CITY_ALIASES[alias]
        for city in APARTMENT_CITY_NAMES:
            if city.lower() in q:
                return city
        return None

    # --- Semantic query ---

    def _build_semantic_query(self, query: str, consumed: list[tuple[int, int]]) -> str:
        """Remove filter token spans from original query; return descriptive remainder."""
        if not consumed:
            return query.strip()
        spans = sorted(set(consumed))
        merged: list[tuple[int, int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        parts: list[str] = []
        prev = 0
        for start, end in merged:
            chunk = query[prev:start].strip()
            if chunk:
                parts.append(chunk)
            prev = end
        tail = query[prev:].strip()
        if tail:
            parts.append(tail)
        return " ".join(parts).strip()
