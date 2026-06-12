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

from types import SimpleNamespace

from pydantic import BaseModel


class StructuredResult(BaseModel):
    answer: str
    score: int


class ObjectResponseRouter:
    def __init__(self, content: str) -> None:
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        self.acompletion = AsyncMock(return_value=SimpleNamespace(choices=[choice]))


@pytest.mark.asyncio
async def test_chat_client_translates_response_model_to_json_schema_and_drops_wrapper_kwargs() -> None:
    router = ObjectResponseRouter('{"answer":"ok","score":9}')
    client = create_litellm_chat_client(model="gpt-4o-mini", router=router, timeout=12)

    result = await client.chat.completions.create(
        messages=[{"role": "user", "content": "hi"}],
        response_model=StructuredResult,
        max_retries=3,
        name="query-analysis",
        langfuse_prompt=object(),
    )

    assert result == StructuredResult(answer="ok", score=9)
    kwargs = router.acompletion.await_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["name"] == "StructuredResult"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert "response_model" not in kwargs
    assert "max_retries" not in kwargs
    assert "name" not in kwargs
    assert "langfuse_prompt" not in kwargs


@pytest.mark.asyncio
async def test_chat_client_parses_dict_response_content() -> None:
    router = ObjectResponseRouter({"answer": "dict-ok", "score": 7})
    client = create_litellm_chat_client(model="gpt-4o-mini", router=router, timeout=12)

    result = await client.chat.completions.create(
        messages=[{"role": "user", "content": "hi"}],
        response_model=StructuredResult,
    )

    assert result == StructuredResult(answer="dict-ok", score=7)


@pytest.mark.asyncio
async def test_chat_client_propagates_invalid_structured_json() -> None:
    router = ObjectResponseRouter("not-json")
    client = create_litellm_chat_client(model="gpt-4o-mini", router=router, timeout=12)

    with pytest.raises(ValueError):
        await client.chat.completions.create(
            messages=[{"role": "user", "content": "hi"}],
            response_model=StructuredResult,
        )
