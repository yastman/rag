from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.handoff_summary import generate_handoff_summary


@pytest.mark.asyncio
async def test_summary_returns_none_for_short_history():
    history = [{"role": "user", "content": "привет"}]
    result = await generate_handoff_summary(history, min_messages=3)
    assert result is None


@pytest.mark.asyncio
async def test_summary_returns_none_for_empty_history():
    result = await generate_handoff_summary([], min_messages=3)
    assert result is None


@pytest.mark.asyncio
async def test_summary_calls_llm_for_sufficient_history():
    history = [
        {"role": "user", "content": "Ищу квартиру в Варне"},
        {"role": "assistant", "content": "Какой бюджет?"},
        {"role": "user", "content": "Около 70 тысяч евро"},
        {"role": "assistant", "content": "Вот несколько вариантов..."},
        {"role": "user", "content": "А что с ипотекой?"},
    ]
    with patch(
        "telegram_bot.services.handoff_summary._call_llm",
        new_callable=AsyncMock,
        return_value="Клиент ищет квартиру в Варне, бюджет ~70к EUR. Интересуется ипотекой.",
    ):
        result = await generate_handoff_summary(history, min_messages=3)
    assert result is not None
    assert "Варне" in result
    assert "ипотек" in result.lower()
