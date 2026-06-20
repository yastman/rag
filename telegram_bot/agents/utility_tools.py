"""Utility tools: mortgage_calculator, daily_summary, handoff (#445).

All tools follow the @tool + @observe + RunnableConfig DI pattern from crm_tools.py.
Dependencies injected via :func:`telegram_bot.agents.context.get_bot_context`
(SDK-native ``runtime.context`` with ``configurable["bot_context"]`` back-compat
— see #1252).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telegram_bot.agents.context import get_bot_context
from telegram_bot.agents.tooling import RunnableConfig, tool
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


def _get_ctx(config: RunnableConfig) -> Any | None:
    """Get BotContext via the SDK-native helper (runtime.context preferred)."""
    return get_bot_context(None, config)


def _fmt(value: float) -> str:
    """Format monetary value: space thousands separator, 2 decimal places."""
    return f"{value:,.2f}".replace(",", " ")


# ---------------------------------------------------------------------------
# Tool 1: mortgage_calculator
# ---------------------------------------------------------------------------


@tool
@observe(name="tool-mortgage-calculator", as_type="tool")
async def mortgage_calculator(
    loan_amount: float,
    annual_rate: float,
    term_years: int,
    config: RunnableConfig,
    down_payment: float = 0,
) -> str:
    """Calculate monthly mortgage payment using the annuity formula.

    Args:
        loan_amount: Total property price in EUR.
        annual_rate: Annual interest rate as percentage (e.g. 3.5 for 3.5%).
        term_years: Loan term in years.
        down_payment: Optional down payment in EUR (reduces principal).
    """
    if loan_amount <= 0 or term_years <= 0:
        return "Некорректные параметры: сумма и срок должны быть положительными."

    if annual_rate < 0:
        return "Некорректная ставка: значение не может быть отрицательным."

    if annual_rate > 100:
        return (
            "Предупреждение: ставка превышает 100%. "
            "Убедитесь, что вы передали значение в процентах (например, 3.5 для 3.5%), а не в долях."
        )

    principal = loan_amount - down_payment
    if principal <= 0:
        return "Первоначальный взнос превышает сумму кредита."

    n = term_years * 12

    if annual_rate == 0:
        monthly = principal / n
    else:
        r = annual_rate / 100 / 12
        monthly = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)

    total = monthly * n
    total_interest = total - principal

    lines = [
        f"Ежемесячный платёж: {_fmt(monthly)} EUR",
        f"Сумма кредита: {_fmt(principal)} EUR",
        f"Общая сумма выплат: {_fmt(total)} EUR",
        f"Переплата (проценты): {_fmt(total_interest)} EUR",
        f"Ставка: {annual_rate}% годовых, срок: {term_years} лет",
    ]

    if down_payment > 0:
        ltv = principal / loan_amount * 100
        lines.append(f"Первоначальный взнос: {_fmt(down_payment)} EUR (LTV: {ltv:.0f}%)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 2: daily_summary
# ---------------------------------------------------------------------------


@tool
@observe(name="tool-daily-summary", as_type="tool")
async def daily_summary(
    config: RunnableConfig,
    date: str = "today",
) -> str:
    """Get daily CRM activity summary for managers.

    Args:
        date: Date for summary: "today", "yesterday", or YYYY-MM-DD format.
    """
    # CRM integration archived (#2689). Validate date format and return stub.
    if date not in ("today", "yesterday"):
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return "Некорректный формат даты. Используйте YYYY-MM-DD."

    return "CRM недоступен. Обратитесь к администратору."


# ---------------------------------------------------------------------------
# Tool 3: handoff
# ---------------------------------------------------------------------------


@tool
@observe(name="tool-handoff", as_type="tool")
async def handoff(
    reason: str,
    config: RunnableConfig,
    urgency: str = "normal",
    context_summary: str = "",
) -> str:
    """Transfer conversation to a human manager.

    Use when the client requests to speak with a person, or when the query
    is too complex for automated handling.

    Args:
        reason: Why handoff is needed.
        urgency: Priority level: low, normal, or high.
        context_summary: Optional conversation summary to include in notification.
    """
    ctx = _get_ctx(config)
    if not ctx:
        return "Ошибка: контекст недоступен."

    bot = getattr(ctx, "bot", None)
    manager_ids = getattr(ctx, "manager_ids", None) or []

    if not bot or not manager_ids:
        return "К сожалению, менеджеры сейчас недоступны. Попробуйте позже."

    prefix = "СРОЧНО " if urgency == "high" else ""
    text = (
        f"{prefix}Запрос на связь с менеджером\n"
        f"User ID: {ctx.telegram_user_id}\n"
        f"Session: {ctx.session_id}\n"
        f"Причина: {reason}\n"
    )
    if context_summary:
        text += f"Контекст: {context_summary}\n"

    delivered = 0
    for mid in manager_ids:
        try:
            await bot.send_message(chat_id=mid, text=text)
            delivered += 1
        except Exception:
            logger.warning("Failed to notify manager %s", mid, exc_info=True)

    # CRM handoff task creation was removed in #1541; archived in #2689.

    # Honest scoring (#2212): handoff_triggered must reflect a REAL action — at
    # least one manager actually notified — not merely that the tool ran. If no
    # notification succeeded, emit handoff_delivery_failed instead of a false
    # success so the CRM/ops dashboard is not misled. Guard get_client() which
    # may be None when Langfuse is disabled.
    lf = get_client()
    if delivered > 0:
        if lf is not None:
            lf.score_current_trace(name="handoff_triggered", value=1, data_type="BOOLEAN")
            lf.score_current_trace(name="handoff_urgency", value=urgency, data_type="CATEGORICAL")
        return "Ваш запрос передан менеджеру. Ожидайте ответа."

    if lf is not None:
        lf.score_current_trace(name="handoff_delivery_failed", value=1, data_type="BOOLEAN")
    logger.error(
        "handoff: all %d manager notification(s) failed for user %s",
        len(manager_ids),
        ctx.telegram_user_id,
    )
    return "К сожалению, не удалось связаться с менеджером. Попробуйте позже."


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def get_utility_tools() -> list:
    """Return all utility tools for agent registration."""
    return [mortgage_calculator, daily_summary, handoff]
