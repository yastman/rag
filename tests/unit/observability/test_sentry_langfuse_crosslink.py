"""Sentry <-> Langfuse cross-link contract (#2218).

When a Sentry event is captured inside an active Langfuse observation, the
event MUST automatically carry the Langfuse trace_id so on-call can pivot
in one click from Sentry incident → Langfuse trace → Loki logs.

The implementation extends the existing ``_make_before_send`` hook in
``src/observability_sentry.py`` (already running for PII redaction). After
PII scrub, it reads ``langfuse.get_client().get_current_trace_id()`` and
attaches:

* ``event["tags"]["langfuse_trace_id"]`` — searchable tag
* ``event["contexts"]["langfuse"]`` — structured context block with
  ``trace_id``, ``observation_id``, and a deep-link URL when
  ``LANGFUSE_HOST`` is configured.

Implementation notes (from Langfuse v4 SDK ``code_review.md`` via
Context7):

* ``get_current_trace_id()`` returns ``None`` when no Langfuse client is
  initialized — the hook tolerates that and just returns the event.
* The hook is wrapped in try/except: a failure to read the Langfuse client
  must never block a Sentry event from being captured.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def reset_observability_sentry() -> None:
    import src.observability_sentry as mod

    mod._reset_for_tests()
    yield
    mod._reset_for_tests()


class TestBeforeSendAttachesLangfuseTraceId:
    """``_make_before_send`` must attach Langfuse trace IDs to every event."""

    def test_event_carries_langfuse_trace_id_tag(self, reset_observability_sentry) -> None:
        import src.observability_sentry as mod

        fake_lf = MagicMock(name="LangfuseClient")
        fake_lf.get_current_trace_id.return_value = "abcdef1234567890abcdef1234567890"
        fake_lf.get_current_observation_id.return_value = "fedcba0987654321"

        with patch.object(mod, "_get_langfuse_client", return_value=fake_lf):
            before_send = mod._make_before_send()
            event: dict = {"event_id": "e1", "message": "boom"}
            result = before_send(event, hint=None)

        assert result is not None
        assert result["tags"]["langfuse_trace_id"] == ("abcdef1234567890abcdef1234567890")

    def test_event_carries_langfuse_context_block(self, reset_observability_sentry) -> None:
        import src.observability_sentry as mod

        fake_lf = MagicMock(name="LangfuseClient")
        fake_lf.get_current_trace_id.return_value = "trace-xyz"
        fake_lf.get_current_observation_id.return_value = "obs-456"

        with (
            patch.object(mod, "_get_langfuse_client", return_value=fake_lf),
            patch.dict("os.environ", {"LANGFUSE_HOST": "http://langfuse:3000"}),
        ):
            before_send = mod._make_before_send()
            event: dict = {"event_id": "e1"}
            result = before_send(event, hint=None)

        assert "contexts" in result
        ctx = result["contexts"]["langfuse"]
        assert ctx["trace_id"] == "trace-xyz"
        assert ctx["observation_id"] == "obs-456"
        assert ctx["url"] == "http://langfuse:3000/trace/trace-xyz"

    def test_event_unchanged_when_no_langfuse_client(self, reset_observability_sentry) -> None:
        """Without an initialized Langfuse client, no langfuse_* fields appear."""
        import src.observability_sentry as mod

        with patch.object(mod, "_get_langfuse_client", return_value=None):
            before_send = mod._make_before_send()
            event: dict = {"event_id": "e1", "message": "boom"}
            result = before_send(event, hint=None)

        assert result is not None
        assert "langfuse_trace_id" not in result.get("tags", {})
        assert "langfuse" not in result.get("contexts", {})

    def test_event_unchanged_when_no_active_trace(self, reset_observability_sentry) -> None:
        """When Langfuse client exists but no @observe is active, skip."""
        import src.observability_sentry as mod

        fake_lf = MagicMock(name="LangfuseClient")
        fake_lf.get_current_trace_id.return_value = None
        fake_lf.get_current_observation_id.return_value = None

        with patch.object(mod, "_get_langfuse_client", return_value=fake_lf):
            before_send = mod._make_before_send()
            event: dict = {"event_id": "e1"}
            result = before_send(event, hint=None)

        assert "langfuse_trace_id" not in result.get("tags", {})
        assert "langfuse" not in result.get("contexts", {})

    def test_hook_never_blocks_event_on_langfuse_error(self, reset_observability_sentry) -> None:
        """A failure to read Langfuse must not drop the Sentry event."""
        import src.observability_sentry as mod

        fake_lf = MagicMock(name="LangfuseClient")
        fake_lf.get_current_trace_id.side_effect = RuntimeError("Langfuse exploded")

        with patch.object(mod, "_get_langfuse_client", return_value=fake_lf):
            before_send = mod._make_before_send()
            event: dict = {"event_id": "e1", "message": "boom"}
            result = before_send(event, hint=None)

        # The event must still be returned (PII scrub may have run, that's fine).
        assert result is not None
        assert result["event_id"] == "e1"

    def test_pii_redaction_still_happens_when_langfuse_attaches(
        self, reset_observability_sentry
    ) -> None:
        """The Langfuse cross-link must run AFTER PII scrub, not replace it."""
        import src.observability_sentry as mod

        fake_lf = MagicMock(name="LangfuseClient")
        fake_lf.get_current_trace_id.return_value = "trace-42"
        fake_lf.get_current_observation_id.return_value = None

        with patch.object(mod, "_get_langfuse_client", return_value=fake_lf):
            before_send = mod._make_before_send()
            event: dict = {
                "event_id": "e1",
                "message": "User phone: +380501112233 was seen",
            }
            result = before_send(event, hint=None)

        assert result["tags"]["langfuse_trace_id"] == "trace-42"
        # PIIRedactor masks long digit sequences; phone must not appear verbatim.
        assert "+380501112233" not in result["message"]


class TestGetLangfuseClient:
    """``_get_langfuse_client`` must tolerate missing Langfuse SDK / no init."""

    def test_returns_none_when_langfuse_not_imported(self) -> None:
        import src.observability_sentry as mod

        # Simulate ImportError on langfuse import
        with patch.dict("sys.modules", {"langfuse": None}):
            client = mod._get_langfuse_client()
            assert client is None

    def test_returns_client_when_get_client_works(self) -> None:
        import src.observability_sentry as mod

        fake_client = MagicMock(name="LangfuseClient")

        with patch("langfuse.get_client", return_value=fake_client, create=True):
            client = mod._get_langfuse_client()
            assert client is fake_client
