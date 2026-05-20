"""Tests for SessionSummaryWorker (***REMOVED***445 Task 5)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.session_summary_worker import SessionSummaryWorker


def _mock_completion(content: str) -> MagicMock:
    """Helper: create a mock ChatCompletion response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    return mock_response


@pytest.fixture
def worker():
    return SessionSummaryWorker(
        redis=AsyncMock(),
        llm=MagicMock(),
        kommo_client=None,
        idle_timeout_min=30,
        poll_interval_sec=10,  ***REMOVED*** fast for tests
    )


async def test_worker_starts_and_stops(worker):
    await worker.start()
    assert worker._task is not None
    await worker.stop()
    assert worker._task.done()


async def test_no_idle_sessions(worker):
    worker._redis.scan = AsyncMock(return_value=(0, []))
    result = await worker._check_idle_sessions()
    assert result == 0


async def test_idle_session_detected(worker):
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:123"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Looking for 2-room apartment"},
            {"role": "assistant", "content": "I found several options..."},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="Client looking for 2-room apartment")
    count = await worker._check_idle_sessions()
    assert count == 1
    worker._redis.delete.assert_called_once()


async def test_idle_session_scoring_skipped_when_langfuse_client_missing(worker, monkeypatch):
    """Missing Langfuse client must not break the idle-session worker loop."""
    from telegram_bot.services import session_summary_worker as ssw_mod

    monkeypatch.setattr(ssw_mod, "get_client", lambda: None)
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:123"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Looking for 2-room apartment"},
            {"role": "assistant", "content": "I found several options..."},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="Client looking for 2-room apartment")

    count = await worker._check_idle_sessions()

    assert count == 1
    worker._redis.delete.assert_called_once()


async def test_skip_short_conversations(worker):
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:456"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Hi"},
        ]
    )
    count = await worker._check_idle_sessions()
    assert count == 0  ***REMOVED*** < 2 messages, skip


async def test_graceful_stop_during_processing(worker):
    """Worker stops cleanly even if already running."""
    await worker.start()
    assert worker._task is not None
    ***REMOVED*** stop() must complete without hanging
    await asyncio.wait_for(worker.stop(), timeout=3.0)
    assert worker._task.done()


async def test_recent_session_not_processed(worker):
    """Session active 5 min ago should not be processed (under 30 min threshold)."""
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:789"]))
    ***REMOVED*** 5 minutes ago — under idle_timeout_min=30
    worker._redis.get = AsyncMock(return_value=str(time.time() - 300).encode())
    worker._generate_summary = AsyncMock()
    count = await worker._check_idle_sessions()
    assert count == 0
    worker._generate_summary.assert_not_called()


async def test_kommo_write_skipped_without_lead_id(worker):
    """Kommo add_note is skipped when lead_id is not yet resolved (entity_id=0 guard)."""
    mock_kommo = AsyncMock()
    worker._kommo = mock_kommo
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:111"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Budget is 80k EUR"},
            {"role": "assistant", "content": "Great, I have options in your range"},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="Budget 80k EUR client")
    await worker._check_idle_sessions()
    ***REMOVED*** lead_id not yet resolved — add_note should NOT be called
    mock_kommo.add_note.assert_not_called()


async def test_none_redis_key_skipped(worker):
    """Keys that have been expired (get returns None) are skipped."""
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:999"]))
    worker._redis.get = AsyncMock(return_value=None)
    worker._generate_summary = AsyncMock()
    count = await worker._check_idle_sessions()
    assert count == 0
    worker._generate_summary.assert_not_called()


async def test_scan_multi_page_cursor_accumulation(worker):
    """SCAN loop accumulates keys across multiple pages (cursor non-zero then zero)."""
    ***REMOVED*** First page returns cursor=5 (more pages), second page returns cursor=0 (done)
    worker._redis.scan = AsyncMock(
        side_effect=[
            (5, [b"session:last_active:101"]),
            (0, [b"session:last_active:102"]),
        ]
    )
    ***REMOVED*** Both keys are old enough to process
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "msg"},
            {"role": "assistant", "content": "reply"},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="summary")
    count = await worker._check_idle_sessions()
    ***REMOVED*** Both keys from both pages should be processed
    assert count == 2
    assert worker._redis.scan.call_count == 2


