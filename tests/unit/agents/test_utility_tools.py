"""Tests for utility tools: mortgage_calculator, daily_summary, handoff (#445)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.runnables import RunnableConfig

from telegram_bot.agents.context import BotContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot_context(**kwargs) -> BotContext:
    """Build a minimal BotContext for tests."""
    defaults: dict = {
        "telegram_user_id": 42,
        "session_id": "s-test",
        "language": "ru",
        "kommo_client": None,
        "history_service": AsyncMock(),
        "embeddings": AsyncMock(),
        "sparse_embeddings": AsyncMock(),
        "qdrant": AsyncMock(),
        "cache": AsyncMock(),
        "reranker": None,
        "llm": MagicMock(),
        "content_filter_enabled": True,
        "guard_mode": "hard",
    }
    defaults.update(kwargs)
    return BotContext(**defaults)


def _make_config(ctx: BotContext) -> RunnableConfig:
    return RunnableConfig(configurable={"bot_context": ctx})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bot_context():
    return _make_bot_context()


@pytest.fixture
def bot_context_no_kommo():
    return _make_bot_context(kommo_client=None)


@pytest.fixture
def mock_kommo():
    kommo = AsyncMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])
    return kommo


@pytest.fixture
def bot_context_with_kommo(mock_kommo):
    return _make_bot_context(kommo_client=mock_kommo)


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def bot_context_with_bot(mock_bot):
    return _make_bot_context(bot=mock_bot, manager_ids=[100, 200])


@pytest.fixture
def bot_context_no_managers():
    return _make_bot_context(bot=AsyncMock(), manager_ids=[])


# ---------------------------------------------------------------------------
# Task 1: mortgage_calculator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mortgage_basic(bot_context):
    """Basic annuity calculation: 100k EUR at 3.5% for 20 years."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 100000, "annual_rate": 3.5, "term_years": 20},
        config=_make_config(bot_context),
    )
    assert "Ежемесячный платёж" in result
    assert "579" in result  # ~579.96 EUR


@pytest.mark.asyncio
async def test_mortgage_zero_rate(bot_context):
    """Zero interest rate: simple division P/n."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 120000, "annual_rate": 0, "term_years": 10},
        config=_make_config(bot_context),
    )
    # 120000 / 120 = 1000 EUR/month
    assert "1 000" in result or "1000" in result


@pytest.mark.asyncio
async def test_mortgage_with_down_payment(bot_context):
    """With down payment: LTV should be shown."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 200000, "annual_rate": 4.0, "term_years": 25, "down_payment": 40000},
        config=_make_config(bot_context),
    )
    assert "LTV" in result or "80" in result


@pytest.mark.asyncio
async def test_mortgage_invalid_amount(bot_context):
    """Negative loan amount returns validation error."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": -1, "annual_rate": 3.5, "term_years": 20},
        config=_make_config(bot_context),
    )
    assert "ошибка" in result.lower() or "некорректн" in result.lower()


@pytest.mark.asyncio
async def test_mortgage_invalid_term(bot_context):
    """Zero term returns validation error."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 100000, "annual_rate": 3.5, "term_years": 0},
        config=_make_config(bot_context),
    )
    assert "ошибка" in result.lower() or "некорректн" in result.lower()


@pytest.mark.asyncio
async def test_mortgage_down_payment_exceeds_loan(bot_context):
    """Down payment >= loan amount returns error."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 50000, "annual_rate": 3.5, "term_years": 10, "down_payment": 60000},
        config=_make_config(bot_context),
    )
    assert "взнос" in result.lower() or "превышает" in result.lower()


@pytest.mark.asyncio
async def test_mortgage_negative_rate(bot_context):
    """Negative annual_rate returns validation error (M1)."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 100000, "annual_rate": -1.0, "term_years": 20},
        config=_make_config(bot_context),
    )
    assert "ставка" in result.lower() or "некорректн" in result.lower()


@pytest.mark.asyncio
async def test_mortgage_rate_over_100_warning(bot_context):
    """annual_rate > 100 returns percentage-format warning (M1)."""
    from telegram_bot.agents.utility_tools import mortgage_calculator

    result = await mortgage_calculator.ainvoke(
        {"loan_amount": 100000, "annual_rate": 150.0, "term_years": 20},
        config=_make_config(bot_context),
    )
    assert "100%" in result or "предупреждение" in result.lower() or "процент" in result.lower()


# ---------------------------------------------------------------------------
# Task 2: daily_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daily_summary_no_kommo(bot_context_no_kommo):
    """Returns CRM unavailable message when kommo_client is None."""
    from telegram_bot.agents.utility_tools import daily_summary

    result = await daily_summary.ainvoke(
        {"date": "today"},
        config=_make_config(bot_context_no_kommo),
    )
    assert "CRM недоступен" in result


