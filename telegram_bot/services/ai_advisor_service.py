"""AI Advisor service — LLM-powered CRM insights (#731).

Two main actions:
- get_daily_plan(): Morning briefing — leads + tasks + stale deals → action plan
- get_deal_and_task_tips(): Tips for stale deals + task prioritization

Prompts are managed in Langfuse; fallbacks are hardcoded for reliability.
LLM responses use HTML formatting (not Markdown) for Telegram parse_mode=HTML.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from telegram_bot.integrations.prompt_manager import get_prompt


logger = logging.getLogger(__name__)

_BRIEFING_CACHE_TTL = 600  # 10 minutes
_STALE_THRESHOLD_SECONDS = 5 * 86400  # 5 days
_MAX_TOKENS = 600

# Langfuse prompt names
_PROMPT_DAILY_PLAN = "advisor-daily-plan"
_PROMPT_DEAL_TIPS = "advisor-deal-tips"

# Fallback prompts (used when Langfuse unavailable)
_FALLBACK_DAILY_PLAN = (
    "Ты — CRM-ассистент менеджера по продажам недвижимости.\n"
    "На основе данных о лидах, задачах и застрявших сделках составь план действий на день.\n\n"
    "Правила ответа:\n"
    "- Максимум 5 пунктов\n"
    "- Каждый пункт: конкретное действие + причина\n"
    "- Начни с самого важного (просроченные задачи → горячие лиды → застрявшие сделки)\n"
    "- Используй HTML-теги для форматирования: <b>жирный</b>, <i>курсив</i>\n"
    "- НЕ используй Markdown (* или **)"
)

_FALLBACK_DEAL_TIPS = (
    "Ты — CRM-ассистент менеджера по продажам недвижимости.\n"
    "Проанализируй застрявшие сделки и задачи, предложи конкретные действия.\n\n"
    "Правила ответа:\n"
    "- Максимум 5 пунктов\n"
    "- Для каждой сделки/задачи: что делать и почему\n"
    "- Используй HTML-теги: <b>жирный</b>, <i>курсив</i>\n"
    "- НЕ используй Markdown"
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
        """Fetch leads and format as text for LLM context."""
        try:
            leads = await self._kommo.search_leads(responsible_user_id=manager_id, limit=20)
        except Exception:
            logger.exception("Failed to fetch leads for advisor")
            return "Данные о лидах недоступны."

        if not leads:
            return "Нет активных лидов."

        return "\n".join(
            f"- {lead.name or '—'} (бюджет: {lead.budget or '—'}, создан: {lead.created_at or '—'})"
            for lead in leads
        )

    async def _fetch_tasks_text(self, manager_id: int | None) -> str:
        """Fetch open tasks and format as text for LLM context."""
        try:
            tasks = await self._kommo.get_tasks(responsible_user_id=manager_id, is_completed=False)
        except Exception:
            logger.exception("Failed to fetch tasks for advisor")
            return "Данные о задачах недоступны."

        if not tasks:
            return "Нет активных задач."

        now = int(time.time())
        return "\n".join(
            f"- {task.text or '—'} (срок: {task.complete_till or '—'}"
            f", {'ПРОСРОЧЕНО' if task.complete_till and task.complete_till < now else 'в срок'})"
            for task in tasks
        )

    async def _fetch_stale_text(self, manager_id: int | None) -> str:
        """Fetch stale deals (5+ days without updates)."""
        try:
            leads = await self._kommo.search_leads(responsible_user_id=manager_id, limit=50)
        except Exception:
            logger.exception("Failed to fetch leads for stale analysis")
            return "Данные о сделках недоступны."

        if not leads:
            return "Нет сделок."

        now = int(time.time())
        stale = [
            lead
            for lead in leads
            if lead.updated_at and (now - lead.updated_at) > _STALE_THRESHOLD_SECONDS
        ]

        if not stale:
            return "Все сделки активны."

        return "\n".join(
            f"- {lead.name or '—'} (без активности {(now - (lead.updated_at or 0)) // 86400} дней)"
            for lead in stale
        )

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

        system_prompt = get_prompt(
            name=_PROMPT_DAILY_PLAN,
            fallback=_FALLBACK_DAILY_PLAN,
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

        system_prompt = get_prompt(
            name=_PROMPT_DEAL_TIPS,
            fallback=_FALLBACK_DEAL_TIPS,
        )

        user_text = f"Задачи:\n{tasks_text}\n\nЗастрявшие сделки:\n{stale_text}"

        return await self._call_llm(system_prompt, user_text)
