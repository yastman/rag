"""Tests for transcribe_node — voice-to-text via Whisper API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.state import make_initial_state


def _make_voice_state(audio: bytes = b"fake-ogg-data", duration: float = 5.0) -> dict:
    """Create a state dict with voice_audio populated."""
    state = make_initial_state(user_id=123, session_id="test-abc-20260211", query="")
    state["voice_audio"] = audio
    state["voice_duration_s"] = duration
    state["input_type"] = "voice"
    return state


class TestTranscribeNode:
    @pytest.mark.asyncio
    async def test_transcribe_returns_text(self):
        """transcribe_node calls Whisper API and returns transcribed text."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="Привет мир")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()
        result = await node(state)

        assert result["stt_text"] == "Привет мир"
        assert result["query"] == "Привет мир"
        assert result["stt_duration_ms"] > 0
        mock_llm.audio.transcriptions.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_transcribe_sets_messages(self):
        """transcribe_node sets messages with transcribed text."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест запрос")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()
        result = await node(state)

        assert len(result["messages"]) == 1
        assert result["messages"][0]["content"] == "тест запрос"

    @pytest.mark.asyncio
    async def test_transcribe_empty_text_raises(self):
        """transcribe_node raises ValueError on empty transcription."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()

        with pytest.raises(ValueError, match="Empty transcription"):
            await node(state)

    @pytest.mark.asyncio
    async def test_transcribe_passes_language(self):
        """transcribe_node passes language parameter to Whisper API."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="uk", stt_model="whisper")
        state = _make_voice_state()
        await node(state)

        call_kwargs = mock_llm.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["language"] == "uk"
        assert call_kwargs["model"] == "whisper"

    @pytest.mark.asyncio
    async def test_transcribe_api_error(self):
        """transcribe_node propagates API errors."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.side_effect = Exception("API timeout")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()

        with pytest.raises(Exception, match="API timeout"):
            await node(state)

    @pytest.mark.asyncio
    async def test_transcribe_show_transcription(self):
        """transcribe_node sends transcription preview when show_transcription=True."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест")
        mock_message = AsyncMock()

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(
            llm=mock_llm,
            voice_language="ru",
            stt_model="whisper",
            show_transcription=True,
            message=mock_message,
        )
        state = _make_voice_state()
        await node(state)

        mock_message.answer.assert_awaited_once()
        call_args = mock_message.answer.call_args
        assert "тест" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_transcribe_no_preview_when_disabled(self):
        """transcribe_node does not send preview when show_transcription=False."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="тест")
        mock_message = AsyncMock()

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(
            llm=mock_llm,
            voice_language="ru",
            stt_model="whisper",
            show_transcription=False,
            message=mock_message,
        )
        state = _make_voice_state()
        await node(state)

        mock_message.answer.assert_not_awaited()
