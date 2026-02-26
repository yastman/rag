"""Tests for apartment ingestion flow — text serialization and embedding prep."""

from src.ingestion.apartments.flow import format_apartment_text
from telegram_bot.services.apartment_models import ApartmentRecord


class TestFormatApartmentText:
    def test_contains_complex_name(self) -> None:
        record = ApartmentRecord(
            complex_name="Premier Fort Beach",
            city="Sunny Beach",
            section="D-1",
            apartment_number="248",
            rooms=2,
            floor=4,
            floor_label="4",
            area_m2=78.66,
            view_primary="sea",
            view_tags=["sea"],
            price_eur=215000.0,
            price_bgn=420503.45,
            is_furnished=False,
            has_floor_plan=False,
            has_photo=False,
        )
        text = format_apartment_text(record)
        assert "Premier Fort Beach" in text
        assert "215" in text  # price
        assert "78.66" in text  # area

    def test_promotion_flag(self) -> None:
        record = ApartmentRecord(
            complex_name="Test",
            city="Elenite",
            section="A",
            apartment_number="1",
            rooms=1,
            floor=2,
            floor_label="2",
            area_m2=30.0,
            view_primary="pool",
            view_tags=["pool"],
            price_eur=50000.0,
            price_bgn=97000.0,
            is_furnished=True,
            has_floor_plan=False,
            has_photo=False,
            is_promotion=True,
            old_price_eur=60000.0,
        )
        text = format_apartment_text(record)
        assert "Акция" in text or "акция" in text

    def test_payload_contains_city(self) -> None:
        """Payload must include city for Qdrant filtering."""
        record = ApartmentRecord(
            complex_name="Panorama Fort Beach",
            city="Elenite",
            section="E-2",
            apartment_number="172",
            rooms=3,
            floor=5,
            floor_label="5",
            area_m2=171.53,
            view_primary="sea_panorama",
            view_tags=["sea", "panorama"],
            price_eur=195000.0,
            price_bgn=381386.85,
            is_furnished=False,
            has_floor_plan=False,
            has_photo=False,
        )
        payload = record.to_payload()
        assert payload["city"] == "Elenite"
