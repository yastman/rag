"""Tests for dynamic example generation from Qdrant."""

from telegram_bot.services.apartments_service import generate_search_examples


class TestGenerateExamples:
    def test_returns_4_examples(self) -> None:
        stats = {
            "cities": ["Солнечный берег", "Свети Влас", "Элените"],
            "complexes": ["Premier Fort Beach", "Nessebar Fort Residence"],
            "rooms": [1, 2, 3],
            "min_price": 69500,
            "max_price": 314000,
        }
        examples = generate_search_examples(stats)
        assert len(examples) == 4
        assert all(isinstance(e, str) for e in examples)

    def test_examples_contain_real_data(self) -> None:
        stats = {
            "cities": ["Солнечный берег"],
            "complexes": ["Premier Fort Beach"],
            "rooms": [2],
            "min_price": 80000,
            "max_price": 200000,
        }
        examples = generate_search_examples(stats)
        assert any("Солнечный берег" in e or "Premier Fort" in e for e in examples)

    def test_examples_diverse(self) -> None:
        stats = {
            "cities": ["Солнечный берег", "Свети Влас", "Элените"],
            "complexes": ["Premier Fort Beach"],
            "rooms": [1, 2, 3],
            "min_price": 69500,
            "max_price": 314000,
        }
        examples = generate_search_examples(stats)
        assert len(set(examples)) == 4

    def test_empty_stats_uses_defaults(self) -> None:
        examples = generate_search_examples({})
        assert len(examples) == 4
        assert all(isinstance(e, str) for e in examples)

    def test_single_city_no_complex(self) -> None:
        stats = {
            "cities": ["Бургас"],
            "complexes": [],
            "rooms": [1],
            "min_price": 50000,
            "max_price": 150000,
        }
        examples = generate_search_examples(stats)
        assert len(examples) == 4
        assert any("Бургас" in e for e in examples)

    def test_no_cities_uses_defaults(self) -> None:
        stats = {"cities": [], "complexes": [], "rooms": [], "min_price": 0, "max_price": 0}
        examples = generate_search_examples(stats)
        assert len(examples) == 4
