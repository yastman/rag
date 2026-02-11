"""Tests for ResponseStyleDetector — C+ scoring classifier."""

from __future__ import annotations

from telegram_bot.services.response_style_detector import ResponseStyleDetector, StyleInfo


class TestExplicitTriggers:
    """Explicit keywords override length heuristics."""

    def test_short_trigger_skolko_stoit(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("сколько стоит студия")
        assert result.style == "short"
        assert result.reasoning == "explicit_short_trigger"

    def test_short_trigger_kakaya_tsena(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("какая цена на квартиру в Несебре")
        assert result.style == "short"
        assert result.reasoning == "explicit_short_trigger"

    def test_detailed_trigger_sravni(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("сравни цены Несебр vs Равда")
        assert result.style == "detailed"
        assert result.reasoning == "explicit_detailed_trigger"

    def test_detailed_trigger_podrobno(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("расскажи подробно про рассрочку")
        assert result.style == "detailed"
        assert result.reasoning == "explicit_detailed_trigger"

    def test_detailed_overrides_short_query_length(self) -> None:
        """Even a 3-word query triggers detailed if keyword present."""
        detector = ResponseStyleDetector()
        result = detector.detect("сравни два варианта")
        assert result.style == "detailed"


class TestTransactionalIntents:
    """Domain-specific transactional patterns -> short."""

    def test_price_range_query(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("квартира до 50000 евро с мебелью")
        assert result.style == "short"
        assert result.reasoning == "transactional_intent"

    def test_minimalnaya_rassrochka(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("минимальная рассрочка на покупку квартиры")
        assert result.style == "short"
        assert result.reasoning == "explicit_short_trigger"


class TestLengthHeuristics:
    """Fallback when no triggers match."""

    def test_short_query_fallback(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("привет как дела")
        assert result.style == "short"
        assert result.reasoning == "short_query"

    def test_medium_query_fallback(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect(
            "мне нужна информация о процессе покупки недвижимости иностранцем в Болгарии"
        )
        assert result.style == "balanced"
        assert result.reasoning == "medium_query"

    def test_long_query_fallback(self) -> None:
        detector = ResponseStyleDetector()
        words = " ".join(["слово"] * 25)
        result = detector.detect(words)
        assert result.style == "detailed"
        assert result.reasoning == "long_query"


class TestDifficultyDetection:
    """Difficulty affects token budget."""

    def test_easy_short_query(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("цена студии")
        assert result.difficulty == "easy"

    def test_hard_comparison_query(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("сравни плюсы и минусы покупки")
        assert result.difficulty == "hard"

    def test_medium_default(self) -> None:
        detector = ResponseStyleDetector()
        result = detector.detect("расскажи о процессе покупки недвижимости в Болгарии")
        assert result.difficulty == "medium"


class TestStyleInfoDataclass:
    """StyleInfo has all required fields."""

    def test_fields_present(self) -> None:
        info = StyleInfo(style="short", difficulty="easy", reasoning="test", word_count=3)
        assert info.style == "short"
        assert info.difficulty == "easy"
        assert info.reasoning == "test"
        assert info.word_count == 3
