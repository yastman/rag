"""Langfuse observability coverage for Mini App FastAPI endpoints (#1658).

These tests mirror the canonical pattern from
``tests/unit/api/test_rag_api_runtime.py`` (PII-safe ``update_current_span`` +
``propagate_attributes`` with ``session_id``/``user_id``/``tags``) and assert
that ``mini_app/api.py`` and ``mini_app/phone.py`` instrument every public
mutation endpoint with Langfuse spans.

Forbidden by the issue's contract:
- raw request payloads in span input/output (only curated dicts);
- prometheus metrics (none added here);
- ``langfuse_trace_id`` plumbing on the Mini App API surface (see #1253).
"""

from __future__ import annotations

import pytest


pytest.importorskip("fastapi")

from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from mini_app.api import app, start_expert
from mini_app.phone import PhoneRequest, submit_phone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_langfuse_observed(func) -> bool:
    """Return True when ``func`` carries a Langfuse @observe decorator marker.

    Langfuse v4 exposes ``__langfuse_observed__`` and/or ``__wrapped__`` on the
    decorated callable; we accept either signal as evidence of instrumentation.
    """
    return (
        getattr(func, "__langfuse_observed__", False)
        or hasattr(func, "__wrapped__")
        or getattr(func, "__qualname__", "").startswith("observe")
    )


# ---------------------------------------------------------------------------
# /api/start-expert
# ---------------------------------------------------------------------------


def test_start_expert_endpoint_is_observed():
    """``start_expert`` must be wrapped by Langfuse @observe (#1658)."""
    assert _is_langfuse_observed(start_expert), (
        "mini_app.api.start_expert must carry @observe; got bare callable"
    )


@pytest.mark.asyncio
async def test_start_expert_propagates_session_attributes():
    """``/api/start-expert`` must call propagate_attributes(session_id, user_id, tags)."""
    fake_redis = AsyncMock()
    fake_redis.set = AsyncMock(return_value=True)
    fake_redis.publish = AsyncMock(return_value=1)

    lf = MagicMock()
    lf.update_current_span = MagicMock()

    with (
        patch("mini_app.api._get_redis", AsyncMock(return_value=fake_redis)),
        patch.dict("os.environ", {"BOT_USERNAME": "testbot"}),
        patch("mini_app.api.propagate_attributes", return_value=nullcontext()) as mock_propagate,
        patch("mini_app.api.get_client", return_value=lf),
        patch(
            "mini_app.api.load_mini_app_config",
            return_value={"experts": [{"id": "consultant", "name": "Консультант"}]},
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/start-expert",
                json={
                    "user_id": 123,
                    "expert_id": "consultant",
                    "message": "Подбери квартиру в Софии",
                    "query_id": "qid-1",
                },
            )

    assert resp.status_code == 200, resp.text
    mock_propagate.assert_called_once()
    kwargs = mock_propagate.call_args.kwargs
    assert kwargs["session_id"] == "miniapp-123"
    assert kwargs["user_id"] == "123"
    tags = kwargs["tags"]
    assert "miniapp" in tags
    assert "start-expert" in tags
    assert "consultant" in tags


@pytest.mark.asyncio
async def test_start_expert_updates_current_span_with_safe_payload():
    """``/api/start-expert`` must report a curated, PII-free span payload."""
    fake_redis = AsyncMock()
    fake_redis.set = AsyncMock(return_value=True)
    fake_redis.publish = AsyncMock(return_value=1)

    lf = MagicMock()
    lf.update_current_span = MagicMock()

    raw_message = "Подбери квартиру в Софии"

    with (
        patch("mini_app.api._get_redis", AsyncMock(return_value=fake_redis)),
        patch.dict("os.environ", {"BOT_USERNAME": "testbot"}),
        patch("mini_app.api.propagate_attributes", return_value=nullcontext()),
        patch("mini_app.api.get_client", return_value=lf),
        patch(
            "mini_app.api.load_mini_app_config",
            return_value={"experts": [{"id": "consultant", "name": "Консультант"}]},
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/start-expert",
                json={
                    "user_id": 123,
                    "expert_id": "consultant",
                    "message": raw_message,
                    "query_id": "qid-1",
                },
            )

    lf.update_current_span.assert_called_once()
    kwargs = lf.update_current_span.call_args.kwargs
    input_payload = kwargs["input"]
    assert isinstance(input_payload, dict)
    assert input_payload["content_type"] == "miniapp"
    assert input_payload["expert_id"] == "consultant"
    # Raw user message MUST NOT appear in span input.
    assert raw_message not in str(input_payload), (
        f"Raw message leaked into span input: {input_payload!r}"
    )
    output_payload = kwargs.get("output", {})
    assert isinstance(output_payload, dict)
    # Raw uuid not asserted — but at minimum a deeplink_emitted-style flag must exist.
    assert output_payload.get("delivery_status") in {"sent", "ok"}


# ---------------------------------------------------------------------------
# /api/phone
# ---------------------------------------------------------------------------


def test_phone_endpoint_is_observed():
    """``mini_app.api.phone`` (and underlying ``submit_phone``) must be observed."""
    # ``phone`` endpoint delegates to submit_phone — instrument the worker.
    assert _is_langfuse_observed(submit_phone), (
        "mini_app.phone.submit_phone must carry @observe; got bare callable"
    )


@pytest.mark.asyncio
async def test_phone_propagates_session_attributes():
    """``/api/phone`` must propagate session_id/user_id/tags for the funnel."""
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

    lf = MagicMock()
    lf.update_current_span = MagicMock()

    with (
        patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
        patch("mini_app.api.propagate_attributes", return_value=nullcontext()) as mock_propagate,
        patch("mini_app.api.get_client", return_value=lf),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/phone",
                json={
                    "phone": "+359888123456",
                    "source": "viewing_consultant",
                    "user_id": 456,
                },
            )

    assert resp.status_code == 200, resp.text
    mock_propagate.assert_called_once()
    kwargs = mock_propagate.call_args.kwargs
    assert kwargs["session_id"] == "miniapp-456"
    assert kwargs["user_id"] == "456"
    tags = kwargs["tags"]
    assert "miniapp" in tags
    assert "submit-phone" in tags
    assert "viewing_consultant" in tags


@pytest.mark.asyncio
async def test_phone_excludes_pii_from_span_payload():
    """Span payload for /api/phone must NOT contain raw phone or name."""
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 2})

    lf = MagicMock()
    lf.update_current_span = MagicMock()

    raw_phone = "+359888123456"
    raw_name = "Ivan Petrov"

    with (
        patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
        patch("mini_app.api.propagate_attributes", return_value=nullcontext()),
        patch("mini_app.api.get_client", return_value=lf),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/phone",
                json={
                    "phone": raw_phone,
                    "source": "viewing_consultant",
                    "user_id": 456,
                    "name": raw_name,
                },
            )

    lf.update_current_span.assert_called_once()
    kwargs = lf.update_current_span.call_args.kwargs
    payload_repr = repr(kwargs.get("input", {})) + repr(kwargs.get("output", {}))
    assert raw_phone not in payload_repr, f"Raw phone leaked into span: {payload_repr}"
    assert raw_name not in payload_repr, f"Raw name leaked into span: {payload_repr}"
    input_payload = kwargs["input"]
    assert input_payload["content_type"] == "miniapp"
    assert input_payload["source"] == "viewing_consultant"
    assert input_payload["phone_present"] is True
    assert input_payload["name_present"] is True