class TestSessionSummaryWorkerObserveInstrumentation:
    """Tests for @observe instrumentation on SessionSummaryWorker._generate_summary (***REMOVED***1662).

    Contract: ``_generate_summary`` must be wrapped with
    ``@observe(name="session-summary-llm", capture_input=False, capture_output=False)``
    so the auto-traced generation produced by ``langfuse.openai`` is parented
    under a named span (instead of becoming a flat child of the outer
    ``session-summary-check`` span). Curated input/output payloads are written
    via ``update_current_span``; full conversation history and full summary
    text must NOT appear in span fields. On LLM failure the span is recorded
    at ERROR level with a truncated ``status_message`` and the exception is
    re-raised (the outer ``_run_loop`` already swallows worker-cycle errors,
    see ***REMOVED***1662 Implementation Plan step 4).
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Replace get_client used by the worker module with a recording mock."""
        from telegram_bot.services import session_summary_worker as ssw_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(ssw_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe(monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace the @observe decorator at module-import time with a no-op.

        This lets behavior assertions (input/output/error) run without the real
        Langfuse SDK trying to start an OTEL span.
        """
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        ***REMOVED*** Reload session_summary_worker so it picks up the no-op decorator.
        sys.modules.pop("telegram_bot.services.session_summary_worker", None)
        importlib.import_module("telegram_bot.services.session_summary_worker")

    def test_module_imports_observe_and_get_client(self):
        """Module wires the Langfuse decorator + client accessor (***REMOVED***1662 contract)."""
        from telegram_bot.services import session_summary_worker as ssw_mod

        assert hasattr(ssw_mod, "observe"), (
            "telegram_bot.services.session_summary_worker must import `observe` "
            "from telegram_bot.observability for the @observe decorator on "
            "SessionSummaryWorker._generate_summary"
        )
        assert hasattr(ssw_mod, "get_client"), (
            "telegram_bot.services.session_summary_worker must import "
            "`get_client` from telegram_bot.observability for curated "
            "update_current_span calls"
        )

    def test_observe_decorator_applied_with_correct_kwargs(self, monkeypatch):
        """@observe must be applied with the trace-coverage audit's exact kwargs.

        Specifically the LLM-call wrapper must use:
            @observe(name="session-summary-llm",
                     capture_input=False, capture_output=False)
        which mirrors the ``nurturing-llm-generate`` pattern referenced in
        issue ***REMOVED***1662 SDK Baseline.
        """
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        captured_calls: list[dict[str, object]] = []

        def recording_observe(**kwargs):
            captured_calls.append(kwargs)

            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", recording_observe)
        sys.modules.pop("telegram_bot.services.session_summary_worker", None)
        importlib.import_module("telegram_bot.services.session_summary_worker")

        ***REMOVED*** The module already applies @observe to _check_idle_sessions
        ***REMOVED*** (name="session-summary-check"). After this issue ships, an additional
        ***REMOVED*** @observe(name="session-summary-llm", ...) must also be present on
        ***REMOVED*** _generate_summary.
        llm_calls = [c for c in captured_calls if c.get("name") == "session-summary-llm"]
        assert len(llm_calls) == 1, (
            "Expected exactly one @observe(name='session-summary-llm', ...) on "
            "SessionSummaryWorker._generate_summary, got "
            f"{[c.get('name') for c in captured_calls]}"
        )
        kwargs = llm_calls[0]
        assert kwargs.get("capture_input") is False
        assert kwargs.get("capture_output") is False

    async def test_input_payload_is_curated_history_turns_and_model(self, monkeypatch):
        """Span input must record history_turns + model only (no full history)."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        ***REMOVED*** Re-import to bind the no-op observe applied above.
        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
            kommo_client=None,
            summary_model="claude-haiku-4-5",
        )
        worker._llm.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Краткая выжимка для клиента")
        )

        history = [
            {"role": "user", "content": "Ищу 2-комнатную квартиру у моря, бюджет 80к EUR"},
            {"role": "assistant", "content": "Подобрал несколько вариантов в Несебре..."},
            {"role": "user", "content": "А что насчёт района Святой Влас?"},
            {"role": "assistant", "content": "Святой Влас — отличный выбор, есть три варианта."},
        ]

        await worker._generate_summary(history)

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "input" in c.kwargs
        ]
        assert len(input_calls) >= 1, (
            "update_current_span(input=...) was never called on _generate_summary"
        )
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert captured_input.get("history_turns") == len(history)
        assert captured_input.get("model") == "claude-haiku-4-5"

        ***REMOVED*** Forbidden: no full history content in span input.
        rendered = str(captured_input)
        for msg in history:
            assert msg["content"] not in rendered, (
                "Full conversation message content must not appear in span input "
                "(issue ***REMOVED***1662 Forbidden section)"
            )

    async def test_output_payload_is_curated_summary_len_and_preview(self, monkeypatch):
        """Span output must record summary_len + bounded summary_preview only."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        long_summary = (
            "Клиент ищет 2-комнатную квартиру у моря в Болгарии, бюджет до 80к EUR. "
            "Заинтересован в Несебре и Святом Власе. Просил подборку с видом на море "
            "и инфраструктурой рядом. Готов рассмотреть вторичку и новостройки. "
            "Следующий шаг: отправить три варианта в Святом Власе на этой неделе."
        )
        assert len(long_summary) > 200  ***REMOVED*** sanity: must exceed preview cap

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
        )
        worker._llm.chat.completions.create = AsyncMock(return_value=_mock_completion(long_summary))

        history = [
            {"role": "user", "content": "msg"},
            {"role": "assistant", "content": "reply"},
        ]

        result = await worker._generate_summary(history)
        assert result == long_summary  ***REMOVED*** behavior unchanged on success path

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert len(output_calls) >= 1, (
            "update_current_span(output=...) was never called on _generate_summary"
        )
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert captured_output.get("summary_len") == len(long_summary)
        preview = captured_output.get("summary_preview", "")
        assert isinstance(preview, str)
        assert len(preview) <= 120, f"summary_preview must be <=120 chars, got {len(preview)}"

        ***REMOVED*** Forbidden: full summary text must not appear in span output.
        assert long_summary not in str(captured_output), (
            "Full summary text must not appear in span output (issue ***REMOVED***1662 Forbidden section)"
        )

    async def test_generate_summary_works_when_langfuse_client_is_none(self, monkeypatch):
        """Tracing must degrade gracefully when Langfuse is unavailable."""
        self._disable_observe(monkeypatch)

        from telegram_bot.services import session_summary_worker as ssw_mod
        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        monkeypatch.setattr(ssw_mod, "get_client", lambda: None)

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
        )
        worker._llm.chat.completions.create = AsyncMock(
            return_value=_mock_completion("Краткая выжимка")
        )

        result = await worker._generate_summary(
            [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        )

        assert result == "Краткая выжимка"

    async def test_exception_path_records_error_level_and_reraises(self, monkeypatch):
        """On LLM exception: span level=ERROR with status_message, then re-raise.

        Per issue ***REMOVED***1662 Implementation Plan step 4: record ERROR span and
        re-raise. The outer ``_run_loop`` already swallows worker-cycle errors,
        so re-raising is safe and gives ``_check_idle_sessions`` a chance to
        observe the failure cleanly.
        """
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
        )
        worker._llm.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("LLM exploded mid-summary")
        )

        history = [
            {"role": "user", "content": "msg"},
            {"role": "assistant", "content": "reply"},
        ]

        with pytest.raises(RuntimeError, match="LLM exploded mid-summary"):
            await worker._generate_summary(history)

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert len(error_calls) >= 1, (
            "Failure path must call update_current_span(level='ERROR', ...)"
        )
        status = error_calls[0].get("status_message", "")
        assert "LLM exploded mid-summary" in status
        assert len(status) <= 220, (
            f"status_message must be truncated to ~200 chars, got {len(status)}"
        )

    async def test_short_summary_preview_is_full_summary(self, monkeypatch):
        """Short summaries (<=120 chars) flow through the preview field intact."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        short_summary = "Клиент: 2BR, Несебр, до 80к EUR."
        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
        )
        worker._llm.chat.completions.create = AsyncMock(
            return_value=_mock_completion(short_summary)
        )

        await worker._generate_summary(
            [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        )

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert output_calls, "update_current_span(output=...) was never called"
        captured_output = output_calls[-1]["output"]
        assert captured_output.get("summary_preview") == short_summary
        assert captured_output.get("summary_len") == len(short_summary)



class TestHistorySourceWiring:
    """Regression tests for ***REMOVED***1599: history_source must be configurable.

    Before this fix the worker silently no-op'd whenever it was enabled
    because ``_get_conversation_history`` was a placeholder returning ``[]``,
    so it deleted idle session keys without ever generating a summary.
    """

    async def test_idle_session_uses_history_source_callable(self):
        """A wired history_source produces real history → summary is generated."""
        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        async def fake_history_source(user_id: str) -> list[dict[str, str]]:
            assert user_id == "777"
            return [
                {"role": "user", "content": "Ищу 2BR в Несебре"},
                {"role": "assistant", "content": "Подобрал три варианта"},
            ]

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
            history_source=fake_history_source,
            idle_timeout_min=30,
        )
        worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:777"]))
        worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
        worker._redis.delete = AsyncMock()
        worker._generate_summary = AsyncMock(return_value="Клиент: 2BR Несебр")

        count = await worker._check_idle_sessions()

        assert count == 1
        worker._generate_summary.assert_called_once()
        passed_history = worker._generate_summary.call_args.args[0]
        assert len(passed_history) == 2

    async def test_default_get_history_returns_empty_without_source(self):
        """Without history_source the placeholder still returns []."""
        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        worker = SessionSummaryWorker(redis=AsyncMock(), llm=AsyncMock())
        result = await worker._get_conversation_history("123")
        assert result == []

    async def test_history_source_exception_falls_back_to_empty(self):
        """A buggy history_source must not crash the worker — returns []."""
        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        async def boom(_user_id: str) -> list[dict[str, str]]:
            raise RuntimeError("checkpointer down")

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
            history_source=boom,
        )
        result = await worker._get_conversation_history("123")
        assert result == []

    async def test_start_logs_warning_when_history_source_missing(self, caplog):
        """Operators must see a startup warning when the worker is a no-op."""
        import logging

        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        worker = SessionSummaryWorker(redis=AsyncMock(), llm=AsyncMock())
        with caplog.at_level(logging.WARNING, logger="telegram_bot.services.session_summary_worker"):
            await worker.start()
            await worker.stop()

        warnings = [
            rec for rec in caplog.records if "without history_source" in rec.getMessage()
        ]
        assert warnings, (
            "Worker must log WARNING at start when history_source is not wired (***REMOVED***1599)"
        )

    async def test_start_does_not_warn_when_history_source_present(self, caplog):
        """A wired worker must not log the no-op warning."""
        import logging

        from telegram_bot.services.session_summary_worker import SessionSummaryWorker

        async def empty_source(_user_id: str) -> list[dict[str, str]]:
            return []

        worker = SessionSummaryWorker(
            redis=AsyncMock(),
            llm=AsyncMock(),
            history_source=empty_source,
        )
        with caplog.at_level(logging.WARNING, logger="telegram_bot.services.session_summary_worker"):
            await worker.start()
            await worker.stop()

        warnings = [
            rec for rec in caplog.records if "without history_source" in rec.getMessage()
        ]
        assert not warnings
