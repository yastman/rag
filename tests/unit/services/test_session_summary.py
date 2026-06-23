"""Unit tests for SessionSummary model, generate_summary(), and compat guard."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import telegram_bot.services.session_summary as ss_module
from telegram_bot.services.session_summary import (
    SessionSummary,
    _trim_turns_for_summary,
    check_responses_parse_compat,
    format_summary_as_note,
    format_turns_for_prompt,
    generate_summary,
)


_SINGLE_TURN = [{"query": "q", "response": "r", "timestamp": "t", "input_type": "text"}]


def _make_summary(**overrides: object) -> SessionSummary:
    """Helper: build a SessionSummary with sensible defaults."""
    defaults = {
        "brief": "Test.",
        "client_needs": [],
        "budget": None,
        "preferences": [],
        "next_steps": [],
        "sentiment": "neutral",
    }
    defaults.update(overrides)
    return SessionSummary(**defaults)  # type: ignore[arg-type]


def _make_responses_llm(
    summary: SessionSummary | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Build an AsyncMock LLM with responses.parse available."""
    mock_llm = AsyncMock()
    if side_effect:
        mock_llm.responses.parse = AsyncMock(side_effect=side_effect)
    else:
        mock_response = MagicMock()
        mock_response.output_parsed = summary
        mock_llm.responses.parse = AsyncMock(return_value=mock_response)
    return mock_llm


