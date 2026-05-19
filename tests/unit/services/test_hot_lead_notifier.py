"""Tests for hot lead notification service (#388)."""

from unittest.mock import AsyncMock

from telegram_bot.services.hot_lead_notifier import HotLeadNotifier


async def test_notifier_sends_once_per_session():
    """Fan-out to managers on first event; dedupe skips second."""
    cache = AsyncMock()
    cache.redis = AsyncMock()
    cache.redis.set = AsyncMock(side_effect=[True, False])
    bot = AsyncMock()

    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1, 2], dedupe_ttl_sec=3600)
    payload = {"lead_id": 77, "score": 88, "session_id": "chat-abc"}

    await notifier.notify_if_hot(payload)
    await notifier.notify_if_hot(payload)

    # First call fans out to 2 managers, second is deduped
    assert bot.send_message.await_count == 2


async def test_notifier_returns_false_when_deduped():
    """Return False when lead notification was already sent."""
    cache = AsyncMock()
    cache.redis = AsyncMock()
    cache.redis.set = AsyncMock(return_value=False)
    bot = AsyncMock()

    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=3600)
    result = await notifier.notify_if_hot({"lead_id": 1, "score": 90, "session_id": "s1"})

    assert result is False
    bot.send_message.assert_not_awaited()


async def test_notifier_returns_false_on_missing_fields():
    """Return False when required fields are missing."""
    cache = AsyncMock()
    bot = AsyncMock()

    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=3600)
    result = await notifier.notify_if_hot({"score": 90})

    assert result is False
    bot.send_message.assert_not_awaited()


async def test_notifier_handles_non_numeric_score_without_crashing():
    """Invalid score payload should not crash notification flow."""
    cache = AsyncMock()
    cache.redis = None
    bot = AsyncMock()
    notifier = HotLeadNotifier(bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=3600)

    result = await notifier.notify_if_hot({"lead_id": 1, "score": "high", "session_id": "s1"})

    assert result is True
    bot.send_message.assert_awaited_once()
    assert "score=0" in bot.send_message.await_args.kwargs["text"]



import pytest


