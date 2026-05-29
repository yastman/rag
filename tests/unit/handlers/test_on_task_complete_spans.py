"""`on_task_complete` span-completeness contract (#2214, P1).

`crm-quick-complete` had `@observe` but neither branch updated the span, so a
successful completion and a failed one looked identical on the Langfuse
dashboard. This mirrors the `on_task_postpone` pattern: record input on entry,
output on success, and `level="ERROR"` + `status_message` on failure. The span
update must be guarded so a missing Langfuse client never breaks the handler.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _patched_lf(monkeypatch) -> MagicMock:
    from telegram_bot.handlers import crm_callbacks as cb_mod

    mock_lf = MagicMock()
    monkeypatch.setattr(cb_mod, "get_client", lambda: mock_lf)
    return mock_lf


def _span_kwargs(mock_lf: MagicMock) -> list[dict]:
    return [c.kwargs for c in mock_lf.update_current_span.call_args_list]


@pytest.mark.asyncio
async def test_complete_success_sets_output_span(monkeypatch):
    mock_lf = _patched_lf(monkeypatch)
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    kommo = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:complete:42"
    callback.message = None  # skip edit_text branch

    await on_task_complete(callback, kommo_client=kommo)

    kommo.complete_task.assert_awaited_once_with(42)
    kwargs = _span_kwargs(mock_lf)
    assert any("output" in k for k in kwargs), "success branch must record span output"
    assert not any(k.get("level") == "ERROR" for k in kwargs), "success must not be ERROR"


@pytest.mark.asyncio
async def test_complete_failure_sets_error_span(monkeypatch):
    mock_lf = _patched_lf(monkeypatch)
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    kommo = AsyncMock()
    kommo.complete_task = AsyncMock(side_effect=RuntimeError("kommo 500"))
    callback = AsyncMock()
    callback.data = "crm:task:complete:42"
    callback.message = None

    await on_task_complete(callback, kommo_client=kommo)

    kwargs = _span_kwargs(mock_lf)
    assert any(k.get("level") == "ERROR" for k in kwargs), "failure must mark span ERROR"
    assert any(k.get("status_message") for k in kwargs), "failure must set status_message"
    # user still gets an alert
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_complete_no_kommo_records_cancelled(monkeypatch):
    mock_lf = _patched_lf(monkeypatch)
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    callback = AsyncMock()
    callback.data = "crm:task:complete:42"

    await on_task_complete(callback, kommo_client=None)

    kwargs = _span_kwargs(mock_lf)
    assert any("output" in k for k in kwargs), "no-CRM branch must record a span output"
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_complete_no_crash_when_langfuse_unavailable(monkeypatch):
    from telegram_bot.handlers import crm_callbacks as cb_mod

    monkeypatch.setattr(cb_mod, "get_client", lambda: None)
    from telegram_bot.handlers.crm_callbacks import on_task_complete

    kommo = AsyncMock()
    callback = AsyncMock()
    callback.data = "crm:task:complete:42"
    callback.message = None

    # must not raise even though no Langfuse client is available
    await on_task_complete(callback, kommo_client=kommo)
    kommo.complete_task.assert_awaited_once_with(42)
