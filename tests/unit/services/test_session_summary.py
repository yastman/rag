"""Unit tests for SessionSummary model and generate_summary()."""

from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.session_summary import (
    SessionSummary,
    format_summary_as_note,
    format_turns_for_prompt,
    generate_summary,
)


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


class TestFormatTurnsForPrompt:
    """Test turns formatting for LLM prompt."""

    def test_formats_turns_as_dialog(self):
        """format_turns_for_prompt renders Q&A pairs as readable dialog."""
        turns = [
            {
                "query": "Какие квартиры у моря?",
                "response": "Есть варианты в Sunny Beach от $50K.",
                "timestamp": "2026-02-17T10:00:00+00:00",
                "input_type": "text",
            },
            {
                "query": "А с двумя комнатами?",
                "response": "2-комнатные от $75K, есть 3 варианта.",
                "timestamp": "2026-02-17T10:02:00+00:00",
                "input_type": "text",
            },
        ]
        result = format_turns_for_prompt(turns)

        assert "Клиент: Какие квартиры у моря?" in result
        assert "Бот: Есть варианты в Sunny Beach от $50K." in result
        assert "Клиент: А с двумя комнатами?" in result

    def test_empty_turns(self):
        """format_turns_for_prompt returns empty string for no turns."""
        assert format_turns_for_prompt([]) == ""


class TestGenerateSummary:
    """Test generate_summary() with mocked LLM."""

    async def test_returns_session_summary(self):
        """generate_summary returns SessionSummary from LLM response."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.output_parsed = SessionSummary(
            brief="Клиент ищет квартиру у моря.",
            client_needs=["2-комнатная", "вид на море"],
            budget="$80,000",
            preferences=["Sunny Beach"],
            next_steps=["подобрать варианты"],
            sentiment="positive",
        )
        mock_llm.responses.parse = AsyncMock(return_value=mock_response)

        turns = [
            {
                "query": "Ищу квартиру у моря",
                "response": "Есть варианты от $50K",
                "timestamp": "2026-02-17T10:00:00+00:00",
                "input_type": "text",
            }
        ]

        result = await generate_summary(turns=turns, llm=mock_llm)

        assert isinstance(result, SessionSummary)
        assert result.brief == "Клиент ищет квартиру у моря."
        assert result.budget == "$80,000"
        mock_llm.responses.parse.assert_awaited_once()

    async def test_passes_model_parameter(self):
        """generate_summary uses provided model name."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.output_parsed = SessionSummary(
            brief="Test.",
            client_needs=[],
            budget=None,
            preferences=[],
            next_steps=[],
            sentiment="neutral",
        )
        mock_llm.responses.parse = AsyncMock(return_value=mock_response)

        await generate_summary(
            turns=[{"query": "q", "response": "r", "timestamp": "t", "input_type": "text"}],
            llm=mock_llm,
            model="gpt-4o-mini",
        )

        call_kwargs = mock_llm.responses.parse.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    async def test_returns_none_on_empty_turns(self):
        """generate_summary returns None when no turns provided."""
        mock_llm = AsyncMock()

        result = await generate_summary(turns=[], llm=mock_llm)

        assert result is None
        mock_llm.responses.parse.assert_not_called()

    async def test_returns_none_on_llm_error(self):
        """generate_summary returns None on LLM exception."""
        mock_llm = AsyncMock()
        mock_llm.responses.parse = AsyncMock(side_effect=RuntimeError("API error"))

        result = await generate_summary(
            turns=[{"query": "q", "response": "r", "timestamp": "t", "input_type": "text"}],
            llm=mock_llm,
        )

        assert result is None

    async def test_returns_none_on_refusal_or_unparsed_output(self):
        """generate_summary returns None when model does not produce parsed payload."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.output_parsed = None
        mock_llm.responses.parse = AsyncMock(return_value=mock_response)

        result = await generate_summary(
            turns=[{"query": "q", "response": "r", "timestamp": "t", "input_type": "text"}],
            llm=mock_llm,
        )

        assert result is None


class TestFormatSummaryAsNote:
    """Test CRM note formatting."""

    def test_formats_full_summary(self):
        """format_summary_as_note produces readable CRM note."""
        summary = SessionSummary(
            brief="Клиент ищет квартиру у моря.",
            client_needs=["2-комнатная квартира", "вид на море"],
            budget="$80,000",
            preferences=["Sunny Beach", "не выше 5 этажа"],
            next_steps=["подобрать 3 варианта", "назначить показ"],
            sentiment="positive",
        )
        note = format_summary_as_note(summary)

        assert "AI Summary" in note
        assert "Клиент ищет квартиру у моря." in note
        assert "2-комнатная квартира" in note
        assert "$80,000" in note
        assert "Sunny Beach" in note
        assert "подобрать 3 варианта" in note

    def test_formats_minimal_summary(self):
        """format_summary_as_note handles empty optional fields."""
        summary = SessionSummary(
            brief="Короткий разговор.",
            client_needs=[],
            budget=None,
            preferences=[],
            next_steps=[],
            sentiment="neutral",
        )
        note = format_summary_as_note(summary)

        assert "Короткий разговор." in note
        # No budget section when None
        assert "Бюджет" not in note
