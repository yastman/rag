"""Unit tests for voice agent."""

from __future__ import annotations


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
