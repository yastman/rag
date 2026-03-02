"""AI Advisor service — LLM-powered CRM insights (#731).

Two main actions:
- get_daily_plan(): Morning briefing — leads + tasks + stale deals → action plan
- get_deal_and_task_tips(): Tips for stale deals + task prioritization

Prompts are managed in Langfuse; fallbacks are hardcoded for reliability.
LLM responses use HTML formatting (not Markdown) for Telegram parse_mode=HTML.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from typing import Any

from telegram_bot.integrations.prompt_manager import get_prompt


logger = logging.getLogger(__name__)

_BRIEFING_CACHE_TTL = 600  # 10 minutes
_STALE_THRESHOLD_SECONDS = 5 * 86400  # 5 days
_MAX_TOKENS = 800

# Langfuse prompt names
_PROMPT_DAILY_PLAN = "advisor-daily-plan"
_PROMPT_DEAL_TIPS = "advisor-deal-tips"

_MONTH_NAMES_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def _format_budget(amount: int | None) -> str:
    """Format budget as '€50 000' or '—' for None."""
    if amount is None:
        return "—"
    return f"€{amount:,}".replace(",", " ")


def _format_date(unix_ts: int | None) -> str:
    """Format Unix timestamp as '2 марта 2025'."""
    if unix_ts is None:
        return "—"
    d = dt.datetime.fromtimestamp(unix_ts, tz=dt.UTC)
    month = _MONTH_NAMES_RU.get(d.month, str(d.month))
    return f"{d.day} {month} {d.year}"


def _format_days_ago(unix_ts: int | None, now: int) -> str:
    """Format as 'X дн. назад' or 'сегодня'."""
    if unix_ts is None:
        return "—"
    days = (now - unix_ts) // 86400
    if days <= 0:
        return "сегодня"
    if days == 1:
        return "1 день назад"
    if 2 <= days <= 4:
        return f"{days} дня назад"
    return f"{days} дн. назад"


# Fallback prompts (used when Langfuse unavailable)
_FALLBACK_DAILY_PLAN = (
    "Ты — AI-помощник менеджера по продажам недвижимости в Болгарии.\n"
    "Сегодня: {{today}}.\n\n"
    "ЗАДАЧА: Составь план действий на день. Менеджер только открыл CRM — "
    "у него новые заявки, просроченные задачи, застрявшие сделки. "
    "Помоги разобраться что делать первым.\n\n"
    "ЛОГИКА ПЛАНА:\n"
    "1. Просроченные задачи по дорогим сделкам → делай ПЕРВЫМ\n"
    "2. Горячие новые лиды (1-2 дня) → звони пока не остыли\n"
    "3. Застрявшие сделки с высоким бюджетом → реанимируй\n"
    "4. Задачи на сегодня → по порядку\n"
    "5. Остальное → если останется время\n\n"
    "ФОРМАТ ОТВЕТА (строго HTML, НЕ Markdown):\n"
    "<b>📋 План на {{today}}</b>\n\n"
    "<b>🔥 Сделай первым:</b>\n"
    "1. Действие — <b>Имя</b> (€бюджет, причина)\n\n"
    "<b>📅 Основные дела:</b>\n"
    "2. Действие — <b>Имя</b>\n\n"
    "<b>💡 Если будет время:</b>\n"
    "3. Действие\n\n"
    "<b>📊 Итого:</b> X срочных, Y основных, Z можно отложить\n\n"
    "ПРАВИЛА:\n"
    "- Максимум 10 пунктов в плане\n"
    "- Если у лида есть просроченная задача — объедини в один пункт\n"
    "- Каждый пункт = конкретное действие + имя + причина\n"
    "- Не используй Markdown (** или *)"
)

_FALLBACK_DEAL_TIPS = (
    "Ты — AI-помощник менеджера по продажам недвижимости в Болгарии.\n"
    "Сегодня: {{today}}.\n\n"
    "ЗАДАЧА: Проанализируй задачи и застрявшие сделки менеджера. "
    "Дай конкретные советы: что делать с каждой и почему.\n\n"
    "ЛОГИКА ПРИОРИТИЗАЦИИ:\n"
    "1. ⚠️ Просроченные задачи — всегда первые\n"
    "2. Застрявшие сделки с высоким бюджетом — риск потери клиента\n"
    "3. Задачи на сегодня — не откладывай\n"
    "4. Сделки без активности 5-7 дней — пора напомнить\n\n"
    "ФОРМАТ ОТВЕТА (строго HTML):\n"
    "Для каждого пункта:\n"
    "<b>N. Имя / Задача</b> — €бюджет или срок\n"
    "💡 Конкретное действие и почему именно сейчас\n\n"
    "ПРАВИЛА:\n"
    "- Максимум 7 пунктов\n"
    "- Для застрявших сделок предложи шаблон сообщения клиенту\n"
    "- Не используй Markdown (** или *)"
)


class AIAdvisorService:
    """LLM-powered manager advisor: daily plan and deal tips."""

    def __init__(
        self,
        *,
        kommo_client: Any,
        llm: Any,
        cache: Any = None,
    ) -> None:
        self._kommo = kommo_client
        self._llm = llm
        self._cache = cache

    async def _fetch_leads_text(self, manager_id: int | None) -> str:
        """Fetch leads and format as rich text for LLM context."""
        try:
            leads = await self._kommo.search_leads(responsible_user_id=manager_id, limit=20)
        except Exception:
            logger.exception("Failed to fetch leads for advisor")
            return "Данные о лидах недоступны."

        if not leads:
            return "Нет активных лидов."

        now = int(time.time())
        parts: list[str] = []
        for lead in leads:
            days_inactive = ""
            if lead.updated_at:
                d = (now - lead.updated_at) // 86400
                if d >= 5:
                    days_inactive = f" | ⚠️ без активности {d} дн."

            parts.append(
                f"• {lead.name or '—'}\n"
                f"  Бюджет: {_format_budget(lead.budget)}\n"
                f"  Создан: {_format_date(lead.created_at)} ({_format_days_ago(lead.created_at, now)})\n"
                f"  Обновлён: {_format_date(lead.updated_at)} ({_format_days_ago(lead.updated_at, now)})"
                f"{days_inactive}"
            )
        return "\n\n".join(parts)

    async def _fetch_tasks_text(self, manager_id: int | None) -> str:
        """Fetch open tasks and format as rich text for LLM context."""
        try:
            tasks = await self._kommo.get_tasks(responsible_user_id=manager_id, is_completed=False)
        except Exception:
            logger.exception("Failed to fetch tasks for advisor")
            return "Данные о задачах недоступны."

        if not tasks:
            return "Нет активных задач."

        now = int(time.time())
        parts: list[str] = []
        for task in tasks:
            # Определяем статус срока
            if task.complete_till:
                days_left = (task.complete_till - now) // 86400
                if days_left < 0:
                    status = f"⚠️ ПРОСРОЧЕНО на {abs(days_left)} дн."
                elif days_left == 0:
                    status = "📅 Срок сегодня"
                elif days_left == 1:
                    status = "📅 Срок завтра"
                else:
                    status = f"Срок через {days_left} дн."
            else:
                status = "Без срока"

            # Привязка к лиду
            linked = ""
            if task.entity_type == "leads" and task.entity_id:
                linked = f"\n  Привязана к лиду ID: {task.entity_id}"

            parts.append(
                f"• {task.text or '—'}\n"
                f"  Срок: {_format_date(task.complete_till)} — {status}"
                f"{linked}"
            )
        return "\n\n".join(parts)

    async def _fetch_stale_text(self, manager_id: int | None) -> str:
        """Fetch leads and categorize by inactivity severity."""
        try:
            leads = await self._kommo.search_leads(responsible_user_id=manager_id, limit=50)
        except Exception:
            logger.exception("Failed to fetch leads for stale analysis")
            return "Данные о сделках недоступны."

        if not leads:
            return "Нет сделок."

        now = int(time.time())
        critical: list[str] = []  # 15+ дней
        attention: list[str] = []  # 8-14 дней
        remind: list[str] = []  # 5-7 дней

        for lead in leads:
            if not lead.updated_at:
                continue
            days = (now - lead.updated_at) // 86400
            if days < 5:
                continue

            entry = (
                f"• {lead.name or '—'} — {_format_budget(lead.budget)}, без активности {days} дн."
            )

            if days >= 15:
                critical.append(entry)
            elif days >= 8:
                attention.append(entry)
            else:
                remind.append(entry)

        if not critical and not attention and not remind:
            return "Все сделки активны — нет застрявших."

        sections: list[str] = []
        if critical:
            sections.append(
                f"🔴 Критичные (15+ дней) — {len(critical)} шт:\n" + "\n".join(critical)
            )
        if attention:
            sections.append(
                f"🟡 Внимание (8-14 дней) — {len(attention)} шт:\n" + "\n".join(attention)
            )
        if remind:
            sections.append(f"🟢 Напомнить (5-7 дней) — {len(remind)} шт:\n" + "\n".join(remind))

        return "\n\n".join(sections)

    async def _call_llm(self, system_prompt: str, user_text: str) -> str:
        """Call LLM with system+user prompt, return response text."""
        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=_MAX_TOKENS,
            )
            return response.choices[0].message.content or "Нет ответа."
        except Exception:
            logger.exception("LLM call failed in advisor")
            return "❌ Ошибка при генерации ответа."

    async def get_daily_plan(self, manager_id: int | None) -> str:
        """Generate morning action plan from all CRM data.

        Fetches leads, tasks and stale deals in parallel, then asks LLM
        to generate a prioritized daily action plan. Result is cached 10 min.

        Args:
            manager_id: Kommo responsible_user_id. None = all.

        Returns:
            HTML-formatted action plan string.
        """
        cache_key = f"advisor:daily_plan:{manager_id}"

        if self._cache and getattr(self._cache, "redis", None):
            try:
                cached = await self._cache.redis.get(cache_key)
                if cached:
                    return str(cached)
            except Exception:
                logger.warning("Cache get failed for %s", cache_key)

        leads_text, tasks_text, stale_text = await asyncio.gather(
            self._fetch_leads_text(manager_id),
            self._fetch_tasks_text(manager_id),
            self._fetch_stale_text(manager_id),
        )

        today = dt.datetime.now(dt.UTC).strftime("%d.%m.%Y")

        system_prompt = get_prompt(
            name=_PROMPT_DAILY_PLAN,
            fallback=_FALLBACK_DAILY_PLAN,
            variables={"today": today},
        )

        user_text = (
            f"Лиды:\n{leads_text}\n\nЗадачи:\n{tasks_text}\n\nЗастрявшие сделки:\n{stale_text}"
        )

        result = await self._call_llm(system_prompt, user_text)

        if self._cache and getattr(self._cache, "redis", None):
            try:
                await self._cache.redis.setex(cache_key, _BRIEFING_CACHE_TTL, result)
            except Exception:
                logger.warning("Cache set failed for %s", cache_key)

        return result

    async def get_deal_and_task_tips(self, manager_id: int | None) -> str:
        """Generate tips for stale deals and task prioritization.

        Fetches tasks and stale deals in parallel, then asks LLM for advice.

        Args:
            manager_id: Kommo responsible_user_id. None = all.

        Returns:
            HTML-formatted tips string.
        """
        tasks_text, stale_text = await asyncio.gather(
            self._fetch_tasks_text(manager_id),
            self._fetch_stale_text(manager_id),
        )

        today = dt.datetime.now(dt.UTC).strftime("%d.%m.%Y")

        system_prompt = get_prompt(
            name=_PROMPT_DEAL_TIPS,
            fallback=_FALLBACK_DEAL_TIPS,
            variables={"today": today},
        )

        user_text = f"Задачи:\n{tasks_text}\n\nЗастрявшие сделки:\n{stale_text}"

        return await self._call_llm(system_prompt, user_text)