# ---------------------------------------------------------------------------
# submit_phone error path (Kommo failure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_phone_marks_span_error_on_kommo_failure():
    """Kommo failure inside submit_phone must mark the active span ERROR
    BEFORE returning the graceful response."""
    lf = MagicMock()
    lf.update_current_span = MagicMock()

    with (
        patch("mini_app.phone.get_kommo_client", side_effect=RuntimeError("Kommo down")),
        patch("mini_app.phone.get_client", return_value=lf),
    ):
        result = await submit_phone(
            PhoneRequest(phone="+359888123456", source="viewing_consultant", user_id=456)
        )

    # graceful contract preserved
    assert result == {"success": True, "lead_id": None}
    # but the error must surface in the span
    lf.update_current_span.assert_called()
    found_error = False
    for call in lf.update_current_span.call_args_list:
        if call.kwargs.get("level") == "ERROR":
            found_error = True
            assert (
                "Kommo" in (call.kwargs.get("status_message") or "")
                or "down" in (call.kwargs.get("status_message") or "").lower()
            )
    assert found_error, (
        f"No ERROR-level span update after Kommo failure; "
        f"calls={lf.update_current_span.call_args_list}"
    )


@pytest.mark.asyncio
async def test_submit_phone_works_when_langfuse_client_is_none():
    """Graceful degradation: get_client() == None must NOT break submit_phone."""
    mock_kommo = MagicMock()
    mock_kommo.upsert_contact = AsyncMock(return_value={"id": 1})
    mock_kommo.create_lead = AsyncMock(return_value={"id": 7})

    with (
        patch("mini_app.phone.get_kommo_client", return_value=mock_kommo),
        patch("mini_app.phone.get_client", return_value=None),
    ):
        result = await submit_phone(PhoneRequest(phone="+359888123456", source="test", user_id=1))
    assert result == {"success": True, "lead_id": 7}
