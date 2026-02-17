"""Tests for RU/UK query normalizer."""

import pytest

from telegram_bot.services.normalizer import normalize_ru_uk


class TestGreetingsRU:
    """Test Russian greeting stripping."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Добрый день, подскажите про ипотеку", "про ипотеку"),
            ("Здравствуйте, какие есть квартиры", "какие есть квартиры"),
            ("Привет, покажи студии", "покажи студии"),
            ("Приветствую, есть ли дома у моря", "есть ли дома у моря"),
            ("Доброе утро, что нового", "что нового"),
            ("Добрый вечер, подскажите цены", "цены"),
            ("Здрасте, покажите квартиры", "покажите квартиры"),
            ("Хай, что есть в Несебре", "что есть в Несебре"),
        ],
    )
    def test_greeting_stripped(self, input_text, expected):
        assert normalize_ru_uk(input_text) == expected


class TestGreetingsUK:
    """Test Ukrainian greeting stripping."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Привіт, розкажіть будь ласка про кредит, дякую", "про кредит"),
            ("Вітаю, які квартири є", "які квартири є"),
            ("Добрий день, покажіть ціни", "покажіть ціни"),
            ("Доброго ранку, що нового", "що нового"),
        ],
    )
    def test_greeting_stripped(self, input_text, expected):
        assert normalize_ru_uk(input_text) == expected


class TestPoliteRequests:
    """Test polite request phrase stripping."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("Подскажите пожалуйста про ставки", "про ставки"),
            ("подскажите про условия", "про условия"),
            ("расскажите про квартиры у моря", "про квартиры у моря"),
            ("можете рассказать про цены", "про цены"),
            ("можешь подсказать где дешевле", "где дешевле"),
            ("будьте добры покажите студии", "покажите студии"),
            ("не могли бы вы показать варианты", "показать варианты"),
            ("підкажіть будь ласка про кредит", "про кредит"),
            ("розкажіть будь ласка про умови", "про умови"),
            ("чи можете показати квартири", "показати квартири"),
        ],
    )
    def test_polite_request_stripped(self, input_text, expected):
        assert normalize_ru_uk(input_text) == expected


class TestPoliteTails:
    """Test polite tail phrase stripping."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("покажите квартиры, спасибо", "покажите квартиры"),
            ("какие есть варианты, заранее спасибо", "какие есть варианты"),
            ("покажите цены, буду благодарен", "покажите цены"),
            ("подскажите стоимость, буду признательна", "стоимость"),
            ("что есть в Несебре, благодарю", "что есть в Несебре"),
            ("покажіть квартири, дякую", "покажіть квартири"),
            ("які ціни, заздалегідь дякую", "які ціни"),
            ("покажіть варіанти, буду вдячний", "покажіть варіанти"),
        ],
    )
    def test_polite_tail_stripped(self, input_text, expected):
        assert normalize_ru_uk(input_text) == expected


class TestFillerWords:
    """Test filler word stripping."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            ("ну вот как бы расскажите про ставки", "про ставки"),
            ("покажите пожалуйста квартиры", "покажите квартиры"),
            ("так сказать какие цены", "какие цены"),
            ("короче покажи студии", "покажи студии"),
            ("покажіть будь ласка квартири", "покажіть квартири"),
        ],
    )
    def test_filler_stripped(self, input_text, expected):
        assert normalize_ru_uk(input_text) == expected


class TestEdgeCases:
    """Test edge cases."""

    @pytest.mark.parametrize(
        ("input_text", "expected"),
        [
            pytest.param("условия ипотеки", "условия ипотеки", id="plain_query"),
            pytest.param("Привет", "Привет", id="short_result_returns_original"),
            pytest.param("", "", id="empty_string"),
            pytest.param("Здравствуйте", "Здравствуйте", id="only_greeting"),
            pytest.param("ну вот", "ну вот", id="only_filler"),
            pytest.param(
                "Здравствуйте, можете рассказать про условия кредита, заранее спасибо",
                "про условия кредита",
                id="complex_ru",
            ),
            pytest.param(
                "Привіт, розкажіть будь ласка про кредит, дякую",
                "про кредит",
                id="complex_uk",
            ),
            pytest.param(
                "Добрый день, подскажите пожалуйста, какие есть квартиры в Несебре, заранее спасибо",
                "какие есть квартиры в Несебре",
                id="multiple_patterns",
            ),
            pytest.param(
                "ДОБРЫЙ ДЕНЬ, покажите варианты",
                "покажите варианты",
                id="case_insensitive",
            ),
            pytest.param(
                "квартиры дешевле 100 000 евро",
                "квартиры дешевле 100 000 евро",
                id="preserves_meaningful",
            ),
            pytest.param(
                "Привет,   покажи   студии",
                "покажи студии",
                id="whitespace_normalization",
            ),
        ],
    )
    def test_edge_case(self, input_text, expected):
        assert normalize_ru_uk(input_text) == expected
