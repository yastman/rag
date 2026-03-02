"""AI Advisor service — LLM-powered CRM prioritization and briefings (#697).

Fetches data from KommoClient, sends to LLM for prioritization,
caches full briefing in Redis for 10 minutes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any


logger = logging.getLogger(__name__)

_BRIEFING_CACHE_TTL = 600  # 10 minutes
_STALE_THRESHOLD_SECONDS = 5 * 86400  # 5 days


class AIAdvisorService:
    """LLM-powered manager advisor: prioritizes leads, tasks, and analyzes stale deals."""

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

    async def get_prioritized_leads(self, manager_id: int | None) -> str:
        """Fetch recent leads and return LLM-prioritized list.

        Args:
            manager_id: Kommo responsible_user_id to filter leads. None = all.

        Returns:
            Formatted prioritized leads text or error/empty message.
        """
        try:
            leads = await self._kommo.search_leads(responsible_user_id=manager_id, limit=20)
        except Exception:
            logger.exception("Failed to fetch leads from Kommo")
            return "❌ Не удалось получить лиды из CRM."

        if not leads:
            return "Нет активных лидов."

        leads_text = "\n".join(
            f"- {lead.name or '—'} (ID:{lead.id}"
            f", бюджет:{lead.budget or '—'}"
            f", создан:{lead.created_at or '—'})"
            for lead in leads
        )

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты CRM-ассистент менеджера по продажам недвижимости.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Проранжируй лидов по приоритету "
                            "(бюджет, давность, активность). "
                            "Дай краткие рекомендации по каждому.\n\n"
                            f"{leads_text}"
                        ),
                    },
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content or "Нет ответа от LLM."
        except Exception:
            logger.exception("LLM prioritization failed for leads")
            return "❌ Ошибка при генерации приоритизации лидов."

    async def get_prioritized_tasks(self, manager_id: int | None) -> str:
        """Fetch open tasks and return LLM-prioritized list.

        Args:
            manager_id: Kommo responsible_user_id to filter tasks. None = all.

        Returns:
            Formatted prioritized tasks text or error/empty message.
        """
        try:
            tasks = await self._kommo.get_tasks(responsible_user_id=manager_id, is_completed=False)
        except Exception:
            logger.exception("Failed to fetch tasks from Kommo")
            return "❌ Не удалось получить задачи из CRM."

        if not tasks:
            return "Нет активных задач."

        now = int(time.time())
        tasks_text = "\n".join(
            f"- {task.text or '—'} (ID:{task.id}"
            f", срок:{task.complete_till or '—'}"
            f", {'ПРОСРОЧЕНО' if task.complete_till and task.complete_till < now else 'в срок'})"
            for task in tasks
        )

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты CRM-ассистент. "
                            "Расставь задачи по приоритету: просроченные > сегодня > по важности."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Задачи менеджера:\n{tasks_text}",
                    },
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content or "Нет ответа от LLM."
        except Exception:
            logger.exception("LLM prioritization failed for tasks")
            return "❌ Ошибка при генерации приоритизации задач."

    async def get_stale_deals(self, manager_id: int | None) -> str:
        """Fetch leads and identify stale deals (no activity 5+ days).

        Args:
            manager_id: Kommo responsible_user_id to filter leads. None = all.

        Returns:
            Formatted stale deals analysis or 'all active' message.
        """
        try:
            leads = await self._kommo.search_leads(responsible_user_id=manager_id, limit=50)
        except Exception:
            logger.exception("Failed to fetch leads from Kommo for stale analysis")
            return "❌ Не удалось получить сделки из CRM."

        if not leads:
            return "Нет сделок."

        now = int(time.time())
        stale = [
            lead
            for lead in leads
            if lead.updated_at and (now - lead.updated_at) > _STALE_THRESHOLD_SECONDS
        ]

        if not stale:
            return "Все сделки активны — нет застрявших."

        leads_text = "\n".join(
            f"- {lead.name or '—'} (ID:{lead.id}"
            f", обновлено {(now - (lead.updated_at or 0)) // 86400} дней назад)"
            for lead in stale
        )

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты CRM-ассистент. Проанализируй застрявшие сделки и предложи действия."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Сделки без активности 5+ дней:\n{leads_text}",
                    },
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content or "Нет ответа от LLM."
        except Exception:
            logger.exception("LLM analysis failed for stale deals")
            return "❌ Ошибка при анализе застрявших сделок."

    async def get_full_briefing(self, manager_id: int | None) -> str:
        """Fetch all CRM data and generate a morning briefing.

        Combines prioritized leads, tasks, and stale deals analysis.
        Result is cached in Redis for 10 minutes per manager.

        Args:
            manager_id: Kommo responsible_user_id. None = all.

        Returns:
            Full morning briefing text.
        """
        cache_key = f"advisor:briefing:{manager_id}"

        # Check cache
        if self._cache and getattr(self._cache, "redis", None):
            try:
                cached = await self._cache.redis.get(cache_key)
                if cached:
                    return cached
            except Exception:
                logger.warning("Cache get failed for briefing key=%s", cache_key)

        # Fetch all in parallel
        leads_text, tasks_text, stale_text = await asyncio.gather(
            self.get_prioritized_leads(manager_id),
            self.get_prioritized_tasks(manager_id),
            self.get_stale_deals(manager_id),
        )

        briefing = (
            "📋 *Утренний брифинг*\n\n"
            f"🔥 *Лиды:*\n{leads_text}\n\n"
            f"✅ *Задачи:*\n{tasks_text}\n\n"
            f"📊 *Застрявшие сделки:*\n{stale_text}"
        )

        # Store in cache
        if self._cache and getattr(self._cache, "redis", None):
            try:
                await self._cache.redis.setex(cache_key, _BRIEFING_CACHE_TTL, briefing)
            except Exception:
                logger.warning("Cache set failed for briefing key=%s", cache_key)

        return briefing
