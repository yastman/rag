"""Tests for AIAdvisorService — redesigned with Langfuse prompts (#731)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.kommo_models import Lead, Task


# --- Instantiation ---


def test_ai_advisor_service_is_importable():
    """AIAdvisorService can be imported from telegram_bot.services."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService  # noqa: F401


def test_ai_advisor_service_instantiation():
    """AIAdvisorService instantiates with kommo_client and llm."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    svc = AIAdvisorService(kommo_client=MagicMock(), llm=MagicMock())
    assert svc is not None


def test_ai_advisor_service_instantiation_with_cache():
    """AIAdvisorService accepts optional cache parameter."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    svc = AIAdvisorService(kommo_client=MagicMock(), llm=MagicMock(), cache=MagicMock())
    assert svc is not None


# --- Method existence ---


def test_get_daily_plan_method_exists():
    """AIAdvisorService has get_daily_plan method."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    assert hasattr(AIAdvisorService, "get_daily_plan")


def test_get_deal_and_task_tips_method_exists():
    """AIAdvisorService has get_deal_and_task_tips method."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    assert hasattr(AIAdvisorService, "get_deal_and_task_tips")


# --- get_daily_plan ---


@patch("telegram_bot.services.ai_advisor_service.get_prompt")
async def test_daily_plan_uses_langfuse_prompt(mock_get_prompt: MagicMock) -> None:
    """get_daily_plan fetches prompt from Langfuse via get_prompt()."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    mock_get_prompt.return_value = "System prompt from Langfuse"

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Plan"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    await svc.get_daily_plan(None)

    mock_get_prompt.assert_called()


@patch("telegram_bot.services.ai_advisor_service.get_prompt")
async def test_deal_tips_uses_langfuse_prompt(mock_get_prompt: MagicMock) -> None:
    """get_deal_and_task_tips fetches prompt from Langfuse via get_prompt()."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    mock_get_prompt.return_value = "System prompt from Langfuse"

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Tips"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    await svc.get_deal_and_task_tips(None)

    mock_get_prompt.assert_called()


async def test_get_daily_plan_returns_string() -> None:
    """get_daily_plan returns non-empty string."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Ваш план на день"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        result = await svc.get_daily_plan(manager_id=1)

    assert isinstance(result, str)
    assert len(result) > 0


async def test_get_deal_and_task_tips_returns_string() -> None:
    """get_deal_and_task_tips returns non-empty string."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Советы по сделкам"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        result = await svc.get_deal_and_task_tips(manager_id=1)

    assert isinstance(result, str)
    assert len(result) > 0


async def test_get_daily_plan_fetches_leads_tasks_and_stale() -> None:
    """get_daily_plan fetches leads, tasks and stale data."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Plan"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        await svc.get_daily_plan(manager_id=5)

    # search_leads and get_tasks should both be called
    assert kommo.search_leads.call_count >= 1
    kommo.get_tasks.assert_called()


async def test_get_deal_and_task_tips_fetches_tasks_and_stale() -> None:
    """get_deal_and_task_tips fetches tasks and stale deals."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Tips"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        await svc.get_deal_and_task_tips(manager_id=5)

    kommo.get_tasks.assert_called()
    kommo.search_leads.assert_called()


async def test_get_daily_plan_uses_cache_on_hit() -> None:
    """get_daily_plan returns cached value without calling LLM."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    cache_redis = AsyncMock()
    cache_redis.get = AsyncMock(return_value="Cached plan")
    cache = MagicMock()
    cache.redis = cache_redis

    llm = MagicMock()
    llm.chat.completions.create = AsyncMock()
    kommo = MagicMock()

    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        result = await svc.get_daily_plan(manager_id=5)

    assert result == "Cached plan"
    llm.chat.completions.create.assert_not_called()


async def test_get_daily_plan_stores_result_in_cache() -> None:
    """get_daily_plan stores computed result in cache for future calls."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Plan text"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    cache_redis = AsyncMock()
    cache_redis.get = AsyncMock(return_value=None)  # cache miss
    cache_redis.setex = AsyncMock()
    cache = MagicMock()
    cache.redis = cache_redis

    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        await svc.get_daily_plan(manager_id=3)

    cache_redis.setex.assert_called_once()


async def test_get_daily_plan_cache_key_includes_manager_id() -> None:
    """get_daily_plan uses manager_id in cache key for isolation."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "ok"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    cache_redis = AsyncMock()
    cache_redis.get = AsyncMock(return_value=None)
    cache_redis.setex = AsyncMock()
    cache = MagicMock()
    cache.redis = cache_redis

    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        await svc.get_daily_plan(manager_id=99)

    get_call_key = cache_redis.get.call_args[0][0]
    assert "99" in str(get_call_key)


async def test_get_daily_plan_handles_kommo_error() -> None:
    """get_daily_plan returns string when Kommo API fails."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(side_effect=Exception("Kommo error"))
    kommo.get_tasks = AsyncMock(side_effect=Exception("Kommo error"))

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Plan despite error"
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        result = await svc.get_daily_plan(manager_id=1)

    assert isinstance(result, str)


