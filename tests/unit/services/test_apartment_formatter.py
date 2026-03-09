"""Tests for apartment formatting utilities (Task 3).

TDD RED phase: these tests must fail before implementation.
"""

from __future__ import annotations

from telegram_bot.services.apartment_formatter import format_apartment_html, format_apartment_text


class TestFormatApartmentText:
    """Tests for format_apartment_text() — LLM context formatting."""

    def test_empty_results_returns_no_results_message(self) -> None:
        result = format_apartment_text([])
        assert "не найдены" in result

    def test_single_result_includes_complex_name(self) -> None:
        results = [
            {
                "payload": {
                    "complex_name": "Premier Fort Beach",
                    "price_eur": 150000,
                    "rooms": 2,
                    "area_m2": 65.0,
                    "floor": 3,
                    "view_tags": ["sea"],
                    "section": "A",
                    "apartment_number": "101",
                    "is_furnished": True,
                }
            }
        ]
        result = format_apartment_text(results)
        assert "Premier Fort Beach" in result

    def test_single_result_includes_price(self) -> None:
        results = [
            {
                "payload": {
                    "complex_name": "Test",
                    "price_eur": 150000,
                    "rooms": 2,
                    "area_m2": 65.0,
                    "floor": 3,
                    "view_tags": [],
                    "section": "A",
                    "apartment_number": "1",
                    "is_furnished": False,
                }
            }
        ]
        result = format_apartment_text(results)
        assert "150" in result

    def test_single_result_header_shows_count(self) -> None:
        results = [
            {
                "payload": {
                    "complex_name": "Test",
                    "price_eur": 100000,
                    "rooms": 1,
                    "area_m2": 40.0,
                    "floor": 1,
                    "view_tags": [],
                    "section": "A",
                    "apartment_number": "1",
                    "is_furnished": False,
                }
            }
        ]
        result = format_apartment_text(results)
        assert "Найдено 1" in result

    def test_multiple_results_numbered(self) -> None:
        results = [
            {
                "payload": {
                    "complex_name": "Fort A",
                    "price_eur": 100000,
                    "rooms": 1,
                    "area_m2": 40.0,
                    "floor": 1,
                    "view_tags": [],
                    "section": "A",
                    "apartment_number": "1",
                    "is_furnished": False,
                }
            },
            {
                "payload": {
                    "complex_name": "Fort B",
                    "price_eur": 200000,
                    "rooms": 3,
                    "area_m2": 90.0,
                    "floor": 5,
                    "view_tags": ["pool"],
                    "section": "B",
                    "apartment_number": "2",
                    "is_furnished": True,
                }
            },
        ]
        result = format_apartment_text(results)
        assert "1." in result
        assert "2." in result
        assert "Найдено 2" in result

    def test_furnished_label_included(self) -> None:
        results = [
            {
                "payload": {
                    "complex_name": "Test",
                    "price_eur": 100000,
                    "rooms": 1,
                    "area_m2": 40.0,
                    "floor": 1,
                    "view_tags": [],
                    "section": "A",
                    "apartment_number": "1",
                    "is_furnished": True,
                }
            }
        ]
        result = format_apartment_text(results)
        assert "мебел" in result

    def test_floor_zero_displayed_as_cokol(self) -> None:
        results = [
            {
                "payload": {
                    "complex_name": "Test",
                    "price_eur": 100000,
                    "rooms": 1,
                    "area_m2": 40.0,
                    "floor": 0,
                    "view_tags": [],
                    "section": "A",
                    "apartment_number": "1",
                    "is_furnished": False,
                }
            }
        ]
        result = format_apartment_text(results)
        assert "цоколь" in result


class TestFormatApartmentHtml:
    """Tests for format_apartment_html() — property card formatting."""

    def test_basic_fields_include_complex_name(self) -> None:
        result = format_apartment_html(
            property_id="apt1",
            complex_name="Premier Fort Beach",
            location="Солнечный берег",
            property_type="1-спальня",
            floor=3,
            area_m2=65.0,
            view="sea",
            price_eur=150000,
        )
        assert "Premier Fort Beach" in result

    def test_price_formatted_with_spaces(self) -> None:
        result = format_apartment_html(
            property_id="apt1",
            complex_name="Test",
            location="City",
            property_type="Studio",
            floor=1,
            area_m2=30.0,
            view="garden",
            price_eur=150000,
        )
        # Price should be formatted as "150 000"
        assert "150" in result
        assert "€" in result

    def test_location_included(self) -> None:
        result = format_apartment_html(
            property_id="apt1",
            complex_name="Test",
            location="Солнечный берег",
            property_type="Studio",
            floor=1,
            area_m2=30.0,
            view="",
            price_eur=50000,
        )
        assert "Солнечный берег" in result

    def test_area_m2_included(self) -> None:
        result = format_apartment_html(
            property_id="apt1",
            complex_name="Test",
            location="City",
            property_type="Studio",
            floor=1,
            area_m2=65.5,
            view="",
            price_eur=50000,
        )
        assert "65" in result

    def test_optional_section_included_when_provided(self) -> None:
        result = format_apartment_html(
            property_id="apt1",
            complex_name="Test",
            location="City",
            property_type="Studio",
            floor=1,
            area_m2=30.0,
            view="garden",
            price_eur=50000,
            section="B",
            apartment_number="42",
        )
        assert "B" in result
        assert "42" in result

    def test_section_omitted_when_empty(self) -> None:
        result = format_apartment_html(
            property_id="apt1",
            complex_name="Test",
            location="City",
            property_type="Studio",
            floor=1,
            area_m2=30.0,
            view="",
            price_eur=50000,
        )
        assert "Секция" not in result
        assert "№" not in result
