"""Tests for NurturingScheduler (***REMOVED***390)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.nurturing_scheduler import NurturingScheduler


@pytest.fixture
def fake_services():
    config = MagicMock()
    config.nurturing_interval_minutes = 60
    config.funnel_rollup_cron = "15 * * * *"
    config.nurturing_dispatch_enabled = False
    return {
        "nurturing_service": AsyncMock(),
        "analytics_service": AsyncMock(),
        "lease_store": AsyncMock(),
        "config": config,
    }


@pytest.mark.asyncio
async def test_scheduler_configures_single_instance_coalesced_jobs(fake_services):
    scheduler = NurturingScheduler(**fake_services)
    await scheduler.start()

    assert scheduler.has_job("nurturing-batch")
    assert scheduler.has_job("funnel-analytics-rollup")

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_has_no_jobs_before_start(fake_services):
    scheduler = NurturingScheduler(**fake_services)

    assert not scheduler.has_job("nurturing-batch")
    assert not scheduler.has_job("funnel-analytics-rollup")


@pytest.mark.asyncio
async def test_scheduler_stop_is_idempotent(fake_services):
    scheduler = NurturingScheduler(**fake_services)
    await scheduler.start()
    await scheduler.stop()
    ***REMOVED*** Second stop should not raise
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_uses_funnel_rollup_cron_from_config(fake_services):
    fake_services["config"].funnel_rollup_cron = "7 * * * *"
    scheduler = NurturingScheduler(**fake_services)
    await scheduler.start()

    job = scheduler._scheduler.get_job("funnel-analytics-rollup")
    assert job is not None
    assert "minute='7'" in str(job.trigger)

    await scheduler.stop()


class TestNurturingSchedulerObserveInstrumentation:
    """Tests for @observe instrumentation on NurturingScheduler jobs (***REMOVED***1663).

    Contract: run_nurturing_dispatch and run_funnel_rollup must be wrapped with
    @observe, propagate tags=['job', '<area>'], and on exception emit
    update_current_span(level='ERROR', ...) before re-raising so APScheduler
    can record the failure.
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch):
        from telegram_bot.services import nurturing_scheduler as ns_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(ns_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe_and_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
        import contextlib
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        @contextlib.contextmanager
        def fake_propagate(**_kwargs):
            yield

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        monkeypatch.setattr(observability_mod, "propagate_attributes", fake_propagate)
        sys.modules.pop("telegram_bot.services.nurturing_scheduler", None)
        importlib.import_module("telegram_bot.services.nurturing_scheduler")

    def test_nurturing_scheduler_module_imports_observe_get_client_and_propagate_attributes(self):
        """Module wires the Langfuse decorator + helpers (***REMOVED***1663 contract)."""
        from telegram_bot.services import nurturing_scheduler as ns_mod

        assert hasattr(ns_mod, "observe")
        assert hasattr(ns_mod, "get_client"), (
            "telegram_bot.services.nurturing_scheduler must import `get_client` "
            "for curated update_current_span(level='ERROR', ...) calls"
        )
        assert hasattr(ns_mod, "propagate_attributes"), (
            "telegram_bot.services.nurturing_scheduler must import `propagate_attributes` "
            "for tags=['job', 'nurturing'] / ['job', 'analytics']"
        )

    def test_dispatch_and_rollup_observe_decorators_applied_with_correct_kwargs(self, monkeypatch):
        """@observe must be applied with the exact issue-spec kwargs to both jobs."""
        import contextlib
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        captured: list[dict[str, object]] = []

        def recording_observe(**kwargs):
            captured.append(kwargs)

            def decorator(func):
                return func

            return decorator

        @contextlib.contextmanager
        def fake_propagate(**_kwargs):
            yield

        monkeypatch.setattr(observability_mod, "observe", recording_observe)
        monkeypatch.setattr(observability_mod, "propagate_attributes", fake_propagate)
        sys.modules.pop("telegram_bot.services.nurturing_scheduler", None)
        importlib.import_module("telegram_bot.services.nurturing_scheduler")

        dispatch_calls = [c for c in captured if c.get("name") == "job-nurturing-dispatch"]
        assert len(dispatch_calls) == 1, (
            f"Expected one @observe(name='job-nurturing-dispatch', ...). Captured: {captured}"
        )
        assert dispatch_calls[0].get("capture_input") is False
        assert dispatch_calls[0].get("capture_output") is False

        rollup_calls = [c for c in captured if c.get("name") == "job-funnel-rollup"]
        assert len(rollup_calls) == 1, (
            f"Expected one @observe(name='job-funnel-rollup', ...). Captured: {captured}"
        )
        assert rollup_calls[0].get("capture_input") is False
        assert rollup_calls[0].get("capture_output") is False

        ***REMOVED*** Ensure the existing nurturing-scheduler-tick decorator is preserved.
        tick_calls = [c for c in captured if c.get("name") == "nurturing-scheduler-tick"]
        assert len(tick_calls) == 1, "Existing run_nurturing_batch @observe must be preserved"

    @pytest.mark.asyncio
    async def test_dispatch_propagates_nurturing_tags(self, monkeypatch, fake_services):
        """run_nurturing_dispatch must call propagate_attributes(tags=['job', 'nurturing'])."""
        import contextlib
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        recorded_kwargs: list[dict[str, object]] = []

        @contextlib.contextmanager
        def recording_propagate(**kwargs):
            recorded_kwargs.append(kwargs)
            yield

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        monkeypatch.setattr(observability_mod, "propagate_attributes", recording_propagate)
        sys.modules.pop("telegram_bot.services.nurturing_scheduler", None)
        importlib.import_module("telegram_bot.services.nurturing_scheduler")

        self._patched_lf(monkeypatch)
        from telegram_bot.services.nurturing_scheduler import NurturingScheduler

        scheduler = NurturingScheduler(**fake_services)
        await scheduler.run_nurturing_dispatch()

        assert any(kw.get("tags") == ["job", "nurturing"] for kw in recorded_kwargs), (
            f"Expected tags=['job', 'nurturing']. Recorded: {recorded_kwargs}"
        )

    @pytest.mark.asyncio
    async def test_rollup_propagates_analytics_tags(self, monkeypatch, fake_services):
        """run_funnel_rollup must call propagate_attributes(tags=['job', 'analytics'])."""
        import contextlib
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        recorded_kwargs: list[dict[str, object]] = []

        @contextlib.contextmanager
        def recording_propagate(**kwargs):
            recorded_kwargs.append(kwargs)
            yield

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        monkeypatch.setattr(observability_mod, "propagate_attributes", recording_propagate)
        sys.modules.pop("telegram_bot.services.nurturing_scheduler", None)
        importlib.import_module("telegram_bot.services.nurturing_scheduler")

        self._patched_lf(monkeypatch)
        from telegram_bot.services.nurturing_scheduler import NurturingScheduler

        fake_services["analytics_service"].build_daily_snapshot = AsyncMock(return_value=[])
        scheduler = NurturingScheduler(**fake_services)
        await scheduler.run_funnel_rollup()

        assert any(kw.get("tags") == ["job", "analytics"] for kw in recorded_kwargs), (
            f"Expected tags=['job', 'analytics']. Recorded: {recorded_kwargs}"
        )

    @pytest.mark.asyncio
    async def test_dispatch_error_preserves_original_exception_when_langfuse_unavailable(
        self, monkeypatch, fake_services
    ):
        """Missing Langfuse client must not mask the job failure."""
        self._disable_observe_and_propagate(monkeypatch)

        from telegram_bot.services import nurturing_scheduler as ns_mod
        from telegram_bot.services.nurturing_scheduler import NurturingScheduler

        monkeypatch.setattr(ns_mod, "get_client", lambda: None)
        fake_services["nurturing_service"].dispatch_pending = AsyncMock(
            side_effect=RuntimeError("Dispatch boom")
        )
        scheduler = NurturingScheduler(**fake_services)

        with pytest.raises(RuntimeError, match="Dispatch boom"):
            await scheduler.run_nurturing_dispatch()

    @pytest.mark.asyncio
    async def test_dispatch_exception_records_error_and_reraises(self, monkeypatch, fake_services):
        """Dispatch must record ERROR level and re-raise so APScheduler logs failure."""
        self._disable_observe_and_propagate(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.nurturing_scheduler import NurturingScheduler

        fake_services["nurturing_service"].dispatch_pending = AsyncMock(
            side_effect=RuntimeError("Dispatch boom")
        )
        scheduler = NurturingScheduler(**fake_services)

        with pytest.raises(RuntimeError, match="Dispatch boom"):
            await scheduler.run_nurturing_dispatch()

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert len(error_calls) >= 1
        assert "Dispatch boom" in error_calls[0].get("status_message", "")
        assert len(error_calls[0].get("status_message", "")) <= 220

    @pytest.mark.asyncio
    async def test_rollup_exception_records_error_and_reraises(self, monkeypatch, fake_services):
        """Rollup must record ERROR level and re-raise so APScheduler logs failure."""
        self._disable_observe_and_propagate(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.nurturing_scheduler import NurturingScheduler

        fake_services["analytics_service"].build_daily_snapshot = AsyncMock(
            side_effect=RuntimeError("Rollup boom")
        )
        scheduler = NurturingScheduler(**fake_services)

        with pytest.raises(RuntimeError, match="Rollup boom"):
            await scheduler.run_funnel_rollup()

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert len(error_calls) >= 1
        assert "Rollup boom" in error_calls[0].get("status_message", "")
