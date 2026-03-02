"""Tests for AIAdvisorService — redesigned with Langfuse prompts (#731)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.kommo_models import Lead


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
