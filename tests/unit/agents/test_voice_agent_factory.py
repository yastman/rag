"""Tests for the imperative voice-agent facade."""

from __future__ import annotations

from typing import Any

import pytest

from telegram_bot.agents.voice_agent import VoiceAgentState, create_voice_agent


@pytest.mark.asyncio
async def test_factory_returns_ainvoke_facade() -> None:
    async def fake_tool(query: str, config: dict[str, Any]) -> str:
        return f"voice:{query}:{bool(config)}"

    agent = create_voice_agent(
        cache=object(),
        embeddings=object(),
        model="openai/test",
        tools=[fake_tool],
    )

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "что нужно для прописки?"}]},
        config={"configurable": {}},
    )

    assert result["messages"][-1].content == "voice:что нужно для прописки?:True"


@pytest.mark.asyncio
async def test_factory_reads_stt_text_payload() -> None:
    async def fake_tool(query: str, config: dict[str, Any]) -> str:
        _ = config
        return query

    agent = create_voice_agent(
        cache=object(),
        embeddings=object(),
        model="openai/test",
        tools=[fake_tool],
    )

    result = await agent.ainvoke({"stt_text": "текст из аудио"})

    assert result["response"] == "текст из аудио"


def test_state_schema_includes_voice_input_fields() -> None:
    annotations = VoiceAgentState.__annotations__
    for field in ("voice_audio", "voice_duration_s", "stt_text", "trace_id"):
        assert field in annotations
