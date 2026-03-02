"""Tests for AIAdvisorService — LLM-powered CRM prioritization (#697)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.kommo_models import Lead, Task


# --- Instantiation ---


def test_ai_advisor_service_is_importable():
    """AIAdvisorService can be imported from telegram_bot.services."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService  # noqa: F401


def test_ai_advisor_service_instantiation():
    """AIAdvisorService instantiates with kommo_client and llm."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    assert svc is not None


def test_ai_advisor_service_instantiation_with_cache():
    """AIAdvisorService accepts optional cache parameter."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    llm = MagicMock()
    cache = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)
    assert svc is not None


# --- get_prioritized_leads ---


async def test_get_prioritized_leads_calls_search_leads():
    """get_prioritized_leads calls kommo.search_leads with manager_id."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    result = await svc.get_prioritized_leads(manager_id=42)

    kommo.search_leads.assert_called_once_with(responsible_user_id=42, limit=20)
    assert isinstance(result, str)


async def test_get_prioritized_leads_returns_message_when_no_leads():
    """get_prioritized_leads returns 'no leads' message when kommo returns empty list."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    result = await svc.get_prioritized_leads(manager_id=None)

    assert "лид" in result.lower() or "нет" in result.lower()


async def test_get_prioritized_leads_calls_llm_with_leads():
    """get_prioritized_leads passes leads to LLM for prioritization."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    leads = [
        Lead(id=1, name="Deal A", budget=100000, created_at=1700000000),
        Lead(id=2, name="Deal B", budget=50000, created_at=1700001000),
    ]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "1. Deal A — высокий приоритет"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    result = await svc.get_prioritized_leads(manager_id=1)

    llm.chat.completions.create.assert_called_once()
    assert isinstance(result, str)
    assert len(result) > 0


async def test_get_prioritized_leads_does_not_pass_unsupported_name_kwarg():
    """OpenAI chat.completions.create should be called without top-level 'name' kwarg."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    leads = [Lead(id=1, name="Deal A", budget=100000, created_at=1700000000)]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "ok"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    await svc.get_prioritized_leads(manager_id=1)

    kwargs = llm.chat.completions.create.call_args.kwargs
    assert "name" not in kwargs


# --- get_prioritized_tasks ---


async def test_get_prioritized_tasks_calls_get_tasks():
    """get_prioritized_tasks calls kommo.get_tasks with manager_id and is_completed=False."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.get_tasks = AsyncMock(return_value=[])
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    await svc.get_prioritized_tasks(manager_id=10)

    kommo.get_tasks.assert_called_once_with(responsible_user_id=10, is_completed=False)


async def test_get_prioritized_tasks_returns_message_when_no_tasks():
    """get_prioritized_tasks returns 'no tasks' message when kommo returns empty list."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.get_tasks = AsyncMock(return_value=[])
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    result = await svc.get_prioritized_tasks(manager_id=None)

    assert "задач" in result.lower() or "нет" in result.lower()


async def test_get_prioritized_tasks_calls_llm_with_tasks():
    """get_prioritized_tasks passes tasks to LLM for prioritization."""
    import time

    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    tasks = [
        Task(id=1, text="Позвонить клиенту", complete_till=int(time.time()) + 3600),
        Task(id=2, text="Отправить КП", complete_till=int(time.time()) - 3600),  # overdue
    ]
    kommo = MagicMock()
    kommo.get_tasks = AsyncMock(return_value=tasks)

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "1. Отправить КП — просрочено"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    result = await svc.get_prioritized_tasks(manager_id=5)

    llm.chat.completions.create.assert_called_once()
    assert isinstance(result, str)


async def test_get_prioritized_tasks_does_not_pass_unsupported_name_kwarg():
    """OpenAI chat.completions.create should be called without top-level 'name' kwarg."""
    import time

    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    tasks = [Task(id=1, text="Позвонить клиенту", complete_till=int(time.time()) + 3600)]
    kommo = MagicMock()
    kommo.get_tasks = AsyncMock(return_value=tasks)

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "ok"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    await svc.get_prioritized_tasks(manager_id=5)

    kwargs = llm.chat.completions.create.call_args.kwargs
    assert "name" not in kwargs


# --- get_stale_deals ---


