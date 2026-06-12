"""Tests for Telegram assistant-core adapter helpers."""

from __future__ import annotations

from typing import Any


class _FakeCache:
    async def check_semantic(self, *args: object, **kwargs: object) -> dict[str, Any] | None:
        return None


class _FakeEmbeddings:
    async def aembed_query(self, text: str) -> list[float]:
        return [0.0]


class _FakeSparseEmbeddings:
    async def aembed_query(self, text: str) -> dict[str, Any]:
        return {}


class _FakeQdrant:
    async def hybrid_search_rrf(self, *args: object, **kwargs: object) -> list[dict[str, Any]]:
        return []


def test_build_user_context_is_transport_neutral() -> None:
    from telegram_bot.assistant_core_adapter import build_user_context

    ctx = build_user_context(
        user_id=42,
        session_id="s-1",
        role="manager",
        filters={"city": "Sofia"},
    )

    assert ctx.user_id == "42"
    assert ctx.session_id == "s-1"
    assert ctx.role == "manager"
    assert ctx.filters == {"city": "Sofia"}
    assert ctx.language == "ru"


def test_core_entrypoint_flag_defaults_off(monkeypatch) -> None:
    from telegram_bot.assistant_core_adapter import (
        CORE_ENTRYPOINT_ENV,
        core_entrypoint_enabled,
    )

    monkeypatch.delenv(CORE_ENTRYPOINT_ENV, raising=False)

    assert not core_entrypoint_enabled()


def test_response_text_for_telegram_returns_core_text() -> None:
    from src.core import AssistantResult
    from telegram_bot.assistant_core_adapter import response_text_for_telegram

    assert response_text_for_telegram(AssistantResult(response_text="hello")) == "hello"


async def test_run_core_text_request_uses_assistant_app(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    import telegram_bot.assistant_core_adapter as adapter
    from src.core import AssistantResult, CoreDependencies, UserContext

    dependencies = CoreDependencies(
        cache=_FakeCache(),
        embeddings=_FakeEmbeddings(),
        sparse_embeddings=_FakeSparseEmbeddings(),
        qdrant=_FakeQdrant(),
    )
    user_context = UserContext(user_id="u-1", session_id="s-1")
    run_text = AsyncMock(return_value=AssistantResult(response_text="ok"))

    class FakeAssistantApp:
        async def run_text(self, *args, **kwargs):
            return await run_text(*args, **kwargs)

    seen = {}

    def from_dependencies(deps):
        seen["dependencies"] = deps
        return FakeAssistantApp()

    monkeypatch.setattr(
        adapter.AssistantApp,
        "from_dependencies",
        staticmethod(from_dependencies),
    )

    result = await adapter.run_core_text_request(
        query="hello",
        collection="collection-a",
        user_context=user_context,
        dependencies=dependencies,
        request_id="req-1",
    )

    assert result.response_text == "ok"
    assert seen["dependencies"] is dependencies
    run_text.assert_awaited_once_with(
        "hello",
        collection="collection-a",
        user_context=user_context,
        request_id="req-1",
    )
