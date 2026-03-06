"""Tests for Mini App chat SSE endpoint."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from mini_app.api import app
from mini_app.chat import ChatRequest, chat_sse_generator


@pytest.mark.asyncio
async def test_chat_returns_sse_stream():
    mock_result = {"response": "Студии от 38 900 EUR", "response_sent": False}

    with patch("mini_app.chat.run_mini_app_query", AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/chat",
                json={"message": "Какие цены на студии?", "user_id": 123},
            )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_chat_requires_message():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/chat", json={"user_id": 123})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_sse_error_handling():
    request = ChatRequest(message="test", user_id=123)
    with patch("mini_app.chat.run_mini_app_query", AsyncMock(side_effect=Exception("oops"))):
        events = []
        async for event in chat_sse_generator(request):
            events.append(event)
    error_events = [e for e in events if "error" in e]
    assert len(error_events) == 1
    data = json.loads(error_events[0].removeprefix("data: ").strip())
    assert data["type"] == "error"
    assert "text" in data


@pytest.mark.asyncio
async def test_chat_sse_chunks_response():
    long_response = "A" * 60  # 60 chars -> 3 chunks of 20
    mock_result = {"response": long_response}
    with patch("mini_app.chat.run_mini_app_query", AsyncMock(return_value=mock_result)):
        events = []
        async for event in chat_sse_generator(ChatRequest(message="test", user_id=123)):
            events.append(event)
    chunk_events = []
    for event in events:
        if event.startswith("data: "):
            data = json.loads(event[6:].strip())
            if data.get("type") == "chunk":
                chunk_events.append(data)
    assert len(chunk_events) == 3
    for chunk in chunk_events:
        assert len(chunk["text"]) == 20


@pytest.mark.asyncio
async def test_chat_with_expert_id():
    mock_result = {"response": "OK"}
    mock_query = AsyncMock(return_value=mock_result)
    with patch("mini_app.chat.run_mini_app_query", mock_query):
        async for _ in chat_sse_generator(
            ChatRequest(message="test", user_id=123, expert_id="consultant")
        ):
            pass
    mock_query.assert_called_once_with(message="test", user_id=123, expert_id="consultant")
