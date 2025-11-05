"""Extract filters from natural language queries."""

import re
from typing import Any


class FilterExtractor:
    """Extract structured filters from user queries."""

    def extract_filters(self, query: str) -> dict[str, Any]:
        """
        Extract filters from natural language query.

        Args:
            query: User query text

        Returns:
            Dict with extracted filters like {"price": {"lt": 100000}}
        """
        filters = {}

        # Price filters
        price_filter = self._extract_price(query)
        if price_filter:
            filters["price"] = price_filter

        # Rooms filter
        rooms = self._extract_rooms(query)
        if rooms:
            filters["rooms"] = rooms

        # City filter
        city = self._extract_city(query)
        if city:
            filters["city"] = city

        # Area filter
        area_filter = self._extract_area(query)
        if area_filter:
            filters["area"] = area_filter

        # Floor filter
        floor = self._extract_floor(query)
        if floor:
            filters["floor"] = floor

        # Distance to sea filter
        distance_filter = self._extract_distance_to_sea(query)
        if distance_filter:
            filters["distance_to_sea"] = distance_filter

        # Maintenance cost filter
        maintenance_filter = self._extract_maintenance(query)
        if maintenance_filter:
            filters["maintenance"] = maintenance_filter

        # Bathrooms filter
        bathrooms = self._extract_bathrooms(query)
        if bathrooms:
            filters["bathrooms"] = bathrooms

        # Furniture filter
        furniture = self._extract_furniture(query)
        if furniture:
            filters["furniture"] = furniture

        # Year-round filter
        year_round = self._extract_year_round(query)
        if year_round:
            filters["year_round"] = year_round

        return filters

    def _extract_price(self, query: str) -> dict[str, int] | None:
        """Extract price filter from query."""
        query_lower = query.lower()

        # "дешевле 100000", "до 100к", "< 100000"
        patterns_lt = [
            r"дешевле\s+(\d+[\s\d]*)",
            r"до\s+(\d+[\s\d]*)",
            r"меньше\s+(\d+[\s\d]*)",
            r"<\s*(\d+[\s\d]*)",
            r"не\s+дороже\s+(\d+[\s\d]*)",
        ]

        for pattern in patterns_lt:
            match = re.search(pattern, query_lower)
            if match:
                price = self._parse_number(match.group(1))
                if price:
                    return {"lt": price}

        # "дороже 100000", "от 100000", "> 100000"
        patterns_gt = [
            r"дороже\s+(\d+[\s\d]*)",
            r"от\s+(\d+[\s\d]*)",
            r"больше\s+(\d+[\s\d]*)",
            r">\s*(\d+[\s\d]*)",
        ]

        for pattern in patterns_gt:
            match = re.search(pattern, query_lower)
            if match:
                price = self._parse_number(match.group(1))
                if price:
                    return {"gt": price}

        # Range: "от 80000 до 150000"
        range_pattern = r"от\s+(\d+[\s\d]*)\s+до\s+(\d+[\s\d]*)"
        match = re.search(range_pattern, query_lower)
        if match:
            min_price = self._parse_number(match.group(1))
            max_price = self._parse_number(match.group(2))
            if min_price and max_price:
                return {"gte": min_price, "lte": max_price}

        return None

    def _extract_rooms(self, query: str) -> int | None:
        """Extract number of rooms."""
        query_lower = query.lower()

        # "3 комнаты", "трехкомнатная", "3-комнатная"
        patterns = [
            r"(\d+)[\s-]*комнат",
            r"(одно|дву|трех|четырех|пяти)комнатн",
            r"студия",
        ]

        # Number mapping
        num_map = {
            "одно": 1,
            "дву": 2,
            "трех": 3,
            "четырех": 4,
            "пяти": 5,
            "студия": 1,
        }

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                rooms_str = match.group(1) if match.lastindex else match.group(0)
                # Try to parse as number
                if rooms_str.isdigit():
                    return int(rooms_str)
                # Try word mapping
                for word, num in num_map.items():
                    if word in rooms_str:
                        return num

        return None

    def _extract_city(self, query: str) -> str | None:
        """Extract city name."""
        cities = [
            "Солнечный берег",
            "Несебр",
            "Бургас",
            "Варна",
            "София",
            "Поморие",
            "Созополь",
        ]

        for city in cities:
            if city.lower() in query.lower():
                return city

        return None

    def _extract_area(self, query: str) -> dict[str, int] | None:
        """Extract area filter."""
        query_lower = query.lower()

        # "больше 50 м2", "от 60 кв.м"
        patterns = [
            r"больше\s+(\d+)\s*(?:м|кв)",
            r"от\s+(\d+)\s*(?:м|кв)",
            r"меньше\s+(\d+)\s*(?:м|кв)",
            r"до\s+(\d+)\s*(?:м|кв)",
        ]

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                area = int(match.group(1))
                if "больше" in pattern or "от" in pattern:
                    return {"gte": area}
                return {"lte": area}

        return None

    def _extract_floor(self, query: str) -> int | None:
        """Extract floor filter."""
        query_lower = query.lower()

        # "4 этаж", "на 4 этаже", "только 4 этажа"
        patterns = [
            r"(\d+)\s*этаж",
            r"на\s+(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                return int(match.group(1))

        return None

    def _parse_number(self, text: str) -> int | None:
        """Parse number from text, handling spaces and k suffix."""
        text = text.strip().replace(" ", "").replace("\xa0", "")

        # Handle "100к" -> 100000
        if text.endswith("к"):
            text = text[:-1] + "000"

        try:
            return int(text)
        except ValueError:
            return None

    def _extract_distance_to_sea(self, query: str) -> dict[str, int] | None:
        """Extract distance to sea filter from query."""
        query_lower = query.lower()

        # "до 500м до моря", "не дальше 600м", "в 400м от моря"
        patterns = [
            r"до\s+(\d+)\s*(?:м|метр).*?(?:до\s+)?(?:моря|пляжа)",
            r"не\s+дальше\s+(\d+)\s*(?:м|метр)",
            r"в\s+(\d+)\s*(?:м|метр).*?от\s+(?:моря|пляжа)",
            r"(?:моря|пляжа).*?(\d+)\s*(?:м|метр)",
            r"первая\s+линия",
            r"у\s+моря",
        ]

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                if "первая линия" in pattern or "у моря" in pattern:
                    return {"lte": 200}
                try:
                    distance = int(match.group(1))
                    return {"lte": distance}
                except (ValueError, IndexError):
                    continue

        return None

    def _extract_maintenance(self, query: str) -> dict[str, float] | None:
        """Extract maintenance cost filter from query."""
        query_lower = query.lower()

        # "поддержка до 10 евро", "такса меньше 15"
        patterns = [
            r"(?:поддержка|такса).*?(?:до|меньше)\s+(\d+)",
            r"(?:до|меньше)\s+(\d+).*?(?:поддержка|такса)",
            r"низкая\s+(?:поддержка|такса)",
        ]

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                if "низкая" in pattern:
                    return {"lte": 12.0}
                try:
                    cost = float(match.group(1))
                    return {"lte": cost}
                except (ValueError, IndexError):
                    continue

        return None

    def _extract_bathrooms(self, query: str) -> int | None:
        """Extract number of bathrooms from query."""
        query_lower = query.lower()

        # "2 санузла", "два санузла"
        patterns = [
            r"(\d+)\s*санузл",
            r"(один|два|три)\s*санузл",
        ]

        num_map = {"один": 1, "два": 2, "три": 3}

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                value = match.group(1)
                if value.isdigit():
                    return int(value)
                if value in num_map:
                    return num_map[value]

        return None

    def _extract_furniture(self, query: str) -> str | None:
        """Extract furniture requirement from query."""
        query_lower = query.lower()

        # "с мебелью", "меблированная"
        patterns = [
            r"с\s+мебелью",
            r"меблирован",
            r"с\s+мебель",
            r"обставлен",
        ]

        for pattern in patterns:
            if re.search(pattern, query_lower):
                return "Есть"

        return None

    def _extract_year_round(self, query: str) -> str | None:
        """Extract year-round requirement from query."""
        query_lower = query.lower()

        # "круглогодичная", "круглый год"
        patterns = [
            r"круглогодичн",
            r"круглый\s+год",
            r"зимой\s+(?:можно|работает)",
        ]

        for pattern in patterns:
            if re.search(pattern, query_lower):
                return "Да"

        return None
