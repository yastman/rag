"""Native LiteLLM SDK boundary contract tests (#3223).

Parity/canary coverage for the frozen LLM contract: provider fallback
aliases, one-call Router delegation, structured-output schema translation,
and connection-error normalization — all against a stubbed Router transport
(no live LLM calls).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import litellm
import pytest
from litellm import ModelResponse
from litellm.exceptions import APIConnectionError, RateLimitError
from pydantic import BaseModel

import src.runtime.llm.router as llm_router_module
from src.adapters.llm.base import LLMConnectionError
from src.runtime.config import GraphConfig
from src.runtime.llm.router import (
    DEFAULT_TIMEOUT_SECONDS,
    LiteLlmClient,
    build_model_list,
    create_llm_client,
    get_litellm_router,
    normalize_connection_error,
)


class DummyRouter:
    def __init__(self, response: object | None = None) -> None:
        self.acompletion = AsyncMock(
            return_value=response if response is not None else {"ok": True}
        )


class FailingRouter:
    """Router double whose ``acompletion`` always raises the given provider error (#3483)."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc
        self.calls: list[dict[str, object]] = []

    async def acompletion(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise self.exc


class ProviderTransport:
    """Provider transport double placed below LiteLLM's real Router machinery."""

    def __init__(self, failed_models: set[str]) -> None:
        self._failed_models = failed_models
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> ModelResponse:
        model = kwargs["model"]
        timeout = kwargs["timeout"]
        assert isinstance(model, str)
        self.calls.append({"model": model, "timeout": timeout})
        if model in self._failed_models:
            raise litellm.InternalServerError(
                "retriable provider failure",
                llm_provider=model.split("/", maxsplit=1)[0],
                model=model,
            )
        return ModelResponse(
            model=model,
            choices=[{"message": {"role": "assistant", "content": "fallback success"}}],
        )


def _real_router(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Build the production model list with harmless credentials for a real Router test."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-cerebras-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("LITELLM_PRIMARY_MODEL", "cerebras/test-primary")
    monkeypatch.setenv("LITELLM_CEREBRAS_FALLBACK_MODEL", "cerebras/test-secondary")
    monkeypatch.setenv("LITELLM_GROQ_FALLBACK_MODEL", "groq/test-groq")
    monkeypatch.setenv("LITELLM_OPENAI_FALLBACK_MODEL", "openai/test-openai")
    get_litellm_router.cache_clear()
    router = get_litellm_router()
    monkeypatch.setattr(router, "_time_to_sleep_before_retry", lambda **_kwargs: 0)
    return router


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
    models_by_alias = {
        entry["model_name"]: entry["litellm_params"]["model"] for entry in model_list
    }
    assert models_by_alias["gpt-4o-mini-cerebras-oss"].startswith("cerebras/")
    assert models_by_alias["gpt-4o-mini-fallback"].startswith("groq/")
    assert models_by_alias["gpt-4o-mini-openai"].startswith("openai/")


def test_router_configuration_preserves_retries_timeout_and_provider_fallback_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retries stay in LiteLLM and fallbacks remain Cerebras, Groq, then OpenAI."""
    captured: dict[str, Any] = {}

    class CapturingRouter:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.delenv("LITELLM_NUM_RETRIES", raising=False)
    monkeypatch.delenv("LITELLM_REQUEST_TIMEOUT", raising=False)
    get_litellm_router.cache_clear()
    monkeypatch.setattr(llm_router_module, "Router", CapturingRouter)
    try:
        get_litellm_router()
    finally:
        get_litellm_router.cache_clear()

    assert captured["num_retries"] == 2
    assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert captured["fallbacks"] == [
        {
            "gpt-4o-mini": [
                "gpt-4o-mini-cerebras-oss",
                "gpt-4o-mini-fallback",
                "gpt-4o-mini-openai",
            ]
        },
        {
            "gpt-oss-120b": [
                "gpt-4o-mini-cerebras-oss",
                "gpt-4o-mini-fallback",
                "gpt-4o-mini-openai",
            ]
        },
    ]


@pytest.mark.asyncio
async def test_real_router_retries_then_falls_back_in_provider_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiteLLM 1.98.0 itself owns two retries before each configured fallback."""
    router = _real_router(monkeypatch)
    transport = ProviderTransport({"cerebras/test-primary", "cerebras/test-secondary"})
    monkeypatch.setattr(litellm, "acompletion", transport)
    try:
        client = LiteLlmClient(router=router, timeout=17.25)
        response = await client.completion(messages=[{"role": "user", "content": "hi"}])
    finally:
        get_litellm_router.cache_clear()

    assert response.choices[0].message.content == "fallback success"
    assert transport.calls == [
        {"model": "cerebras/test-primary", "timeout": 17.25},
        {"model": "cerebras/test-primary", "timeout": 17.25},
        {"model": "cerebras/test-primary", "timeout": 17.25},
        {"model": "cerebras/test-secondary", "timeout": 17.25},
        {"model": "cerebras/test-secondary", "timeout": 17.25},
        {"model": "cerebras/test-secondary", "timeout": 17.25},
        {"model": "groq/test-groq", "timeout": 17.25},
    ]


@pytest.mark.asyncio
async def test_real_router_retries_and_falls_back_after_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider timeout follows the same Router retry/fallback path without wall-clock timing."""
    router = _real_router(monkeypatch)
    calls: list[dict[str, Any]] = []

    async def timed_out_provider(**kwargs: Any) -> ModelResponse:
        model = kwargs["model"]
        timeout = kwargs["timeout"]
        assert isinstance(model, str)
        calls.append({"model": model, "timeout": timeout})
        if model.startswith("cerebras/"):
            raise litellm.Timeout(
                "provider timed out",
                llm_provider="cerebras",
                model=model,
            )
        return ModelResponse(
            model=model,
            choices=[{"message": {"role": "assistant", "content": "timeout fallback success"}}],
        )

    monkeypatch.setattr(litellm, "acompletion", timed_out_provider)
    try:
        client = LiteLlmClient(router=router, timeout=17.25)
        response = await client.completion(messages=[{"role": "user", "content": "hi"}])
    finally:
        get_litellm_router.cache_clear()

    assert response.choices[0].message.content == "timeout fallback success"
    assert calls == [
        {"model": "cerebras/test-primary", "timeout": 17.25},
        {"model": "cerebras/test-primary", "timeout": 17.25},
        {"model": "cerebras/test-primary", "timeout": 17.25},
        {"model": "cerebras/test-secondary", "timeout": 17.25},
        {"model": "cerebras/test-secondary", "timeout": 17.25},
        {"model": "cerebras/test-secondary", "timeout": 17.25},
        {"model": "groq/test-groq", "timeout": 17.25},
    ]


@pytest.mark.asyncio
async def test_real_router_falls_back_after_downstream_bad_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A downstream provider 400 is distinct from invalid caller input.

    LiteLLM 1.98.0 does not retry this non-retriable response, but its configured
    Router fallback chain still tries each model group. Local malformed input is
    rejected by ``LiteLlmClient`` before this SDK path begins.
    """
    router = _real_router(monkeypatch)
    calls: list[str] = []

    async def invalid_provider_input(**kwargs: Any) -> ModelResponse:
        model = kwargs["model"]
        assert isinstance(model, str)
        calls.append(model)
        raise litellm.BadRequestError(
            "invalid provider input",
            llm_provider=model.split("/", maxsplit=1)[0],
            model=model,
        )

    monkeypatch.setattr(litellm, "acompletion", invalid_provider_input)
    try:
        client = LiteLlmClient(router=router, timeout=17.25)
        with pytest.raises(litellm.BadRequestError):
            await client.completion(messages=[{"role": "user", "content": "hi"}])
    finally:
        get_litellm_router.cache_clear()

    assert calls == [
        "cerebras/test-primary",
        "cerebras/test-secondary",
        "groq/test-groq",
        "openai/test-openai",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("messages", [None, "not-a-list", [{"role": "user"}, object()]])
async def test_invalid_caller_messages_do_not_reach_real_router_transport(
    monkeypatch: pytest.MonkeyPatch,
    messages: Any,
) -> None:
    """Malformed local message containers fail before LiteLLM can retry or fallback."""
    router = _real_router(monkeypatch)
    transport = ProviderTransport(set())
    monkeypatch.setattr(litellm, "acompletion", transport)
    try:
        client = LiteLlmClient(router=router, timeout=17.25)
        with pytest.raises(TypeError, match="messages must be a list of message dictionaries"):
            await client.completion(messages=messages)
    finally:
        get_litellm_router.cache_clear()

    assert transport.calls == []


@pytest.mark.asyncio
async def test_real_router_keeps_litellm_empty_message_list_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LiteLLM 1.98.0 documents an empty message list as an accepted default."""
    router = _real_router(monkeypatch)
    transport = ProviderTransport(set())
    monkeypatch.setattr(litellm, "acompletion", transport)
    try:
        client = LiteLlmClient(router=router, timeout=17.25)
        response = await client.completion(messages=[])
    finally:
        get_litellm_router.cache_clear()

    assert response.choices[0].message.content == "fallback success"
    assert transport.calls == [{"model": "cerebras/test-primary", "timeout": 17.25}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_kwargs",
    [{"name": "legacy"}, {"max_retries": 1}, {"stream": True}],
)
async def test_invalid_caller_kwargs_do_not_reach_real_router_transport(
    monkeypatch: pytest.MonkeyPatch,
    invalid_kwargs: dict[str, Any],
) -> None:
    """Unsupported boundary kwargs are local errors, never fallback candidates."""
    router = _real_router(monkeypatch)
    transport = ProviderTransport(set())
    monkeypatch.setattr(litellm, "acompletion", transport)
    try:
        client = LiteLlmClient(router=router, timeout=17.25)
        with pytest.raises(TypeError):
            await client.completion(
                messages=[{"role": "user", "content": "hi"}],
                **invalid_kwargs,
            )
    finally:
        get_litellm_router.cache_clear()

    assert transport.calls == []


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


def test_normalize_connection_error_maps_only_connection_failures() -> None:
    connection_exc = APIConnectionError("refused", llm_provider="test", model="test")
    normalized = normalize_connection_error(connection_exc)
    assert isinstance(normalized, LLMConnectionError)
    assert normalized.raw_error is connection_exc
    assert normalize_connection_error(RuntimeError("other")) is None


@pytest.mark.asyncio
async def test_completion_normalizes_router_connection_error_at_boundary() -> None:
    """#3483: the boundary raises the project-owned LLMConnectionError for connection failures.

    ``Router.acompletion`` speaking ``litellm.exceptions.APIConnectionError`` must
    not leak past ``LiteLlmClient.completion`` — generation verbs classify
    connection failures only through the project-owned exception.
    """
    raw = APIConnectionError("refused", llm_provider="test", model="test")
    client = create_llm_client(model="gpt-4o-mini", router=FailingRouter(raw), timeout=12)

    with pytest.raises(LLMConnectionError) as excinfo:
        await client.completion(messages=[{"role": "user", "content": "hi"}])

    assert excinfo.value.raw_error is raw


@pytest.mark.asyncio
async def test_completion_propagates_non_connection_provider_error_unchanged() -> None:
    """#3483: non-connection provider failures keep their raw, distinguishable type."""
    raw = RateLimitError("quota exhausted", llm_provider="test", model="test")
    client = create_llm_client(model="gpt-4o-mini", router=FailingRouter(raw), timeout=12)

    with pytest.raises(RateLimitError) as excinfo:
        await client.completion(messages=[{"role": "user", "content": "hi"}])

    assert excinfo.value is raw


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


@pytest.mark.asyncio
async def test_completion_rejects_streaming_without_calling_router() -> None:
    """#3481 removed the only streaming consumer, so this boundary stays one-shot."""
    router = DummyRouter()
    client = create_llm_client(model="gpt-4o-mini", router=router, timeout=12)

    with pytest.raises(TypeError, match="does not support streaming"):
        await client.completion(
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )

    router.acompletion.assert_not_awaited()