class TestHotLeadNotifierObserveInstrumentation:
    """Tests for @observe instrumentation on HotLeadNotifier.notify_if_hot (#1663).

    Contract: notify_if_hot must be wrapped with @observe so each notification
    attempt produces a named Langfuse span. Curated update_current_span calls
    record only {lead_id, score, threshold} as input and {notified} as output.
    Full payload dicts (which may contain phone/email/session metadata) MUST
    NOT be captured.
    """

    @staticmethod
    def _patched_lf(monkeypatch: pytest.MonkeyPatch):
        from unittest.mock import MagicMock

        from telegram_bot.services import hot_lead_notifier as hln_mod

        mock_lf = MagicMock()
        monkeypatch.setattr(hln_mod, "get_client", lambda: mock_lf)
        return mock_lf

    @staticmethod
    def _disable_observe(monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib
        import sys

        from telegram_bot import observability as observability_mod

        def fake_observe(**_kwargs):
            def decorator(func):
                return func

            return decorator

        monkeypatch.setattr(observability_mod, "observe", fake_observe)
        sys.modules.pop("telegram_bot.services.hot_lead_notifier", None)
        importlib.import_module("telegram_bot.services.hot_lead_notifier")

    def test_module_imports_observe_and_get_client(self):
        """Module wires the Langfuse decorator + client accessor (#1663 contract)."""
        from telegram_bot.services import hot_lead_notifier as hln_mod

        assert hasattr(hln_mod, "observe"), (
            "telegram_bot.services.hot_lead_notifier must import `observe`"
        )
        assert hasattr(hln_mod, "get_client"), (
            "telegram_bot.services.hot_lead_notifier must import `get_client`"
        )

    def test_observe_decorator_applied_with_correct_kwargs(self, monkeypatch):
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
        sys.modules.pop("telegram_bot.services.hot_lead_notifier", None)
        importlib.import_module("telegram_bot.services.hot_lead_notifier")

        sync_calls = [c for c in captured if c.get("name") == "job-hot-lead-notify"]
        assert len(sync_calls) == 1, (
            f"Expected exactly one @observe(name='job-hot-lead-notify', ...). "
            f"Captured: {captured}"
        )
        kwargs = sync_calls[0]
        assert kwargs.get("capture_input") is False
        assert kwargs.get("capture_output") is False

    async def test_input_payload_is_curated_lead_score_threshold_only(self, monkeypatch):
        """Span input must record curated keys (lead_id, score, threshold) only."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        cache = AsyncMock()
        cache.redis = AsyncMock()
        cache.redis.set = AsyncMock(return_value=True)
        bot = AsyncMock()
        notifier = HotLeadNotifier(
            bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=60
        )

        # Payload includes a "secret" PII-like field that MUST NOT leak into spans.
        await notifier.notify_if_hot(
            {
                "lead_id": 77,
                "score": 88,
                "session_id": "chat-abc",
                "threshold": 70,
                "phone": "+380501112233",
            }
        )

        input_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list
            if "input" in c.kwargs
        ]
        assert len(input_calls) >= 1, "update_current_span(input=...) was never called"
        captured_input = input_calls[0]["input"]
        assert isinstance(captured_input, dict)
        assert captured_input.get("lead_id") == 77
        assert captured_input.get("score") == 88
        assert captured_input.get("threshold") == 70
        # PII must NOT appear in span input.
        assert "phone" not in captured_input
        assert "+380501112233" not in str(captured_input)
        # session_id is acceptable elsewhere but must not be captured here per audit
        # (curated keys are exactly: lead_id, score, threshold).
        assert set(captured_input.keys()) <= {"lead_id", "score", "threshold"}

    async def test_output_payload_records_notified_bool(self, monkeypatch):
        """Span output must record {'notified': bool}."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        cache = AsyncMock()
        cache.redis = AsyncMock()
        cache.redis.set = AsyncMock(return_value=True)
        bot = AsyncMock()
        notifier = HotLeadNotifier(
            bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=60
        )

        result = await notifier.notify_if_hot(
            {"lead_id": 1, "score": 90, "session_id": "s1", "threshold": 70}
        )

        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list
            if "output" in c.kwargs
        ]
        assert len(output_calls) >= 1, "update_current_span(output=...) was never called"
        captured_output = output_calls[-1]["output"]
        assert isinstance(captured_output, dict)
        assert captured_output.get("notified") is True
        assert result is True

    async def test_output_records_notified_false_when_deduped(self, monkeypatch):
        """When deduped, span output must record notified=False."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        cache = AsyncMock()
        cache.redis = AsyncMock()
        cache.redis.set = AsyncMock(return_value=False)  # deduped
        bot = AsyncMock()
        notifier = HotLeadNotifier(
            bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=60
        )

        result = await notifier.notify_if_hot(
            {"lead_id": 1, "score": 90, "session_id": "s1", "threshold": 70}
        )

        assert result is False
        output_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list
            if "output" in c.kwargs
        ]
        assert len(output_calls) >= 1
        assert output_calls[-1]["output"].get("notified") is False

    async def test_exception_path_records_error_level_and_reraises(self, monkeypatch):
        """On exception, update_current_span(level='ERROR', ...) and re-raise."""
        self._disable_observe(monkeypatch)
        mock_lf = self._patched_lf(monkeypatch)

        from telegram_bot.services.hot_lead_notifier import HotLeadNotifier

        cache = AsyncMock()
        cache.redis = AsyncMock()
        cache.redis.set = AsyncMock(return_value=True)
        bot = AsyncMock()
        bot.send_message = AsyncMock(side_effect=RuntimeError("Telegram down"))
        notifier = HotLeadNotifier(
            bot=bot, cache=cache, manager_ids=[1], dedupe_ttl_sec=60
        )

        with pytest.raises(RuntimeError, match="Telegram down"):
            await notifier.notify_if_hot(
                {"lead_id": 1, "score": 90, "session_id": "s1", "threshold": 70}
            )

        error_calls = [
            c.kwargs for c in mock_lf.update_current_span.call_args_list
            if c.kwargs.get("level") == "ERROR"
        ]
        assert len(error_calls) >= 1, (
            "Failure path must call update_current_span(level='ERROR', ...)"
        )
        status = error_calls[0].get("status_message", "")
        assert "Telegram down" in status
        assert len(status) <= 220
