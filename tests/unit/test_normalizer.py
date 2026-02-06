"""Tests for RU/UK query normalizer."""

from telegram_bot.services.normalizer import normalize_ru_uk


class TestGreetingsRU:
    """Test Russian greeting stripping."""

    def test_dobryj_den(self):
        assert normalize_ru_uk("Добрый день, подскажите про ипотеку") == "про ипотеку"

    def test_zdravstvujte(self):
        assert normalize_ru_uk("Здравствуйте, какие есть квартиры") == "какие есть квартиры"

    def test_privet(self):
        assert normalize_ru_uk("Привет, покажи студии") == "покажи студии"

    def test_privetstvuyu(self):
        assert normalize_ru_uk("Приветствую, есть ли дома у моря") == "есть ли дома у моря"

    def test_dobroe_utro(self):
        assert normalize_ru_uk("Доброе утро, что нового") == "что нового"

    def test_dobryj_vecher(self):
        assert normalize_ru_uk("Добрый вечер, подскажите цены") == "цены"

    def test_zdrasye(self):
        assert normalize_ru_uk("Здрасте, покажите квартиры") == "покажите квартиры"

    def test_haj(self):
        assert normalize_ru_uk("Хай, что есть в Несебре") == "что есть в Несебре"


class TestGreetingsUK:
    """Test Ukrainian greeting stripping."""

    def test_pryvit(self):
        assert normalize_ru_uk("Привіт, розкажіть будь ласка про кредит, дякую") == "про кредит"

    def test_vitayu(self):
        assert normalize_ru_uk("Вітаю, які квартири є") == "які квартири є"

    def test_dobryj_den_uk(self):
        assert normalize_ru_uk("Добрий день, покажіть ціни") == "покажіть ціни"

    def test_dobroho_ranku(self):
        assert normalize_ru_uk("Доброго ранку, що нового") == "що нового"


class TestPoliteRequests:
    """Test polite request phrase stripping."""

    def test_podskazhite_pozhalujsta(self):
        assert normalize_ru_uk("Подскажите пожалуйста про ставки") == "про ставки"

    def test_podskazhite(self):
        assert normalize_ru_uk("подскажите про условия") == "про условия"

    def test_rasskazhite(self):
        assert normalize_ru_uk("расскажите про квартиры у моря") == "про квартиры у моря"

    def test_mozhete_rasskazat(self):
        assert normalize_ru_uk("можете рассказать про цены") == "про цены"

    def test_mozhesh_podskazat(self):
        assert normalize_ru_uk("можешь подсказать где дешевле") == "где дешевле"

    def test_budte_dobry(self):
        assert normalize_ru_uk("будьте добры покажите студии") == "покажите студии"

    def test_ne_mogli_by_vy(self):
        assert normalize_ru_uk("не могли бы вы показать варианты") == "показать варианты"

    def test_uk_pidkazhit(self):
        assert normalize_ru_uk("підкажіть будь ласка про кредит") == "про кредит"

    def test_uk_rozkazhit(self):
        assert normalize_ru_uk("розкажіть будь ласка про умови") == "про умови"

    def test_uk_chy_mozhete(self):
        assert normalize_ru_uk("чи можете показати квартири") == "показати квартири"


class TestPoliteTails:
    """Test polite tail phrase stripping."""

    def test_spasibo(self):
        assert normalize_ru_uk("покажите квартиры, спасибо") == "покажите квартиры"

    def test_zaranee_spasibo(self):
        assert normalize_ru_uk("какие есть варианты, заранее спасибо") == "какие есть варианты"

    def test_budu_blagodaren(self):
        assert normalize_ru_uk("покажите цены, буду благодарен") == "покажите цены"

    def test_budu_priznatelna(self):
        assert normalize_ru_uk("подскажите стоимость, буду признательна") == "стоимость"

    def test_blagodaryu(self):
        assert normalize_ru_uk("что есть в Несебре, благодарю") == "что есть в Несебре"

    def test_uk_dyakuyu(self):
        assert normalize_ru_uk("покажіть квартири, дякую") == "покажіть квартири"

    def test_uk_zazdaleghid_dyakuyu(self):
        assert normalize_ru_uk("які ціни, заздалегідь дякую") == "які ціни"

    def test_uk_budu_vdachnyj(self):
        assert normalize_ru_uk("покажіть варіанти, буду вдячний") == "покажіть варіанти"


class TestFillerWords:
    """Test filler word stripping."""

    def test_filler_words_ru(self):
        assert normalize_ru_uk("ну вот как бы расскажите про ставки") == "про ставки"

    def test_pozhalujsta_standalone(self):
        assert normalize_ru_uk("покажите пожалуйста квартиры") == "покажите квартиры"

    def test_tak_skazat(self):
        assert normalize_ru_uk("так сказать какие цены") == "какие цены"

    def test_koroche(self):
        assert normalize_ru_uk("короче покажи студии") == "покажи студии"

    def test_uk_bud_laska(self):
        assert normalize_ru_uk("покажіть будь ласка квартири") == "покажіть квартири"


class TestEdgeCases:
    """Test edge cases."""

    def test_plain_query_unchanged(self):
        assert normalize_ru_uk("условия ипотеки") == "условия ипотеки"

    def test_short_result_returns_original(self):
        # "Привет" alone would produce empty string -> return original
        assert normalize_ru_uk("Привет") == "Привет"

    def test_empty_string(self):
        assert normalize_ru_uk("") == ""

    def test_only_greeting_returns_original(self):
        assert normalize_ru_uk("Здравствуйте") == "Здравствуйте"

    def test_only_filler_returns_original(self):
        assert normalize_ru_uk("ну вот") == "ну вот"

    def test_complex_ru(self):
        result = normalize_ru_uk(
            "Здравствуйте, можете рассказать про условия кредита, заранее спасибо"
        )
        assert result == "про условия кредита"

    def test_complex_uk(self):
        result = normalize_ru_uk("Привіт, розкажіть будь ласка про кредит, дякую")
        assert result == "про кредит"

    def test_multiple_patterns_combined(self):
        result = normalize_ru_uk(
            "Добрый день, подскажите пожалуйста, какие есть квартиры в Несебре, заранее спасибо"
        )
        assert result == "какие есть квартиры в Несебре"

    def test_case_insensitive(self):
        assert normalize_ru_uk("ДОБРЫЙ ДЕНЬ, покажите варианты") == "покажите варианты"

    def test_preserves_meaningful_content(self):
        result = normalize_ru_uk("квартиры дешевле 100 000 евро")
        assert result == "квартиры дешевле 100 000 евро"

    def test_whitespace_normalization(self):
        result = normalize_ru_uk("Привет,   покажи   студии")
        assert result == "покажи студии"
