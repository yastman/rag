"""Unit tests for voice agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


pytest.importorskip("livekit")
pytestmark = pytest.mark.requires_extras


def test_voice_bot_init():
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="test-123", lead_data={"name": "Test"})
    assert agent._call_id == "test-123"
    assert "Test" in agent.instructions


def test_voice_bot_instructions_without_lead_data():
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="test-456")
    assert "бот-ассистент" in agent.instructions
    assert "Данные заявки" not in agent.instructions


def test_voice_bot_has_function_tool():
    from src.voice.agent import VoiceBot

    agent = VoiceBot()
    assert hasattr(agent, "search_knowledge_base")
    assert callable(agent.search_knowledge_base)


def test_server_has_tuned_worker_settings():
    """AgentServer uses increased timeouts and reduced idle procs (#218)."""
    from src.voice.agent import server

    assert server._initialize_process_timeout == 30.0
    assert server._shutdown_process_timeout == 30.0
    assert server._num_idle_processes == 2


def test_server_has_prewarm_setup_fnc():
    """AgentServer setup_fnc pre-loads VAD to avoid event loop blocking (#218)."""
    from src.voice.agent import _prewarm_process, server

    assert server.setup_fnc is _prewarm_process


def test_prewarm_stores_vad_in_userdata():
    """_prewarm_process stores VAD model in proc.userdata for reuse (#218)."""
    from src.voice.agent import _prewarm_process

    proc = MagicMock()
    proc.userdata = {}
    with patch("src.voice.agent.silero.VAD.load", return_value="fake-vad") as mock_load:
        _prewarm_process(proc)
        mock_load.assert_called_once()
    assert proc.userdata["vad"] == "fake-vad"


def test_voice_bot_stores_langfuse_trace_id():
    """langfuse_trace_id is stored on the agent for trace linking (#241)."""
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="test-789", langfuse_trace_id="trace-abc123")
    assert agent._langfuse_trace_id == "trace-abc123"


def test_voice_bot_langfuse_trace_id_defaults_none():
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="test-789")
    assert agent._langfuse_trace_id is None


async def test_search_tool_forwards_langfuse_trace_id():
    """langfuse_trace_id is included in the RAG API payload (#241)."""
    from src.voice.agent import VoiceBot

    store = MagicMock()
    store.append_transcript = AsyncMock()

    agent = VoiceBot(
        call_id="22222222-2222-2222-2222-222222222222",
        transcript_store=store,
        langfuse_trace_id="trace-link-test",
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": "OK"}

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.voice.agent._get_http_client", return_value=mock_client):
        await VoiceBot.search_knowledge_base.__wrapped__(agent, None, "test query")

    payload = mock_client.post.await_args.kwargs["json"]
    assert payload["langfuse_trace_id"] == "trace-link-test"
    assert payload["channel"] == "voice"


async def test_search_tool_omits_langfuse_trace_id_when_none():
    """langfuse_trace_id is NOT in payload when not provided (#241)."""
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="22222222-2222-2222-2222-222222222222")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": "OK"}

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.voice.agent._get_http_client", return_value=mock_client):
        await VoiceBot.search_knowledge_base.__wrapped__(agent, None, "test query")

    payload = mock_client.post.await_args.kwargs["json"]
    assert "langfuse_trace_id" not in payload


async def test_search_tool_appends_transcript_entries_with_store():
    from src.voice.agent import VoiceBot

    store = MagicMock()
    store.append_transcript = AsyncMock()

    agent = VoiceBot(call_id="22222222-2222-2222-2222-222222222222", transcript_store=store)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"response": "Найдено 3 варианта."}

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.voice.agent._get_http_client", return_value=mock_client):
        result = await VoiceBot.search_knowledge_base.__wrapped__(agent, None, "что есть в Несебре")

    assert result == "Найдено 3 варианта."
    assert store.append_transcript.await_count == 2
    first = store.append_transcript.await_args_list[0].kwargs
    second = store.append_transcript.await_args_list[1].kwargs
    assert first["call_id"] == "22222222-2222-2222-2222-222222222222"
    assert first["role"] == "user"
    assert second["role"] == "bot"


def test_get_http_client_returns_shared_instance():
    """_get_http_client returns the same AsyncClient on repeated calls (#369)."""
    import src.voice.agent as mod

    original = mod._http_client
    try:
        mod._http_client = None
        first = mod._get_http_client()
        second = mod._get_http_client()
        assert first is second
        assert isinstance(first, httpx.AsyncClient)
    finally:
        mod._http_client = original


def test_get_http_client_has_pool_limits():
    """Shared httpx client uses connection pool limits (#369)."""
    import src.voice.agent as mod

    original = mod._http_client
    try:
        mod._http_client = None
        client = mod._get_http_client()
        pool = client._transport._pool
        assert pool._max_connections == 10
        assert pool._max_keepalive_connections == 5
    finally:
        mod._http_client = original


async def test_close_http_client():
    """_close_http_client closes the client and resets the global (#369)."""
    import src.voice.agent as mod

    original = mod._http_client
    try:
        mod._http_client = None
        mod._get_http_client()
        assert mod._http_client is not None
        await mod._close_http_client()
        assert mod._http_client is None
    finally:
        mod._http_client = original


async def test_entrypoint_shutdown_callback_closes_http_client():
    """entrypoint shutdown callback closes shared HTTP client."""
    import src.voice.agent as mod

    ctx = MagicMock()
    ctx.job = MagicMock(metadata="")
    ctx.proc = MagicMock(userdata={"vad": "fake-vad"})
    ctx.room = MagicMock()

    callbacks = []
    ctx.add_shutdown_callback = MagicMock(side_effect=lambda cb: callbacks.append(cb))

    session = MagicMock()
    session.start = AsyncMock()
    session.generate_reply = AsyncMock()

    with (
        patch("src.voice.agent._get_transcript_store", AsyncMock(return_value=None)),
        patch("src.voice.agent.AgentSession", return_value=session),
        patch("src.voice.agent.elevenlabs.STT", return_value=MagicMock()),
        patch("src.voice.agent.elevenlabs.TTS", return_value=MagicMock()),
        patch("src.voice.agent.openai.LLM", return_value=MagicMock()),
        patch("src.voice.agent.VoiceBot", return_value=MagicMock()),
        patch("src.voice.agent._close_http_client", AsyncMock()) as mock_close_http_client,
    ):
        await mod.entrypoint(ctx)
        assert len(callbacks) == 1
        await callbacks[0]()
        mock_close_http_client.assert_awaited_once()
