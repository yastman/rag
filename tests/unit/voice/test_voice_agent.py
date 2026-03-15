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


def test_voice_bot_stores_trace_session_id():
    """Voice agent keeps `voice-<call_id>` session id for lifecycle traces."""
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="call-xyz")
    assert agent._session_id == "voice-call-xyz"


async def test_voice_tool_propagates_langfuse_trace_id_to_api_payload():
    """Voice tool should pass langfuse_trace_id to RAG API payload (#609)."""
    from src.voice.agent import VoiceBot

    store = MagicMock()
    store.append_transcript = AsyncMock()

    agent = VoiceBot(
        call_id="22222222-2222-2222-2222-222222222222",
        transcript_store=store,
        langfuse_trace_id="trace-123",
    )

    mock_rag_client = MagicMock()
    mock_rag_client.search_knowledge_base = AsyncMock(return_value="OK")

    with patch("src.voice.agent._get_rag_api_client", return_value=mock_rag_client):
        await VoiceBot.search_knowledge_base.__wrapped__(agent, None, "test query")

    request = mock_rag_client.search_knowledge_base.await_args.args[0]
    payload = request.to_payload()
    assert payload["langfuse_trace_id"] == "trace-123"
    assert payload["channel"] == "voice"


async def test_search_tool_omits_langfuse_trace_id_when_none():
    """langfuse_trace_id is NOT in payload when not provided (#241)."""
    from src.voice.agent import VoiceBot

    agent = VoiceBot(call_id="22222222-2222-2222-2222-222222222222")

    mock_rag_client = MagicMock()
    mock_rag_client.search_knowledge_base = AsyncMock(return_value="OK")

    with patch("src.voice.agent._get_rag_api_client", return_value=mock_rag_client):
        await VoiceBot.search_knowledge_base.__wrapped__(agent, None, "test query")

    request = mock_rag_client.search_knowledge_base.await_args.args[0]
    payload = request.to_payload()
    assert "langfuse_trace_id" not in payload


async def test_search_tool_appends_transcript_entries_with_store():
    from src.voice.agent import VoiceBot

    store = MagicMock()
    store.append_transcript = AsyncMock()

    agent = VoiceBot(call_id="22222222-2222-2222-2222-222222222222", transcript_store=store)

    mock_rag_client = MagicMock()
    mock_rag_client.search_knowledge_base = AsyncMock(return_value="Найдено 3 варианта.")

    with patch("src.voice.agent._get_rag_api_client", return_value=mock_rag_client):
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

    original = mod._rag_api_client
    try:
        mod._rag_api_client = None
        first = mod._get_http_client()
        second = mod._get_http_client()
        assert first is second
        assert isinstance(first, httpx.AsyncClient)
    finally:
        mod._rag_api_client = original


def test_get_http_client_has_pool_limits():
    """Shared httpx client uses connection pool limits (#369)."""
    import src.voice.agent as mod

    original = mod._rag_api_client
    try:
        mod._rag_api_client = None
        client = mod._get_http_client()
        pool = client._transport._pool
        assert pool._max_connections == 10
        assert pool._max_keepalive_connections == 5
    finally:
        mod._rag_api_client = original


async def test_close_http_client():
    """_close_http_client closes the client and resets the global (#369)."""
    import src.voice.agent as mod

    original = mod._rag_api_client
    try:
        mod._rag_api_client = None
        mod._get_http_client()
        assert mod._rag_api_client is not None
        await mod._close_http_client()
        assert mod._rag_api_client is None
    finally:
        mod._rag_api_client = original


async def test_mark_job_finished_closes_http_client_when_last_job():
    """Last finished job should close shared HTTP client."""
    import src.voice.agent as mod

    original_client = mod._rag_api_client
    original_jobs = mod._active_jobs
    original_lock = mod._jobs_lock
    try:
        mod._rag_api_client = None
        mod._active_jobs = 0
        mod._jobs_lock = None
        mod._get_http_client()
        await mod._mark_job_started()
        assert mod._active_jobs == 1

        await mod._mark_job_finished()

        assert mod._active_jobs == 0
        assert mod._rag_api_client is None
    finally:
        if mod._rag_api_client is not None:
            await mod._close_http_client()
        mod._rag_api_client = original_client
        mod._active_jobs = original_jobs
        mod._jobs_lock = original_lock


async def test_mark_job_finished_keeps_client_while_other_jobs_active():
    """Shared HTTP client stays open until the last active job finishes."""
    import src.voice.agent as mod

    original_client = mod._rag_api_client
    original_jobs = mod._active_jobs
    original_lock = mod._jobs_lock
    try:
        mod._rag_api_client = None
        mod._active_jobs = 0
        mod._jobs_lock = None
        mod._get_http_client()
        await mod._mark_job_started()
        await mod._mark_job_started()
        assert mod._active_jobs == 2

        await mod._mark_job_finished()

        assert mod._active_jobs == 1
        assert mod._rag_api_client is not None

        await mod._mark_job_finished()
        assert mod._active_jobs == 0
        assert mod._rag_api_client is None
    finally:
        if mod._rag_api_client is not None:
            await mod._close_http_client()
        mod._rag_api_client = original_client
        mod._active_jobs = original_jobs
        mod._jobs_lock = original_lock
