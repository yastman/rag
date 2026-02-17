"""Unit tests for SessionSummary model and generate_summary()."""

from telegram_bot.services.session_summary import SessionSummary


class TestSessionSummaryModel:
    """Test SessionSummary Pydantic model."""

    def test_valid_summary(self):
        """SessionSummary accepts valid data."""
        summary = SessionSummary(
            brief="Клиент интересовался квартирами у моря.",
            client_needs=["2-комнатная квартира", "вид на море"],
            budget="$80,000",
            preferences=["район Sunny Beach", "не выше 5 этажа"],
            next_steps=["подобрать 3 варианта"],
            sentiment="positive",
        )
        assert summary.brief == "Клиент интересовался квартирами у моря."
        assert len(summary.client_needs) == 2
        assert summary.budget == "$80,000"
        assert summary.sentiment == "positive"

    def test_optional_budget(self):
        """SessionSummary allows None budget."""
        summary = SessionSummary(
            brief="Общий разговор.",
            client_needs=[],
            budget=None,
            preferences=[],
            next_steps=[],
            sentiment="neutral",
        )
        assert summary.budget is None

    def test_sentiment_values(self):
        """SessionSummary accepts valid sentiment values."""
        for sentiment in ("positive", "neutral", "negative"):
            summary = SessionSummary(
                brief="Test.",
                client_needs=[],
                budget=None,
                preferences=[],
                next_steps=[],
                sentiment=sentiment,
            )
            assert summary.sentiment == sentiment
