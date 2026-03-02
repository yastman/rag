from unittest.mock import AsyncMock, MagicMock

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
    mock_llm = AsyncMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        "Клиент ищет квартиру в Варне, бюджет ~70к EUR. Интересуется ипотекой."
    )
    mock_llm.chat.completions.create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))
    result = await generate_handoff_summary(history, llm=mock_llm, min_messages=3)
    assert result is not None
    assert "Варне" in result
    assert "ипотек" in result.lower()
    mock_llm.chat.completions.create.assert_called_once()
