from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.ai_advisor_service import AIAdvisorService


def _llm_with_response(content: str = "ok") -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=response)
    return llm


@pytest.mark.asyncio
async def test_ai_advisor_uses_env_llm_model() -> None:
    llm = _llm_with_response()
    service = AIAdvisorService(kommo_client=MagicMock(), llm=llm)

    with patch.dict("os.environ", {"LLM_MODEL": "router-model"}, clear=False):
        _ = await service._call_llm("system", "user")

    assert llm.chat.completions.create.call_args.kwargs["model"] == "router-model"


@pytest.mark.asyncio
async def test_ai_advisor_defaults_to_gpt_4o_mini_model() -> None:
    llm = _llm_with_response()
    service = AIAdvisorService(kommo_client=MagicMock(), llm=llm)

    with patch.dict("os.environ", {}, clear=True):
        _ = await service._call_llm("system", "user")

    assert llm.chat.completions.create.call_args.kwargs["model"] == "gpt-4o-mini"
