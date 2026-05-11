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
    assert len(payload["answer_preview"]) <= 240 + len("... [TRUNCATED]")


def test_build_safe_output_payload_omits_none_optional_fields() -> None:
    payload = build_safe_output_payload(
        answer_text="hello",
        chunks_count=1,
    )

    assert "sources_count" not in payload
    assert "fallback_reason" not in payload
    assert "answer_text" not in payload
    assert "response" not in payload


# ---------------------------------------------------------------------------
# Regression tests for extra safety (blocker 1)
# ---------------------------------------------------------------------------


def test_build_safe_input_payload_extra_cannot_override_safe_keys() -> None:
    """Extra must not override existing safe payload keys."""
    payload = build_safe_input_payload(
        content_type="text",
        text="hello",
        action="original_action",
        scenario="original_scenario",
        route="original_route",
        extra={
            "content_type": "malicious",
            "query_preview": "raw",
            "query_hash": "bad",
            "query_len": 999,
            "action": "bad_action",
            "scenario": "bad_scenario",
            "route": "bad_route",
        },
    )
    # Core safe keys must not be overridden.
    assert payload["content_type"] == "text"
    assert payload["query_len"] == len("hello")
    assert "raw" not in payload["query_preview"]
    assert payload["query_hash"] != "bad"
    # Optional schema keys must not be overridden.
    assert payload["action"] == "original_action"
    assert payload["scenario"] == "original_scenario"
    assert payload["route"] == "original_route"


def test_build_safe_input_payload_extra_blocks_unsafe_key_names() -> None:
    """Extra must not introduce raw key names that defeat the safety contract."""
    unsafe_extras = {
        "text": "raw text",
        "query": "raw query",
        "raw_query": "raw",
        "answer_text": "ans",
        "response": "resp",
    }
    payload = build_safe_input_payload(
        content_type="text",
        text="hello",
        extra=unsafe_extras,
    )
    for key in unsafe_extras:
        assert key not in payload, f"unsafe key {key!r} should not appear in payload"


def test_build_safe_input_payload_extra_values_are_redacted() -> None:
    """Extra string values should be PII-redacted before inclusion."""
    payload = build_safe_input_payload(
        content_type="text",
        text="hello",
        extra={"comment": "Call +79161234567 for details"},
    )
    assert "+79161234567" not in payload["comment"]
    assert "[PHONE]" in payload["comment"]


def test_build_safe_input_payload_extra_long_strings_are_bounded() -> None:
    """Extra string values should be bounded to preview limit."""
    payload = build_safe_input_payload(
        content_type="text",
        text="hello",
        extra={"data": "x" * 300},
    )
    assert len(payload["data"]) <= 240 + len("... [TRUNCATED]")


# ---------------------------------------------------------------------------
# Regression test for preview redact-before-truncate (blocker 2)
# ---------------------------------------------------------------------------


def test_preview_redacts_before_truncation_no_pii_leak_at_boundary() -> None:
    """PII must be redacted before preview truncation.

    When PII straddles the 240-char preview boundary, redacting first ensures
    the full pattern is matched and replaced.  Truncating first would split
    the pattern and leak a partial PII fragment.
    """
    # Place a phone number so it starts before the 240-char boundary but ends
    # after it.  Total length > 240 so truncation applies.  The phone is placed
    # early enough that the replacement token "[PHONE]" is fully inside the
    # 240-char window.
    prefix = "x" * 225
    phone = "+79161234567"  # 12 chars, spans positions 225-236
    suffix = "y" * 50
    text = prefix + phone + suffix  # 287 chars

    payload = build_safe_input_payload(
        content_type="text",
        text=text,
    )

    preview = payload["query_preview"]
    # No raw phone digits may appear — the full phone was redacted first.
    assert "+79161234567" not in preview
    assert "79161234567" not in preview
    # The replacement token should be present (may be partially visible).
    assert "[PHONE]" in preview
    # Preview is still bounded.
    assert len(preview) <= 240 + len("... [TRUNCATED]")
