from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.lead_score_sync import sync_pending_lead_scores


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_returns_zero_when_dependencies_missing() -> None:
    result = await sync_pending_lead_scores(
        scoring_store=None,
        kommo_client=None,
        score_field_id=1,
        band_field_id=2,
    )

    assert result == {"synced": 0, "failed": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_skips_invalid_field_ids() -> None:
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=0,
        band_field_id=2,
    )

    assert result == {"synced": 0, "failed": 0, "skipped": 0}
    scoring_store.list_pending_sync.assert_not_called()


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_marks_synced_and_skipped() -> None:
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()
    scoring_store.list_pending_sync.return_value = [
        SimpleNamespace(
            lead_id=11,
            session_id="s1",
            score_value=87,
            score_band="hot",
            kommo_lead_id=9011,
        ),
        SimpleNamespace(
            lead_id=12,
            session_id="s2",
            score_value=12,
            score_band="cold",
            kommo_lead_id=None,
        ),
    ]

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=1001,
        band_field_id=1002,
        limit=5,
    )

    assert result == {"synced": 1, "failed": 0, "skipped": 1}
    scoring_store.list_pending_sync.assert_awaited_once_with(limit=5)
    kommo_client.update_lead_score.assert_awaited_once()
    call = kommo_client.update_lead_score.await_args.kwargs
    assert call["lead_id"] == 9011
    assert call["idempotency_key"] == "lead-score:11:s1:87:hot"
    assert "custom_fields_values" in call["payload"]
    scoring_store.mark_synced.assert_awaited_once_with(lead_id=11)
    scoring_store.mark_failed.assert_not_called()


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_marks_failed_on_kommo_error() -> None:
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()
    scoring_store.list_pending_sync.return_value = [
        SimpleNamespace(
            lead_id=42,
            session_id="s3",
            score_value=50,
            score_band="warm",
            kommo_lead_id=9042,
        )
    ]
    kommo_client.update_lead_score.side_effect = RuntimeError("kommo down")

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=1001,
        band_field_id=1002,
    )

    assert result == {"synced": 0, "failed": 1, "skipped": 0}
    scoring_store.mark_failed.assert_awaited_once_with(lead_id=42, error="kommo_error")
    scoring_store.mark_synced.assert_not_called()


