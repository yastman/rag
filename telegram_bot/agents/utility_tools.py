"""Utility tools: mortgage_calculator, daily_summary, handoff (#445).

All tools follow the @tool + @observe + RunnableConfig DI pattern from crm_tools.py.
Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import get_client, observe
from telegram_bot.services.kommo_models import TaskCreate


logger = logging.getLogger(__name__)

_DEFAULT_SUMMARY_MODEL = "claude-haiku-4-5"


def _get_ctx(config: RunnableConfig) -> Any | None:
    """Get BotContext from config."""
    return config.get("configurable", {}).get("bot_context")


def _fmt(value: float) -> str:
    """Format monetary value: space thousands separator, 2 decimal places."""
    return f"{value:,.2f}".replace(",", " ")


# ---------------------------------------------------------------------------
# Tool 1: mortgage_calculator
# ---------------------------------------------------------------------------


@tool
@observe(name="tool-mortgage-calculator")
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
# Internal helper for daily_summary
# ---------------------------------------------------------------------------


async def _summarize_with_llm(data: str, llm: Any, model: str = _DEFAULT_SUMMARY_MODEL) -> str:
    """Call LLM to summarize CRM activity."""
    response = await llm.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Summarize CRM activity for a real estate manager. "
                    "Be concise, use bullet points."
                ),
            },
            {"role": "user", "content": data},
        ],
        max_tokens=500,
        name="daily-summary",
    )
    return response.choices[0].message.content or "Нет данных."


# ---------------------------------------------------------------------------
# Tool 2: daily_summary
# ---------------------------------------------------------------------------


@tool
@observe(name="tool-daily-summary")
async def daily_summary(
    config: RunnableConfig,
    date: str = "today",
) -> str:
    """Get daily CRM activity summary for managers.

    Args:
        date: Date for summary: "today", "yesterday", or YYYY-MM-DD format.
    """
    ctx = _get_ctx(config)
    if not ctx or not ctx.kommo_client:
        return "CRM недоступен. Обратитесь к администратору."

    # Parse date
    if date == "today":
        target = datetime.now(UTC).date()
    elif date == "yesterday":
        target = (datetime.now(UTC) - timedelta(days=1)).date()
    else:
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return "Некорректный формат даты. Используйте YYYY-MM-DD."

    try:
        # NOTE: KommoClient does not support date-range filtering; fetches latest 50 records.
        # The date parameter is used only for the summary header, not for actual filtering.
        # TODO: add date-range filter when Kommo API supports it (#445)
        leads = await ctx.kommo_client.search_leads(query="", limit=50)
        tasks = await ctx.kommo_client.get_tasks(limit=50)
    except Exception as e:
        logger.exception("daily_summary CRM query failed")
        return f"Ошибка при запросе CRM: {e}"

    # Build data string for summarization
    lines = [f"CRM Activity for {target.isoformat()} (latest 50 records):"]
    lines.append(f"Leads: {len(leads)}")
    for lead in leads[:10]:
        name = getattr(lead, "name", "—")
        budget = getattr(lead, "budget", None)
        budget_str = f", budget: {budget}" if budget else ""
        lines.append(f"  - {name}{budget_str}")
    lines.append(f"Tasks due: {len(tasks)}")
    data = "\n".join(lines)

    return await _summarize_with_llm(data, ctx.llm)


# ---------------------------------------------------------------------------
# Tool 3: handoff
# ---------------------------------------------------------------------------


@tool
@observe(name="tool-handoff")
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

    for mid in manager_ids:
        try:
            await bot.send_message(chat_id=mid, text=text)
        except Exception:
            logger.warning("Failed to notify manager %s", mid, exc_info=True)

    # Create Kommo task if available
    # TODO: resolve lead_id from telegram_user_id via lead scoring store
    kommo = getattr(ctx, "kommo_client", None)
    lead_id: int | None = None  # lead_id resolution not yet implemented
    if kommo and lead_id:
        try:
            await kommo.create_task(
                TaskCreate(
                    text=f"Handoff: {reason}",
                    entity_id=lead_id,
                    entity_type="leads",
                    complete_till=int(time.time()) + 3600,
                )
            )
        except Exception:
            logger.warning("Failed to create Kommo handoff task", exc_info=True)
    elif kommo:
        logger.debug(
            "Skipping Kommo handoff task: lead_id not resolved for user %s", ctx.telegram_user_id
        )

    lf = get_client()
    lf.score_current_trace(name="handoff_triggered", value=1, data_type="BOOLEAN")
    lf.score_current_trace(name="handoff_urgency", value=urgency, data_type="CATEGORICAL")

    return "Ваш запрос передан менеджеру. Ожидайте ответа."


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def get_utility_tools() -> list:
    """Return all utility tools for agent registration."""
    return [mortgage_calculator, daily_summary, handoff]