async def test_get_daily_plan_handles_llm_error() -> None:
    """get_daily_plan returns error string when LLM fails."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        result = await svc.get_daily_plan(manager_id=1)

    assert isinstance(result, str)
    assert len(result) > 0


# --- Formatting helpers ---


def test_format_budget_with_value():
    """_format_budget formats integer as € with space separator."""
    from telegram_bot.services.ai_advisor_service import _format_budget

    assert _format_budget(50000) == "€50 000"


def test_format_budget_none():
    """_format_budget returns dash for None."""
    from telegram_bot.services.ai_advisor_service import _format_budget

    assert _format_budget(None) == "—"


def test_format_budget_zero():
    """_format_budget returns €0 for zero."""
    from telegram_bot.services.ai_advisor_service import _format_budget

    assert _format_budget(0) == "€0"


def test_format_date_with_timestamp():
    """_format_date returns human-readable Russian date."""
    from telegram_bot.services.ai_advisor_service import _format_date

    # 2025-03-01 00:00:00 UTC = 1740787200
    result = _format_date(1740787200)
    assert "2025" in result
    assert "мар" in result.lower() or "марта" in result.lower()


def test_format_date_none():
    """_format_date returns dash for None."""
    from telegram_bot.services.ai_advisor_service import _format_date

    assert _format_date(None) == "—"


def test_format_days_ago_recent():
    """_format_days_ago shows days count."""
    from telegram_bot.services.ai_advisor_service import _format_days_ago

    now = int(time.time())
    three_days_ago = now - 3 * 86400
    result = _format_days_ago(three_days_ago, now)
    assert "3" in result
    assert "дн" in result


def test_format_days_ago_none():
    """_format_days_ago returns dash for None."""
    from telegram_bot.services.ai_advisor_service import _format_days_ago

    assert _format_days_ago(None, int(time.time())) == "—"


def test_format_days_ago_today():
    """_format_days_ago shows 'сегодня' for 0 days."""
    from telegram_bot.services.ai_advisor_service import _format_days_ago

    now = int(time.time())
    result = _format_days_ago(now, now)
    assert "сегодня" in result.lower()


# --- _fetch_leads_text rich formatting ---


async def test_fetch_leads_text_formats_rich_data():
    """_fetch_leads_text returns human-readable lead data with budget and dates."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    leads = [
        Lead(id=1, name="Иванов", budget=50000, created_at=1740787200, updated_at=1740700800),
        Lead(id=2, name="Петров", budget=None, created_at=1740787200, updated_at=None),
    ]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    svc = AIAdvisorService(kommo_client=kommo, llm=MagicMock())
    result = await svc._fetch_leads_text(manager_id=1)

    assert "Иванов" in result
    assert "€50 000" in result
    assert "2025" in result  # human date


# --- _fetch_tasks_text rich formatting ---


async def test_fetch_tasks_text_formats_rich_data():
    """_fetch_tasks_text shows human dates, overdue markers, linked lead name."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    now_ts = int(time.time())
    tasks = [
        Task(
            id=10,
            text="Перезвонить",
            complete_till=now_ts - 2 * 86400,
            entity_id=1,
            entity_type="leads",
        ),
        Task(
            id=11,
            text="Отправить КП",
            complete_till=now_ts + 86400,
            entity_id=2,
            entity_type="leads",
        ),
    ]
    kommo = MagicMock()
    kommo.get_tasks = AsyncMock(return_value=tasks)

    svc = AIAdvisorService(kommo_client=kommo, llm=MagicMock())
    result = await svc._fetch_tasks_text(manager_id=1)

    assert "Перезвонить" in result
    assert "просрочен" in result.lower()
    assert "Отправить КП" in result


# --- _fetch_stale_text categorized ---


async def test_fetch_stale_text_categorizes_by_severity():
    """_fetch_stale_text groups deals by inactivity severity."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    now_ts = int(time.time())
    leads = [
        Lead(id=1, name="Критичный", budget=80000, updated_at=now_ts - 20 * 86400),
        Lead(id=2, name="Внимание", budget=30000, updated_at=now_ts - 10 * 86400),
        Lead(id=3, name="Напомнить", budget=10000, updated_at=now_ts - 6 * 86400),
        Lead(id=4, name="Активный", budget=5000, updated_at=now_ts - 1 * 86400),
    ]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    svc = AIAdvisorService(kommo_client=kommo, llm=MagicMock())
    result = await svc._fetch_stale_text(manager_id=1)

    assert "Критичный" in result
    assert "Внимание" in result
    assert "Напомнить" in result
    # Активный (1 день) не должен быть в stale
    assert "Активный" not in result
    assert "20" in result  # дней без активности


# --- Fallback prompts contract-style ---


def test_fallback_daily_plan_is_contract_style():
    """Fallback daily plan prompt contains prioritization logic and HTML rules."""
    from telegram_bot.services.ai_advisor_service import _FALLBACK_DAILY_PLAN

    text = _FALLBACK_DAILY_PLAN
    assert "недвижимост" in text.lower()  # домен
    assert "Болгари" in text  # регион
    assert "HTML" in text  # формат
    assert "ПРОСРОЧЕН" in text or "просроченн" in text.lower()  # приоритизация
    assert "{{today}}" in text  # переменная для даты


def test_fallback_deal_tips_is_contract_style():
    """Fallback deal tips prompt contains analysis logic and HTML rules."""
    from telegram_bot.services.ai_advisor_service import _FALLBACK_DEAL_TIPS

    text = _FALLBACK_DEAL_TIPS
    assert "недвижимост" in text.lower()
    assert "HTML" in text
    assert "{{today}}" in text


# --- Existing backward-compat test ---


async def test_get_prioritized_leads_handles_llm_error() -> None:
    """Backward compat: get_daily_plan returns error message when LLM fails."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    leads = [Lead(id=1, name="Deal A", budget=100000)]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)
    kommo.get_tasks = AsyncMock(return_value=[])

    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    with patch("telegram_bot.services.ai_advisor_service.get_prompt", return_value="prompt"):
        result = await svc.get_daily_plan(manager_id=1)

    assert isinstance(result, str)
    assert len(result) > 0
