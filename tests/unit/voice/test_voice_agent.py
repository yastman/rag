"""Unit tests for voice agent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("livekit")


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


@pytest.mark.asyncio
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

    client_cm = AsyncMock()
    client_cm.__aenter__.return_value = mock_client
    client_cm.__aexit__.return_value = None

    with patch("src.voice.agent.httpx.AsyncClient", return_value=client_cm):
        result = await VoiceBot.search_knowledge_base.__wrapped__(agent, None, "что есть в Несебре")

    assert result == "Найдено 3 варианта."
    assert store.append_transcript.await_count == 2
    first = store.append_transcript.await_args_list[0].kwargs
    second = store.append_transcript.await_args_list[1].kwargs
    assert first["call_id"] == "22222222-2222-2222-2222-222222222222"
    assert first["role"] == "user"
    assert second["role"] == "bot"