@pytest.mark.asyncio
async def test_daily_summary_invalid_date(bot_context_with_kommo):
    """Returns error for invalid date format."""
    from telegram_bot.agents.utility_tools import daily_summary

    result = await daily_summary.ainvoke(
        {"date": "not-a-date"},
        config=_make_config(bot_context_with_kommo),
    )
    assert "формат" in result.lower() or "некорректн" in result.lower()


@pytest.mark.asyncio
async def test_daily_summary_success(bot_context_with_kommo):
    """Returns LLM summary when CRM is available."""
    from unittest.mock import patch

    from telegram_bot.agents.utility_tools import daily_summary

    with patch("telegram_bot.agents.utility_tools._summarize_with_llm") as mock_llm:
        mock_llm.return_value = "Summary: 1 new deal, budget 50k"
        result = await daily_summary.ainvoke(
            {"date": "today"},
            config=_make_config(bot_context_with_kommo),
        )
    assert "Summary" in result or "deal" in result.lower()


@pytest.mark.asyncio
async def test_daily_summary_yesterday(bot_context_with_kommo):
    """Accepts 'yesterday' as a date string."""
    from unittest.mock import patch

    from telegram_bot.agents.utility_tools import daily_summary

    with patch("telegram_bot.agents.utility_tools._summarize_with_llm") as mock_llm:
        mock_llm.return_value = "Yesterday summary"
        result = await daily_summary.ainvoke(
            {"date": "yesterday"},
            config=_make_config(bot_context_with_kommo),
        )
    assert "summary" in result.lower() or "yesterday" in result.lower()


@pytest.mark.asyncio
async def test_daily_summary_explicit_date(bot_context_with_kommo):
    """Accepts explicit YYYY-MM-DD date."""
    from unittest.mock import patch

    from telegram_bot.agents.utility_tools import daily_summary

    with patch("telegram_bot.agents.utility_tools._summarize_with_llm") as mock_llm:
        mock_llm.return_value = "Date summary"
        result = await daily_summary.ainvoke(
            {"date": "2026-01-15"},
            config=_make_config(bot_context_with_kommo),
        )
    assert "summary" in result.lower() or "date" in result.lower()


# ---------------------------------------------------------------------------
# Task 3: handoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handoff_sends_to_managers(bot_context_with_bot, mock_bot):
    """Sends notification to each manager and returns confirmation."""
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff.ainvoke(
        {"reason": "Client wants to see property in person"},
        config=_make_config(bot_context_with_bot),
    )
    assert "передан менеджеру" in result
    assert mock_bot.send_message.called


@pytest.mark.asyncio
async def test_handoff_no_managers(bot_context_no_managers):
    """Returns unavailable message when no managers configured."""
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff.ainvoke(
        {"reason": "Need human help"},
        config=_make_config(bot_context_no_managers),
    )
    assert "менеджер" in result.lower() or "недоступн" in result.lower()


@pytest.mark.asyncio
async def test_handoff_no_bot(bot_context):
    """Returns unavailable message when bot is not in context."""
    from telegram_bot.agents.utility_tools import handoff

    result = await handoff.ainvoke(
        {"reason": "Need help"},
        config=_make_config(bot_context),
    )
    assert "менеджер" in result.lower() or "недоступн" in result.lower()


@pytest.mark.asyncio
async def test_handoff_high_urgency(bot_context_with_bot, mock_bot):
    """High urgency includes 'СРОЧНО' in manager notification."""
    from telegram_bot.agents.utility_tools import handoff

    await handoff.ainvoke(
        {"reason": "Emergency", "urgency": "high"},
        config=_make_config(bot_context_with_bot),
    )
    call_args = mock_bot.send_message.call_args_list
    assert call_args
    sent_text = call_args[0].kwargs.get("text", "") or str(call_args[0])
    assert "СРОЧНО" in sent_text


@pytest.mark.asyncio
async def test_handoff_with_context_summary(bot_context_with_bot, mock_bot):
    """Context summary is included in the notification."""
    from telegram_bot.agents.utility_tools import handoff

    await handoff.ainvoke(
        {"reason": "Complex query", "context_summary": "Client prefers 2-room apartments"},
        config=_make_config(bot_context_with_bot),
    )
    call_args = mock_bot.send_message.call_args_list
    assert call_args
    sent_text = call_args[0].kwargs.get("text", "") or str(call_args[0])
    assert "2-room" in sent_text or "apartments" in sent_text or "Контекст" in sent_text
