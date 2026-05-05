"""Unit tests for FakeMessage and FakeChat in validate_traces."""

from __future__ import annotations

import pytest

from scripts.validate_traces import FakeChat, FakeMessage


def test_fake_chat_has_stable_id() -> None:
    chat = FakeChat(chat_id=42)
    assert chat.id == 42


def test_fake_message_has_chat_attribute() -> None:
    msg = FakeMessage()
    assert hasattr(msg, "chat")
    assert msg.chat.id == 0


def test_fake_message_chat_id_customizable() -> None:
    msg = FakeMessage()
    msg.chat = FakeChat(chat_id=99)
    assert msg.chat.id == 99


@pytest.mark.asyncio
async def test_fake_message_answer_returns_sent_message() -> None:
    msg = FakeMessage()
    sent = await msg.answer("hello")
    assert sent is not None
    assert msg.t_answer_called is not None
    assert msg.sent is sent
