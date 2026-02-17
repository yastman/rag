"""Tests for transcribe_node — voice-to-text via Whisper API."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
    async def test_transcribe_empty_text_raises(self):
        """transcribe_node raises ValueError on empty transcription."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()

        with pytest.raises(ValueError, match="Empty transcription"):
            await node(state)
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
    async def test_transcribe_api_error(self):
        """transcribe_node propagates API errors."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.side_effect = Exception("API timeout")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(llm=mock_llm, voice_language="ru", stt_model="whisper")
        state = _make_voice_state()

        with pytest.raises(Exception, match="API timeout"):
            await node(state)
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
    async def test_transcribe_writes_curated_span(self):
        """transcribe_node writes curated Langfuse span input/output."""
        mock_llm = AsyncMock()
        mock_llm.audio.transcriptions.create.return_value = MagicMock(text="Привет мир")

        from telegram_bot.graph.nodes.transcribe import make_transcribe_node

        node = make_transcribe_node(
            llm=mock_llm,
            voice_language="ru",
            stt_model="whisper",
            show_transcription=False,
        )
        state = _make_voice_state()

        with patch("telegram_bot.graph.nodes.transcribe.get_client") as mock_gc:
            mock_lf = MagicMock()
            mock_gc.return_value = mock_lf
            await node(state)

        # Verify curated span was written (input + output)
        assert mock_lf.update_current_span.call_count == 2

        input_call = mock_lf.update_current_span.call_args_list[0]
        input_data = input_call.kwargs["input"]
        assert "voice_language" in input_data
        assert "stt_model" in input_data
        assert "audio_size_bytes" in input_data
        # voice_audio bytes must NOT be in span
        assert "voice_audio" not in str(input_data)

        output_call = mock_lf.update_current_span.call_args_list[1]
        output_data = output_call.kwargs["output"]
        assert "stt_duration_ms" in output_data
        assert "text_length" in output_data
