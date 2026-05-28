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


def test_setup_langfuse_calls_auth_check_when_client_is_initialized(monkeypatch):
    """When a Langfuse client is returned, _setup_langfuse must call
    ``client.auth_check()`` and warn-log on failure (#2210).

    Without auth_check, an unreachable Langfuse host or rotated keys would
    silently degrade to no-op tracing and the operator would have no signal
    in the voice-agent logs. ``mini_app/api.py:73-105`` is the canonical
    lifespan reference.
    """
    import src.voice.agent as mod

    fake_provider = object()
    fake_client = MagicMock()
    fake_client.auth_check.return_value = True

    with (
        patch("src.voice.agent.initialize_langfuse", return_value=fake_client),
        patch("src.voice.agent.trace.get_tracer_provider", return_value=fake_provider),
        patch("livekit.agents.telemetry.set_tracer_provider"),
    ):
        mod._setup_langfuse()

    fake_client.auth_check.assert_called_once_with()


def test_setup_langfuse_logs_warning_when_auth_check_fails(monkeypatch, caplog):
    """auth_check() failure must produce a WARNING log (not crash). #2210."""
    import logging

    import src.voice.agent as mod

    fake_provider = object()
    fake_client = MagicMock()
    fake_client.auth_check.side_effect = RuntimeError("Langfuse unreachable")

    with (
        patch("src.voice.agent.initialize_langfuse", return_value=fake_client),
        patch("src.voice.agent.trace.get_tracer_provider", return_value=fake_provider),
        patch("livekit.agents.telemetry.set_tracer_provider"),
        caplog.at_level(logging.WARNING, logger="src.voice.agent"),
    ):
        mod._setup_langfuse()  # must not raise

    fake_client.auth_check.assert_called_once_with()
    # Warning log must surface so operators see "Langfuse degraded"
    assert any(
        "auth_check" in record.message.lower() or "langfuse" in record.message.lower()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    ), (
        "Voice agent must log a WARNING when Langfuse auth_check fails so the "
        "operator gets a signal instead of silent no-op tracing (#2210)."
    )


def test_setup_langfuse_delegates_to_canonical_initialize(monkeypatch):
    """Voice OTEL setup reuses src.observability.initialize_langfuse instead of
    building a parallel OTLP/TracerProvider/BatchSpanProcessor pipeline (#2059).

    The canonical bootstrap already configures Langfuse with PII masking and
    registers the global TracerProvider. The voice agent only needs to wire the
    resulting provider into LiveKit's telemetry helper.
    """
    import src.voice.agent as mod

    fake_provider = object()
    fake_client = object()

    with (
        patch("src.voice.agent.initialize_langfuse", return_value=fake_client) as init_mock,
        patch("src.voice.agent.trace.get_tracer_provider", return_value=fake_provider),
        patch("livekit.agents.telemetry.set_tracer_provider") as set_provider,
    ):
        mod._setup_langfuse()

    init_mock.assert_called_once_with()
    set_provider.assert_called_once_with(fake_provider)


def test_setup_langfuse_skips_livekit_wiring_when_disabled(monkeypatch):
    """When initialize_langfuse() returns None (missing creds, unreachable host,
    SDK unavailable), the voice agent must NOT register a tracer provider with
    LiveKit. This avoids wiring an unconfigured provider into the agent runtime.
    """
    import src.voice.agent as mod

    with (
        patch("src.voice.agent.initialize_langfuse", return_value=None) as init_mock,
        patch("livekit.agents.telemetry.set_tracer_provider") as set_provider,
    ):
        mod._setup_langfuse()

    init_mock.assert_called_once_with()
    set_provider.assert_not_called()


def test_setup_langfuse_swallows_livekit_telemetry_import_error(monkeypatch):
    """If livekit.agents.telemetry is unavailable (older LiveKit version), the
    setup must still succeed silently. Langfuse spans continue to flow via the
    global TracerProvider that initialize_langfuse() registered.
    """
    import sys

    import src.voice.agent as mod

    fake_client = object()
    fake_provider = object()

    saved = sys.modules.pop("livekit.agents.telemetry", None)
    try:
        with (
            patch("src.voice.agent.initialize_langfuse", return_value=fake_client),
            patch("src.voice.agent.trace.get_tracer_provider", return_value=fake_provider),
            patch.dict(sys.modules, {"livekit.agents.telemetry": None}),
        ):
            # Should not raise even though the import fails.
            mod._setup_langfuse()
    finally:
        if saved is not None:
            sys.modules["livekit.agents.telemetry"] = saved


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
