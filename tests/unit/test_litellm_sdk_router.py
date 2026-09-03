"""Native LiteLLM SDK boundary contract tests (#3223).

Parity/canary coverage for the frozen LLM contract: provider fallback
aliases, one-call Router delegation, structured-output schema translation,
streaming passthrough and connection-error normalization — all against a
stubbed Router transport (no live LLM calls).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from litellm.exceptions import APIConnectionError
from pydantic import BaseModel

from src.adapters.llm.base import LLMConnectionError
from src.runtime.config import GraphConfig
from src.runtime.llm.router import (
    DEFAULT_TIMEOUT_SECONDS,
    LiteLlmClient,
    build_model_list,
    create_llm_client,
    normalize_connection_error,
)


class DummyRouter:
    def __init__(self, response: object | None = None) -> None:
        self.acompletion = AsyncMock(
            return_value=response if response is not None else {"ok": True}
        )


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
async def test_completion_delegates_one_call_to_router_acompletion() -> None:
    router = DummyRouter()
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    result = await client.completion(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
    )

    assert result == {"ok": True}
    router.acompletion.assert_awaited_once_with(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.1,
        model="gpt-4o-mini",
        timeout=12,
    )


@pytest.mark.asyncio
async def test_completion_defaults_model_and_timeout_and_never_forwards_observation_name() -> None:
    router = DummyRouter()
    client = LiteLlmClient(router=router)

    await client.completion(
        messages=[{"role": "user", "content": "hi"}],
        observation_name="rewrite-query",
    )

    kwargs = router.acompletion.await_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert "observation_name" not in kwargs
    assert "name" not in kwargs


def test_graph_config_create_llm_returns_native_client() -> None:
    cfg = GraphConfig(llm_model="gpt-4o-mini")
    client = cfg.create_llm()

    assert isinstance(client, LiteLlmClient)
    assert client.default_model == "gpt-4o-mini"


class StructuredResult(BaseModel):
    answer: str
    score: int


class ObjectResponseRouter:
    def __init__(self, content: object) -> None:
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        self.acompletion = AsyncMock(return_value=SimpleNamespace(choices=[choice]))


@pytest.mark.asyncio
async def test_structured_translates_pydantic_schema_and_validates_response() -> None:
    router = ObjectResponseRouter('{"answer":"ok","score":9}')
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    result = await client.structured(
        messages=[{"role": "user", "content": "hi"}],
        response_model=StructuredResult,
    )

    assert result == StructuredResult(answer="ok", score=9)
    kwargs = router.acompletion.await_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["name"] == "StructuredResult"
    assert kwargs["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_structured_parses_dict_response_content() -> None:
    router = ObjectResponseRouter({"answer": "dict-ok", "score": 7})
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    result = await client.structured(
        messages=[{"role": "user", "content": "hi"}],
        response_model=StructuredResult,
    )

    assert result == StructuredResult(answer="dict-ok", score=7)


@pytest.mark.asyncio
async def test_structured_propagates_invalid_structured_json() -> None:
    router = ObjectResponseRouter("not-json")
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    with pytest.raises(ValueError):
        await client.structured(
            messages=[{"role": "user", "content": "hi"}],
            response_model=StructuredResult,
        )


@pytest.mark.asyncio
async def test_stream_forces_stream_flag_and_returns_native_iterator() -> None:
    router = DummyRouter(response="native-async-iterator")
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    stream = await client.stream(
        messages=[{"role": "user", "content": "hi"}],
        stream_options={"include_usage": True},
    )

    assert stream == "native-async-iterator"
    kwargs = router.acompletion.await_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}
    assert kwargs["model"] == "gpt-4o-mini"


def test_normalize_connection_error_maps_only_connection_failures() -> None:
    connection_exc = APIConnectionError("refused", llm_provider="test", model="test")
    normalized = normalize_connection_error(connection_exc)
    assert isinstance(normalized, LLMConnectionError)
    assert normalized.raw_error is connection_exc
    assert normalize_connection_error(RuntimeError("other")) is None


@pytest.mark.asyncio
async def test_stream_owns_stream_flag_and_drops_caller_supplied_value() -> None:
    """C1 regression: a caller-supplied `stream` kwarg must not collide with the forced flag."""
    router = DummyRouter(response="native-async-iterator")
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    stream = await client.stream(
        messages=[{"role": "user", "content": "hi"}],
        stream=True,  # shim-era habit; the client owns this flag
        stream_options={"include_usage": True},
    )

    assert stream == "native-async-iterator"
    kwargs = router.acompletion.await_args.kwargs
    assert kwargs["stream"] is True  # forced exactly once — no TypeError
    assert kwargs["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("shim_kwarg", ["name", "max_retries"])
async def test_completion_rejects_shim_era_kwargs(shim_kwarg: str) -> None:
    """Shim-era kwargs are rejected loudly instead of silently reaching the SDK."""
    router = DummyRouter()
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    with pytest.raises(TypeError, match="shim-era keyword argument"):
        await client.completion(
            messages=[{"role": "user", "content": "hi"}],
            **{shim_kwarg: "generate-answer"},
        )

    router.acompletion.assert_not_awaited()
