# telegram_bot/services/apartment_filter_extractor.py
"""Apartment-specific filter extraction from natural language queries (0 LLM calls)."""

from __future__ import annotations

import re

from telegram_bot.observability import observe
from telegram_bot.services.apartment_models import ApartmentQueryParseResult, compute_confidence


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


# City aliases — sorted longest-first for greedy match
_CITY_ALIASES: dict[str, str] = {
    # Солнечный берег — все падежи
    "солнечный берег": "Солнечный берег",
    "солнечного берега": "Солнечный берег",
    "солнечном берегу": "Солнечный берег",
    "солнечному берегу": "Солнечный берег",
    "sunny beach": "Солнечный берег",
    "санни бич": "Солнечный берег",
    # Свети Влас — все падежи
    "свети влас": "Свети Влас",
    "свети власе": "Свети Влас",
    "свети власа": "Свети Влас",
    "святой влас": "Свети Влас",
    "святом власе": "Свети Влас",
    "святого власа": "Свети Влас",
    # Элените — не склоняется
    "элените": "Элените",
    "elenite": "Элените",
}

_CITY_ALIASES_SORTED = sorted(_CITY_ALIASES, key=len, reverse=True)


class ApartmentFilterExtractor:
    """Extract apartment filters from natural language (regex-only, 0 LLM calls)."""

    @observe(name="apartment-filter-parse", capture_input=False, capture_output=False)
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

    def _parse_number(self, text: str) -> int | None:
        """Parse integer from text, handling spaces and 'к' = 1000 suffix."""
        text = text.strip().replace(" ", "").replace("\xa0", "")
        if text.endswith("к"):
            text = text[:-1] + "000"
        try:
            return int(text)
        except ValueError:
            return None

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
        for alias in _CITY_ALIASES_SORTED:
            if alias in text:
                start = text.index(alias)
                consumed.append((start, start + len(alias)))
                return _CITY_ALIASES[alias]
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