def _make_fallback_llm(
    summary: SessionSummary | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Build a MagicMock LLM with only beta.chat.completions.parse (no responses)."""
    mock_llm = MagicMock(spec=[])  # no 'responses' attribute
    mock_message = MagicMock()
    mock_message.parsed = summary
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_llm.beta = MagicMock()
    if side_effect:
        mock_llm.beta.chat.completions.parse = AsyncMock(side_effect=side_effect)
    else:
        mock_llm.beta.chat.completions.parse = AsyncMock(return_value=mock_completion)
    return mock_llm


@pytest.fixture(autouse=True)
def _reset_compat_flags():
    """Reset module-level compat flags before each test."""
    ss_module._force_chat_completions_fallback = False
    ss_module._compat_checked = False
    yield
    ss_module._force_chat_completions_fallback = False
    ss_module._compat_checked = False


# ---------------------------------------------------------------------------
# SessionSummary Pydantic model
# ---------------------------------------------------------------------------


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
        summary = _make_summary(budget=None)
        assert summary.budget is None

    def test_sentiment_values(self):
        """SessionSummary accepts valid sentiment values."""
        for sentiment in ("positive", "neutral", "negative"):
            summary = _make_summary(sentiment=sentiment)
            assert summary.sentiment == sentiment


# ---------------------------------------------------------------------------
# format_turns_for_prompt
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# check_responses_parse_compat  (compatibility guard)
# ---------------------------------------------------------------------------


class TestCheckResponsesParseCompat:
    """Test the startup/preflight compatibility check."""

    def test_returns_true_when_responses_parse_available(self):
        """Compat check passes when responses.parse exists and is callable."""
        mock_llm = AsyncMock()
        mock_llm.responses.parse = AsyncMock()

        result = check_responses_parse_compat(mock_llm)

        assert result is True
        assert ss_module._force_chat_completions_fallback is False
        assert ss_module._compat_checked is True

    def test_returns_false_when_responses_missing(self):
        """Compat check fails when llm has no 'responses' attribute."""
        mock_llm = MagicMock(spec=[])  # no responses

        result = check_responses_parse_compat(mock_llm)

        assert result is False
        assert ss_module._force_chat_completions_fallback is True

    def test_returns_false_when_parse_missing(self):
        """Compat check fails when responses exists but has no 'parse'."""
        mock_llm = MagicMock()
        mock_llm.responses = MagicMock(spec=[])  # no parse attribute

        result = check_responses_parse_compat(mock_llm)

        assert result is False
        assert ss_module._force_chat_completions_fallback is True

    def test_returns_false_when_parse_not_callable(self):
        """Compat check fails when responses.parse is not callable (langfuse < 3.2.4)."""
        mock_llm = MagicMock()
        mock_llm.responses.parse = "not_a_function"  # exists but not callable

        result = check_responses_parse_compat(mock_llm)

        assert result is False
        assert ss_module._force_chat_completions_fallback is True

    def test_sets_compat_checked_flag(self):
        """Compat check always sets _compat_checked regardless of result."""
        mock_llm = MagicMock(spec=[])

        assert ss_module._compat_checked is False
        check_responses_parse_compat(mock_llm)
        assert ss_module._compat_checked is True


# ---------------------------------------------------------------------------
# generate_summary  (both code paths + graceful degradation)
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    """Test generate_summary() with mocked LLM."""

    # --- responses.parse path (happy path) ---

    async def test_responses_parse_works_uses_it(self):
        """Test 1: responses.parse available and works -- uses it."""
        expected = _make_summary(brief="Клиент ищет квартиру у моря.", budget="$80,000")
        mock_llm = _make_responses_llm(summary=expected)

        result = await generate_summary(
            turns=[
                {
                    "query": "Ищу квартиру у моря",
                    "response": "Есть варианты от $50K",
                    "timestamp": "2026-02-17T10:00:00+00:00",
                    "input_type": "text",
                }
            ],
            llm=mock_llm,
        )

        assert isinstance(result, SessionSummary)
        assert result.brief == "Клиент ищет квартиру у моря."
        assert result.budget == "$80,000"
        mock_llm.responses.parse.assert_awaited_once()

    async def test_passes_model_parameter(self):
        """generate_summary uses provided model name."""
        mock_llm = _make_responses_llm(summary=_make_summary())

        await generate_summary(turns=_SINGLE_TURN, llm=mock_llm, model="gpt-4o-mini")

        call_kwargs = mock_llm.responses.parse.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"

    async def test_returns_none_on_empty_turns(self):
        """generate_summary returns None when no turns provided."""
        mock_llm = AsyncMock()

        result = await generate_summary(turns=[], llm=mock_llm)

        assert result is None

    async def test_returns_none_on_refusal_or_unparsed_output(self):
        """generate_summary returns None when model does not produce parsed payload."""
        mock_llm = _make_responses_llm(summary=None)

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result is None

    # --- fallback: beta.chat.completions.parse path ---

    async def test_fallback_when_responses_unavailable(self):
        """Test 2: responses.parse unavailable -- fallback works without crash."""
        expected = _make_summary(brief="Fallback test.")
        mock_llm = _make_fallback_llm(summary=expected)

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result == expected
        mock_llm.beta.chat.completions.parse.assert_awaited_once()
        call_kwargs = mock_llm.beta.chat.completions.parse.call_args.kwargs
        assert call_kwargs["response_format"] is SessionSummary
        assert call_kwargs["temperature"] == 0.0

    async def test_fallback_error_returns_none(self):
        """generate_summary returns None when fallback path also fails."""
        mock_llm = _make_fallback_llm(side_effect=RuntimeError("fallback error"))

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result is None

    # --- graceful degradation: responses.parse raises at runtime ---

    async def test_responses_parse_error_degrades_to_fallback(self):
        """Test 3: responses.parse raises error -- graceful degradation to fallback."""
        expected = _make_summary(brief="Degraded OK.")
        # Build an LLM that has responses.parse (raises) AND beta fallback (works)
        mock_llm = AsyncMock()
        mock_llm.responses.parse = AsyncMock(side_effect=TypeError("wrapper bug"))

        mock_message = MagicMock()
        mock_message.parsed = expected
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_llm.beta.chat.completions.parse = AsyncMock(return_value=mock_completion)

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result == expected
        # Both should have been called: responses.parse tried first, then fallback
        mock_llm.responses.parse.assert_awaited_once()
        mock_llm.beta.chat.completions.parse.assert_awaited_once()

    async def test_responses_parse_error_and_fallback_error_returns_none(self):
        """Both paths fail -- returns None gracefully."""
        mock_llm = AsyncMock()
        mock_llm.responses.parse = AsyncMock(side_effect=TypeError("wrapper bug"))
        mock_llm.beta.chat.completions.parse = AsyncMock(
            side_effect=RuntimeError("fallback also broken")
        )

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result is None

    # --- forced fallback via _force_chat_completions_fallback flag ---

    async def test_forced_fallback_skips_responses_parse(self):
        """When compat guard sets _force_chat_completions_fallback, responses.parse is skipped."""
        ss_module._force_chat_completions_fallback = True

        expected = _make_summary(brief="Forced fallback.")
        # LLM that has responses.parse but it should NOT be called
        mock_llm = AsyncMock()
        mock_llm.responses.parse = AsyncMock(side_effect=AssertionError("should not be called"))

        mock_message = MagicMock()
        mock_message.parsed = expected
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_llm.beta.chat.completions.parse = AsyncMock(return_value=mock_completion)

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result == expected
        mock_llm.responses.parse.assert_not_awaited()
        mock_llm.beta.chat.completions.parse.assert_awaited_once()

    async def test_compat_check_then_generate_uses_fallback(self):
        """End-to-end: compat check detects missing responses -> generate uses fallback."""
        mock_llm = _make_fallback_llm(summary=_make_summary(brief="E2E fallback."))

        # Run compat check -- should set _force_chat_completions_fallback
        result_compat = check_responses_parse_compat(mock_llm)
        assert result_compat is False
        assert ss_module._force_chat_completions_fallback is True

        # Now generate should use fallback path
        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)
        assert result is not None
        assert result.brief == "E2E fallback."

    async def test_returns_none_on_llm_error(self):
        """generate_summary returns None when responses.parse raises and no fallback."""
        # LLM with responses.parse that errors + fallback that also errors
        mock_llm = AsyncMock()
        mock_llm.responses.parse = AsyncMock(side_effect=RuntimeError("API error"))
        mock_llm.beta.chat.completions.parse = AsyncMock(side_effect=RuntimeError("also broken"))

        result = await generate_summary(turns=_SINGLE_TURN, llm=mock_llm)

        assert result is None


# ---------------------------------------------------------------------------
# _trim_turns_for_summary
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# format_summary_as_note
# ---------------------------------------------------------------------------


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
        summary = _make_summary(brief="Короткий разговор.")
        note = format_summary_as_note(summary)

        assert "Короткий разговор." in note
        # No budget section when None
        assert "Бюджет" not in note