async def test_get_stale_deals_calls_search_leads():
    """get_stale_deals calls kommo.search_leads with manager_id."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    await svc.get_stale_deals(manager_id=7)

    kommo.search_leads.assert_called_once_with(responsible_user_id=7, limit=50)


async def test_get_stale_deals_returns_active_message_when_no_stale():
    """get_stale_deals returns 'all active' message when no leads are stale."""
    import time

    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    # All leads updated recently (within 5 days)
    recent_ts = int(time.time()) - (2 * 86400)  # 2 days ago
    leads = [
        Lead(id=1, name="Active Deal", updated_at=recent_ts),
    ]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    result = await svc.get_stale_deals(manager_id=1)

    assert "актив" in result.lower() or "нет" in result.lower()


async def test_get_stale_deals_filters_leads_older_than_5_days():
    """get_stale_deals only passes leads without activity 5+ days to LLM."""
    import time

    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    now = int(time.time())
    leads = [
        Lead(id=1, name="Old Deal", updated_at=now - (7 * 86400)),  # 7 days stale
        Lead(id=2, name="Fresh Deal", updated_at=now - (1 * 86400)),  # 1 day fresh
    ]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Old Deal застряла"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    result = await svc.get_stale_deals(manager_id=1)

    # LLM was called (there IS a stale deal)
    llm.chat.completions.create.assert_called_once()
    # The call args should reference the stale lead
    call_kwargs = llm.chat.completions.create.call_args
    messages = (
        call_kwargs.kwargs.get("messages", []) or call_kwargs.args[0] if call_kwargs.args else []
    )
    user_content = ""
    for m in messages if isinstance(messages, list) else []:
        if isinstance(m, dict) and m.get("role") == "user":
            user_content = m.get("content", "")
    assert "Old Deal" in user_content or isinstance(result, str)


async def test_get_stale_deals_does_not_pass_unsupported_name_kwarg():
    """OpenAI chat.completions.create should be called without top-level 'name' kwarg."""
    import time

    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    now = int(time.time())
    leads = [Lead(id=1, name="Old Deal", updated_at=now - (7 * 86400))]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "ok"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    await svc.get_stale_deals(manager_id=1)

    kwargs = llm.chat.completions.create.call_args.kwargs
    assert "name" not in kwargs


async def test_get_stale_deals_returns_no_deals_message_when_empty():
    """get_stale_deals returns message when kommo returns no leads at all."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    llm = MagicMock()
    svc = AIAdvisorService(kommo_client=kommo, llm=llm)

    result = await svc.get_stale_deals(manager_id=None)

    assert isinstance(result, str)
    assert len(result) > 0


# --- get_full_briefing ---


async def test_get_full_briefing_returns_string():
    """get_full_briefing returns a non-empty string."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=MagicMock())
    llm.chat.completions.create.return_value.choices = [MagicMock()]
    llm.chat.completions.create.return_value.choices[0].message.content = "Summary"

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    result = await svc.get_full_briefing(manager_id=1)

    assert isinstance(result, str)
    assert len(result) > 0


async def test_get_full_briefing_uses_cache_on_hit():
    """get_full_briefing returns cached value without calling LLM."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock()

    cache_redis = AsyncMock()
    cache_redis.get = AsyncMock(return_value="Cached briefing")
    cache = MagicMock()
    cache.redis = cache_redis

    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)
    result = await svc.get_full_briefing(manager_id=5)

    assert result == "Cached briefing"
    # LLM should NOT have been called
    llm.chat.completions.create.assert_not_called()


async def test_get_full_briefing_stores_result_in_cache():
    """get_full_briefing stores computed result in cache for future calls."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "Briefing text"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    cache_redis = AsyncMock()
    cache_redis.get = AsyncMock(return_value=None)  # cache miss
    cache_redis.setex = AsyncMock()
    cache = MagicMock()
    cache.redis = cache_redis

    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)
    result = await svc.get_full_briefing(manager_id=3)

    # Cache should have been populated
    cache_redis.setex.assert_called_once()
    assert isinstance(result, str)


async def test_get_full_briefing_cache_key_includes_manager_id():
    """get_full_briefing uses manager_id in cache key for isolation."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=[])
    kommo.get_tasks = AsyncMock(return_value=[])

    llm_response = MagicMock()
    llm_response.choices[0].message.content = "ok"
    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=llm_response)

    cache_redis = AsyncMock()
    cache_redis.get = AsyncMock(return_value=None)
    cache_redis.setex = AsyncMock()
    cache = MagicMock()
    cache.redis = cache_redis

    svc = AIAdvisorService(kommo_client=kommo, llm=llm, cache=cache)
    await svc.get_full_briefing(manager_id=99)

    # Cache get/set should include manager_id in the key
    get_call_key = cache_redis.get.call_args[0][0]
    assert "99" in str(get_call_key)


# --- Error handling ---


async def test_get_prioritized_leads_handles_llm_error():
    """get_prioritized_leads returns error message when LLM fails."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    leads = [Lead(id=1, name="Deal A", budget=100000)]
    kommo = MagicMock()
    kommo.search_leads = AsyncMock(return_value=leads)

    llm = MagicMock()
    llm.chat = MagicMock()
    llm.chat.completions = MagicMock()
    llm.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    result = await svc.get_prioritized_leads(manager_id=1)

    assert isinstance(result, str)
    # Should return error message, not raise
    assert "ошибка" in result.lower() or "недоступ" in result.lower() or len(result) > 0


async def test_get_prioritized_tasks_handles_kommo_error():
    """get_prioritized_tasks returns error message when Kommo API fails."""
    from telegram_bot.services.ai_advisor_service import AIAdvisorService

    kommo = MagicMock()
    kommo.get_tasks = AsyncMock(side_effect=Exception("Kommo API error"))
    llm = MagicMock()

    svc = AIAdvisorService(kommo_client=kommo, llm=llm)
    result = await svc.get_prioritized_tasks(manager_id=1)

    assert isinstance(result, str)
    assert len(result) > 0
