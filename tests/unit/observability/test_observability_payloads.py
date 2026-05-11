"""Tests for observability_payloads — safe Langfuse input/output payload builders."""

from __future__ import annotations

from telegram_bot.observability_payloads import (
    build_safe_input_payload,
    build_safe_output_payload,
)


def test_build_safe_input_payload_masks_and_hashes_text() -> None:
    payload = build_safe_input_payload(
        content_type="text",
        text="Call me at +79161234567 about квартиры до 100к",
        action="message",
        scenario="telethon_text_rag",
    )

    assert payload["content_type"] == "text"
    assert payload["action"] == "message"
    assert payload["scenario"] == "telethon_text_rag"
    assert payload["query_len"] == len("Call me at +79161234567 about квартиры до 100к")
    assert "79161234567" not in payload["query_preview"]
    assert payload["query_hash"]
    assert "text" not in payload


def test_build_safe_input_payload_extra_non_none_merged() -> None:
    payload = build_safe_input_payload(
        content_type="text",
        text="hello",
        extra={"foo": "bar", "baz": None, "num": 42},
    )

    assert payload["foo"] == "bar"
    assert payload["num"] == 42
    assert "baz" not in payload


def test_build_safe_input_payload_omits_none_optional_fields() -> None:
    payload = build_safe_input_payload(
        content_type="text",
        text="hello",
    )

    assert "action" not in payload
    assert "scenario" not in payload
    assert "route" not in payload


def test_build_safe_output_payload_is_bounded_and_hashed() -> None:
    payload = build_safe_output_payload(
        answer_text="Ответ " * 300,
        chunks_count=2,
        delivery_status="sent",
        sources_count=3,
    )

    assert payload["delivery_status"] == "sent"
    assert payload["chunks_count"] == 2
    assert payload["sources_count"] == 3
    assert payload["answer_hash"]
    assert payload["answer_len"] == len("Ответ " * 300)
    assert len(payload["answer_preview"]) <= 240


def test_build_safe_output_payload_omits_none_optional_fields() -> None:
    payload = build_safe_output_payload(
        answer_text="hello",
        chunks_count=1,
    )

    assert "sources_count" not in payload
    assert "fallback_reason" not in payload
    assert "answer_text" not in payload
    assert "response" not in payload
