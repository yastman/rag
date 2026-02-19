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
