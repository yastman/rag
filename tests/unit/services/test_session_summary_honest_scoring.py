"""Session-summary honest CRM scoring (#2212, finding #2).

``_write_summary`` must report a truthful CRM outcome so Langfuse scores can
distinguish "summary generated" from "summary actually written to Kommo".
Today the summary is generated and silently dropped (lead_id unresolved, #445)
while the dashboard still shows summary counts — a false-success signal.

Outcomes: ``no_kommo`` | ``skipped_no_lead`` | ``written`` | ``failed``.
A worker cycle emits ``session_summary_kommo_written`` /
``session_summary_kommo_skipped`` accordingly.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services import session_summary_worker as ssw_mod
from telegram_bot.services.session_summary_worker import SessionSummaryWorker


def _worker(**kwargs) -> SessionSummaryWorker:
    defaults: dict = {
        "redis": AsyncMock(),
        "llm": MagicMock(),
        "kommo_client": None,
        "idle_timeout_min": 30,
        "poll_interval_sec": 10,
    }
    defaults.update(kwargs)
    return SessionSummaryWorker(**defaults)


def _one_idle_session(worker: SessionSummaryWorker) -> None:
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:111"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Budget is 80k EUR"},
            {"role": "assistant", "content": "I have options in range"},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="summary text")


def _score_names(lf: MagicMock) -> list[str]:
    return [c.kwargs.get("name") for c in lf.score_current_trace.call_args_list]


# --- _write_summary outcomes -------------------------------------------------


@pytest.mark.asyncio
async def test_write_summary_no_kommo_returns_no_kommo():
    worker = _worker(kommo_client=None)
    assert await worker._write_summary("u1", "s") == "no_kommo"


@pytest.mark.asyncio
async def test_write_summary_skipped_when_lead_unresolved():
    kommo = AsyncMock()
    worker = _worker(kommo_client=kommo)
    # default _resolve_lead_id returns None (lead resolution pending, #445)
    assert await worker._write_summary("u1", "s") == "skipped_no_lead"
    kommo.add_note.assert_not_called()


@pytest.mark.asyncio
async def test_write_summary_written_when_lead_resolved():
    kommo = AsyncMock()
    worker = _worker(kommo_client=kommo)
    worker._resolve_lead_id = AsyncMock(return_value=555)
    assert await worker._write_summary("u1", "s") == "written"
    kommo.add_note.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_summary_failed_when_add_note_raises():
    kommo = AsyncMock()
    kommo.add_note = AsyncMock(side_effect=RuntimeError("kommo 500"))
    worker = _worker(kommo_client=kommo)
    worker._resolve_lead_id = AsyncMock(return_value=555)
    assert await worker._write_summary("u1", "s") == "failed"


# --- cycle-level honest scoring ---------------------------------------------


@pytest.mark.asyncio
async def test_cycle_scores_kommo_skipped_not_written(monkeypatch):
    lf = MagicMock()
    monkeypatch.setattr(ssw_mod, "get_client", lambda: lf)
    worker = _worker(kommo_client=AsyncMock())  # lead unresolved -> skipped
    _one_idle_session(worker)

    await worker._check_idle_sessions()

    names = _score_names(lf)
    assert "session_summary_kommo_skipped" in names
    assert "session_summary_kommo_written" not in names


@pytest.mark.asyncio
async def test_cycle_scores_kommo_written_when_resolved(monkeypatch):
    lf = MagicMock()
    monkeypatch.setattr(ssw_mod, "get_client", lambda: lf)
    kommo = AsyncMock()
    worker = _worker(kommo_client=kommo)
    worker._resolve_lead_id = AsyncMock(return_value=555)
    _one_idle_session(worker)

    await worker._check_idle_sessions()

    names = _score_names(lf)
    assert "session_summary_kommo_written" in names
    assert "session_summary_kommo_skipped" not in names
    kommo.add_note.assert_awaited_once()
