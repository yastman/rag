"""Unit tests for SessionSummary model and generate_summary()."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.session_summary import (
    SessionSummary,
    _trim_turns_for_summary,
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

    async def test_fallback_to_chat_completions_parse(self):
        """generate_summary uses beta.chat.completions.parse when responses API unavailable."""
        mock_llm = MagicMock(spec=[])  # no 'responses' attribute
        expected = SessionSummary(
            brief="Fallback test.",
            client_needs=[],
            budget=None,
            preferences=[],
            next_steps=[],
            sentiment="neutral",
        )
        mock_message = MagicMock()
        mock_message.parsed = expected
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_llm.beta = MagicMock()
        mock_llm.beta.chat.completions.parse = AsyncMock(return_value=mock_completion)

        result = await generate_summary(
            turns=[{"query": "q", "response": "r", "timestamp": "t", "input_type": "text"}],
            llm=mock_llm,
        )

        assert result == expected
        mock_llm.beta.chat.completions.parse.assert_awaited_once()
        call_kwargs = mock_llm.beta.chat.completions.parse.call_args.kwargs
        assert call_kwargs["response_format"] is SessionSummary
        assert call_kwargs["temperature"] == 0.0

    async def test_fallback_error_returns_none(self):
        """generate_summary returns None when fallback path also fails."""
        mock_llm = MagicMock(spec=[])  # no 'responses' attribute
        mock_llm.beta = MagicMock()
        mock_llm.beta.chat.completions.parse = AsyncMock(side_effect=RuntimeError("fallback error"))

        result = await generate_summary(
            turns=[{"query": "q", "response": "r", "timestamp": "t", "input_type": "text"}],
            llm=mock_llm,
        )

        assert result is None


class TestTrimTurnsForSummary:
    """Test _trim_turns_for_summary internal function."""

    def test_filters_empty_turns(self):
        """_trim_turns_for_summary removes turns with no query and no response."""
        turns = [
            {"query": "q1", "response": "r1"},
            {"query": "", "response": ""},
            {"query": "q2", "response": "r2"},
        ]
        result = _trim_turns_for_summary(turns)
        assert len(result) == 2
        assert result[0]["query"] == "q1"
        assert result[1]["query"] == "q2"

    def test_caps_at_max_turns(self):
        """_trim_turns_for_summary keeps only last 40 turns."""
        turns = [{"query": f"q{i}", "response": f"r{i}"} for i in range(60)]
        result = _trim_turns_for_summary(turns)
        assert len(result) == 40
        assert result[0]["query"] == "q20"
        assert result[-1]["query"] == "q59"

    def test_returns_empty_for_empty_input(self):
        """_trim_turns_for_summary returns empty list for no turns."""
        assert _trim_turns_for_summary([]) == []

    def test_keeps_turns_with_only_query(self):
        """_trim_turns_for_summary keeps turns that have only query."""
        turns = [{"query": "q1", "response": ""}]
        result = _trim_turns_for_summary(turns)
        assert len(result) == 1


class TestFormatSummaryAsNote:
    """Test CRM note formatting."""

    @patch("telegram_bot.services.session_summary.datetime")
    def test_formats_full_summary(self, mock_dt):
        """format_summary_as_note produces readable CRM note with date."""
        mock_dt.now.return_value = datetime(2026, 2, 17, tzinfo=UTC)
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        summary = SessionSummary(
            brief="Клиент ищет квартиру у моря.",
            client_needs=["2-комнатная квартира", "вид на море"],
            budget="$80,000",
            preferences=["Sunny Beach", "не выше 5 этажа"],
            next_steps=["подобрать 3 варианта", "назначить показ"],
            sentiment="positive",
        )
        note = format_summary_as_note(summary)

        assert "AI Summary (2026-02-17)" in note
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
