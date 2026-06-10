from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.runtime.graph.config import GraphConfig
from src.runtime.llm.router import LiteLLMChatClient, build_model_list, create_litellm_chat_client


class DummyRouter:
    def __init__(self) -> None:
        self.acompletion = AsyncMock(return_value={"ok": True})


def test_model_list_preserves_proxy_fallback_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    model_list = build_model_list()

    aliases = {entry["model_name"] for entry in model_list}
    assert {
        "gpt-4o-mini",
        "gpt-oss-120b",
        "gpt-4o-mini-cerebras-oss",
        "gpt-4o-mini-fallback",
        "gpt-4o-mini-openai",
    } <= aliases
    primary = next(entry for entry in model_list if entry["model_name"] == "gpt-4o-mini")
    assert primary["litellm_params"]["model"] == "cerebras/zai-glm-4.7"
    assert primary["litellm_params"]["disable_reasoning"] is True


@pytest.mark.asyncio
async def test_chat_client_delegates_to_router_acompletion() -> None:
    router = DummyRouter()
    client = create_litellm_chat_client(model="gpt-4o-mini", router=router, timeout=12)

    result = await client.chat.completions.create(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        name="legacy-observation-name",
    )

    assert result == {"ok": True}
    router.acompletion.assert_awaited_once_with(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        model="gpt-4o-mini",
        timeout=12,
    )
    assert client._langfuse_auto_trace is False


def test_graph_config_create_llm_returns_litellm_sdk_client() -> None:
    cfg = GraphConfig(llm_model="gpt-4o-mini")
    client = cfg.create_llm()

    assert isinstance(client, LiteLLMChatClient)
    assert client.default_model == "gpt-4o-mini"