class TestLeadScoreSyncObserveInstrumentation:
    """Tests for @observe instrumentation on sync_pending_lead_scores (#1663).

    Contract: sync_pending_lead_scores must be wrapped with @observe so the
    background job emits a named Langfuse span instead of running untraced.
    Curated update_current_span(output=...) records aggregate counters and
    NEVER captures full per-record payloads (no PII, no kommo internals).
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch):
        """Replace get_client used by the lead_score_sync module with a recording mock."""
        from unittest.mock import MagicMock

        from telegram_bot.services import lead_score_sync as lss_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(lss_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe_and_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace @observe + propagate_attributes at module-import time with no-ops.

        This lets behavior assertions run without the real Langfuse SDK.
        """
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
        sys.modules.pop("telegram_bot.services.lead_score_sync", None)
        importlib.import_module("telegram_bot.services.lead_score_sync")

    def test_lead_score_sync_module_imports_observe_get_client_and_propagate_attributes(self):
        """Module wires the Langfuse decorator + helpers (#1663 contract)."""
        from telegram_bot.services import lead_score_sync as lss_mod

        assert hasattr(lss_mod, "observe"), (
            "telegram_bot.services.lead_score_sync must import `observe` "
            "from telegram_bot.observability for the @observe decorator on "
            "sync_pending_lead_scores"
        )
        assert hasattr(lss_mod, "get_client"), (
            "telegram_bot.services.lead_score_sync must import `get_client` "
            "for curated update_current_span calls"
        )
        assert hasattr(lss_mod, "propagate_attributes"), (
            "telegram_bot.services.lead_score_sync must import `propagate_attributes` "
            "for tags=['job', 'lead-scoring']"
        )

    def test_lead_score_sync_observe_decorator_applied_with_correct_kwargs(self, monkeypatch):
        """@observe must be applied with the trace-coverage audit's exact kwargs."""
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        captured: list[dict[str, object]] = []

        def recording_observe(**kwargs):
            captured.append(kwargs)

            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", recording_observe)
        sys.modules.pop("telegram_bot.services.lead_score_sync", None)
        importlib.import_module("telegram_bot.services.lead_score_sync")

        sync_calls = [c for c in captured if c.get("name") == "job-lead-score-sync"]
        assert len(sync_calls) == 1, (
            f"Expected exactly one @observe(name='job-lead-score-sync', ...). Captured: {captured}"
        )
        kwargs = sync_calls[0]
        assert kwargs.get("capture_input") is False
        assert kwargs.get("capture_output") is False

    @pytest.mark.asyncio
    async def test_propagate_attributes_called_with_lead_scoring_tags(self, monkeypatch):
        """propagate_attributes must be called with tags=['job', 'lead-scoring']."""
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
        sys.modules.pop("telegram_bot.services.lead_score_sync", None)
        importlib.import_module("telegram_bot.services.lead_score_sync")

        self._patched_lf(monkeypatch)
        from telegram_bot.services.lead_score_sync import sync_pending_lead_scores

        await sync_pending_lead_scores(
            scoring_store=None,
            kommo_client=None,
            score_field_id=1,
            band_field_id=2,
        )

        assert any(kw.get("tags") == ["job", "lead-scoring"] for kw in recorded_kwargs), (
            "propagate_attributes(tags=['job', 'lead-scoring']) was never called. "
            f"Recorded: {recorded_kwargs}"
        )

    @pytest.mark.asyncio
    async def test_sync_works_when_langfuse_client_unavailable(self, monkeypatch):
        """Lead-score sync must degrade gracefully when tracing is unavailable."""
        self._disable_observe_and_propagate(monkeypatch)

        from telegram_bot.services import lead_score_sync as lss_mod
        from telegram_bot.services.lead_score_sync import sync_pending_lead_scores

        monkeypatch.setattr(lss_mod, "get_client", lambda: None)

        result = await sync_pending_lead_scores(
            scoring_store=None,
            kommo_client=None,
            score_field_id=1,
            band_field_id=2,
        )

        assert result == {"synced": 0, "failed": 0, "skipped": 0}

    @pytest.mark.asyncio
    async def test_output_records_processed_failed_skipped_counts(self, monkeypatch):
        """Span output must record processed/failed/skipped after the batch."""
        self._disable_observe_and_propagate(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.lead_score_sync import sync_pending_lead_scores

        scoring_store = AsyncMock()
        kommo_client = AsyncMock()
        scoring_store.list_pending_sync.return_value = [
            SimpleNamespace(
                lead_id=1,
                session_id="s1",
                score_value=10,
                score_band="cold",
                kommo_lead_id=901,
            ),
            SimpleNamespace(
                lead_id=2,
                session_id="s2",
                score_value=80,
                score_band="hot",
                kommo_lead_id=None,
            ),
        ]

        await sync_pending_lead_scores(
            scoring_store=scoring_store,
            kommo_client=kommo_client,
            score_field_id=1001,
            band_field_id=1002,
        )

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list if "output" in c.kwargs
        ]
        assert len(output_calls) >= 1, "update_current_span(output=...) was never called"
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert "processed" in captured_output
        assert "failed" in captured_output
        assert "skipped" in captured_output
        assert captured_output["processed"] == 1
        assert captured_output["failed"] == 0
        assert captured_output["skipped"] == 1

    @pytest.mark.asyncio
    async def test_lead_score_sync_exception_path_records_error_level_and_reraises(self, monkeypatch):
        """On exception, update_current_span(level='ERROR', ...) and re-raise."""
        self._disable_observe_and_propagate(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.lead_score_sync import sync_pending_lead_scores

        scoring_store = AsyncMock()
        scoring_store.list_pending_sync.side_effect = RuntimeError("DB exploded")
        kommo_client = AsyncMock()

        with pytest.raises(RuntimeError, match="DB exploded"):
            await sync_pending_lead_scores(
                scoring_store=scoring_store,
                kommo_client=kommo_client,
                score_field_id=1,
                band_field_id=2,
            )

        error_calls = [
            c.kwargs
            for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert len(error_calls) >= 1, (
            "Failure path must call update_current_span(level='ERROR', ...)"
        )
        status = error_calls[0].get("status_message", "")
        assert "DB exploded" in status
        assert len(status) <= 220, "status_message must be truncated to ~200 chars"
