"""Unit tests for runtime event schema, writer, and config.

Tests cover:
- RuntimeEvent schema serialization and validation
- RuntimeEventWriter append behavior and daily rotation
- Config env parsing (enabled, dir, max_age_days)
- Disabled/no-op mode
- PII scrubbing of banned keys
- Write-failure resilience
- emit_runtime_event() helper
"""

import json
import logging
from datetime import UTC
from datetime import datetime as dt
from pathlib import Path
from unittest.mock import patch

import pytest

from telegram_bot.runtime_events import (
    RuntimeEvent,
    RuntimeEventWriter,
    _get_writer,
    emit_runtime_event,
)
from telegram_bot.runtime_events_config import RuntimeEventsConfig


class TestRuntimeEventSchema:
    """Test RuntimeEvent dataclass creation and serialization."""

    def test_event_creation_with_all_fields(self):
        """RuntimeEvent can be created with all fields."""
        event = RuntimeEvent(
            ts="2026-05-01T12:34:56.789Z",
            event_type="integration.fallback",
            severity="warning",
            session_id="sess-123",
            source_file="telegram_bot.integrations.prompt_manager",
            function="_fetch_prompt_core",
            line=42,
            message="Langfuse prompt fetch failed",
            payload={"prompt_name": "test"},
        )
        assert event.event_type == "integration.fallback"
        assert event.severity == "warning"
        assert event.session_id == "sess-123"
        assert event.line == 42

    def test_event_creation_with_none_fields(self):
        """RuntimeEvent accepts None for optional fields."""
        event = RuntimeEvent(
            ts="2026-05-01T12:34:56.789Z",
            event_type="search.empty_results",
            severity="info",
            session_id=None,
            source_file=__name__,
            function="test",
            line=None,
            message="No results",
            payload=None,
        )
        assert event.session_id is None
        assert event.line is None
        assert event.payload is None

    def test_event_to_json_compact(self):
        """Serialization produces compact JSON with ensure_ascii=False."""
        event = RuntimeEvent(
            ts="2026-05-01T12:34:56.789Z",
            event_type="test.event",
            severity="debug",
            session_id=None,
            source_file="test_module",
            function="test_fn",
            line=None,
            message="hello world",
            payload={"key": "value"},
        )
        raw = event.to_json()
        assert isinstance(raw, str)
        # Compact: no extra spaces after commas or colons
        assert ", " not in raw
        parsed = json.loads(raw)
        assert parsed["event_type"] == "test.event"
        assert parsed["message"] == "hello world"
        assert parsed["payload"]["key"] == "value"

    def test_event_immutability(self):
        """RuntimeEvent is frozen and cannot be modified."""
        event = RuntimeEvent(
            ts="2026-05-01T12:34:56.789Z",
            event_type="test.event",
            severity="debug",
            session_id=None,
            source_file="mod",
            function="fn",
            line=None,
            message="m",
            payload=None,
        )
        with pytest.raises(AttributeError):
            event.severity = "error"


class TestRuntimeEventsConfig:
    """Test env-based configuration."""

    def test_default_config_disabled(self, monkeypatch):
        """Default config has enabled=False and safe defaults."""
        monkeypatch.delenv("RUNTIME_EVENTS_ENABLED", raising=False)
        monkeypatch.delenv("RUNTIME_EVENTS_DIR", raising=False)
        monkeypatch.delenv("RUNTIME_EVENTS_MAX_AGE_DAYS", raising=False)
        cfg = RuntimeEventsConfig()
        assert cfg.enabled is False
        assert cfg.dir == "logs/runtime_events"
        assert cfg.max_age_days is None

    def test_enabled_from_env(self, monkeypatch):
        """RUNTIME_EVENTS_ENABLED=1 enables events."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "1")
        cfg = RuntimeEventsConfig()
        assert cfg.enabled is True

    def test_disabled_explicit_zero(self, monkeypatch):
        """RUNTIME_EVENTS_ENABLED=0 disables events."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "0")
        cfg = RuntimeEventsConfig()
        assert cfg.enabled is False

    def test_custom_dir(self, monkeypatch):
        """RUNTIME_EVENTS_DIR overrides default directory."""
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", "/tmp/events")
        cfg = RuntimeEventsConfig()
        assert cfg.dir == "/tmp/events"

    def test_max_age_days(self, monkeypatch):
        """RUNTIME_EVENTS_MAX_AGE_DAYS parsed as int."""
        monkeypatch.setenv("RUNTIME_EVENTS_MAX_AGE_DAYS", "7")
        cfg = RuntimeEventsConfig()
        assert cfg.max_age_days == 7


class TestRuntimeEventWriterRotation:
    """Test file rotation and append behavior."""

    def test_daily_file_path(self, tmp_path):
        """Writer selects file based on current UTC date."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        today = dt.now(UTC).date().isoformat()
        expected = tmp_path / f"{today}.jsonl"
        assert writer._current_path() == expected

    def test_daily_file_path_uses_utc_date(self, tmp_path):
        """Writer uses UTC date for daily rotation, not local ``date.today()``."""
        from datetime import datetime
        from unittest.mock import MagicMock

        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)

        # Fixed UTC datetime: 2026-12-25T23:59Z (UTC date = Dec 25)
        fixed_dt = datetime(2026, 12, 25, 23, 59, tzinfo=UTC)
        mock_dt_class = MagicMock()
        mock_dt_class.now.return_value = fixed_dt

        with patch("telegram_bot.runtime_events.datetime", mock_dt_class):
            path = writer._current_path()

        assert path == tmp_path / "2026-12-25.jsonl"

    def test_append_creates_file_and_directory(self, tmp_path):
        """append() creates parent directories and file if missing."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path / "sub" / "dir"))
        writer = RuntimeEventWriter(cfg)
        event = RuntimeEvent(
            ts="2026-05-01T12:00:00.000Z",
            event_type="test.append",
            severity="info",
            session_id=None,
            source_file=__name__,
            function="test_append",
            line=1,
            message="appended",
            payload=None,
        )
        writer.append(event)
        assert writer._current_path().exists()
        lines = writer._current_path().read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event_type"] == "test.append"

    def test_append_multiple_lines(self, tmp_path):
        """Multiple appends result in multiple JSONL lines."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        for i in range(3):
            event = RuntimeEvent(
                ts=f"2026-05-01T12:00:0{i}.000Z",
                event_type="test.multi",
                severity="info",
                session_id=None,
                source_file=__name__,
                function="test_multi",
                line=i,
                message=f"line {i}",
                payload=None,
            )
            writer.append(event)
        lines = writer._current_path().read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3


class TestRuntimeEventWriterScrubbing:
    """Test PII scrubbing in payloads."""

    @pytest.mark.parametrize(
        "banned_key",
        [
            "user_id",
            "telegram_id",
            "phone",
            "email",
            "token",
            "password",
            "secret",
            "api_key",
            "query",
            "prompt",
            "traceback",
            "connection_string",
        ],
    )
    def test_scrubbing_banned_keys(self, banned_key, tmp_path):
        """Banned keys are replaced with <redacted>."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        payload = {banned_key: "sensitive-value", "safe_key": "safe-value"}
        scrubbed = writer._scrub_payload(payload)
        assert scrubbed[banned_key] == "<redacted>"
        assert scrubbed["safe_key"] == "safe-value"

    @pytest.mark.parametrize(
        "banned_key",
        [
            # Same-case variants (should already work, but verify)
            "user_id",
            "phone",
            "email",
            "api_key",
            # Mixed-case and upper-case variants (the fix ensures these are caught)
            "USER_ID",
            "User_Id",
            "PHONE",
            "Phone",
            "EMAIL",
            "Email",
            "API_KEY",
            "Api_Key",
            "TOKEN",
            "Token",
            "PASSWORD",
            "Password",
            "SECRET",
            "Secret",
            "TELEGRAM_ID",
            "Telegram_Id",
            "QUERY",
            "Query",
            "PROMPT",
            "Prompt",
            "TRACEBACK",
            "Traceback",
            "CONNECTION_STRING",
            "Connection_String",
        ],
    )
    def test_scrubbing_banned_keys_case_insensitive(self, banned_key, tmp_path):
        """Banned keys are matched case-insensitively (API_KEY, Phone, userId etc.)."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        payload = {banned_key: "sensitive-value", "safe_key": "safe-value"}
        scrubbed = writer._scrub_payload(payload)
        assert scrubbed[banned_key] == "<redacted>", f"Expected key {banned_key!r} to be redacted"
        assert scrubbed["safe_key"] == "safe-value"

    def test_scrubbing_nested_dict(self, tmp_path):
        """Scrubbing recurses into nested dictionaries."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        payload = {"outer": {"user_id": "123", "name": "ok"}, "safe": "top"}
        scrubbed = writer._scrub_payload(payload)
        assert scrubbed["outer"]["user_id"] == "<redacted>"
        assert scrubbed["outer"]["name"] == "ok"
        assert scrubbed["safe"] == "top"

    def test_scrubbing_nested_dict_case_insensitive(self, tmp_path):
        """Case-insensitive scrubbing recurses into nested dictionaries."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        payload = {"outer": {"USER_ID": "123", "name": "ok"}, "safe": "top"}
        scrubbed = writer._scrub_payload(payload)
        assert scrubbed["outer"]["USER_ID"] == "<redacted>"
        assert scrubbed["outer"]["name"] == "ok"
        assert scrubbed["safe"] == "top"

    def test_scrubbing_list_inside_dict(self, tmp_path):
        """Scrubbing handles lists nested inside dicts."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        payload = {"items": [{"phone": "123"}, {"email": "a@b.c"}]}
        scrubbed = writer._scrub_payload(payload)
        assert scrubbed["items"][0]["phone"] == "<redacted>"
        assert scrubbed["items"][1]["email"] == "<redacted>"

    def test_scrubbing_none_payload(self, tmp_path):
        """None payload returns None."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        assert writer._scrub_payload(None) is None

    def test_scrubbing_non_dict_payload(self, tmp_path):
        """Non-dict payloads are wrapped or handled safely."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        # The plan says payload is dict[str, Any] | None, but we should be defensive
        result = writer._scrub_payload("raw-string")
        assert result == "raw-string"

    def test_scrubbing_applied_on_append(self, tmp_path):
        """append() stores scrubbed payload, not original."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        event = RuntimeEvent(
            ts="2026-05-01T12:00:00.000Z",
            event_type="test.scrub",
            severity="info",
            session_id=None,
            source_file=__name__,
            function="test_scrub_append",
            line=1,
            message="scrub test",
            payload={"user_id": "12345", "prompt_name": "ok"},
        )
        writer.append(event)
        lines = writer._current_path().read_text(encoding="utf-8").strip().splitlines()
        parsed = json.loads(lines[0])
        assert parsed["payload"]["user_id"] == "<redacted>"
        assert parsed["payload"]["prompt_name"] == "ok"


class TestRuntimeEventWriterDisabled:
    """Test no-op behavior when disabled."""

    def test_disabled_writer_no_file_created(self, tmp_path):
        """Disabled writer does not create files."""
        cfg = RuntimeEventsConfig(enabled=False, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        event = RuntimeEvent(
            ts="2026-05-01T12:00:00.000Z",
            event_type="test.disabled",
            severity="info",
            session_id=None,
            source_file=__name__,
            function="test_disabled",
            line=1,
            message="should not appear",
            payload=None,
        )
        writer.append(event)
        # No files should be created in tmp_path
        assert list(tmp_path.iterdir()) == []

    def test_disabled_writer_append_is_no_op(self, tmp_path):
        """append() returns quickly when disabled."""
        cfg = RuntimeEventsConfig(enabled=False, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        # Should not raise
        writer.append(None)  # type: ignore[arg-type]


class TestRuntimeEventWriterResilience:
    """Test write-failure handling."""

    def test_append_failure_logged_not_raised(self, tmp_path, caplog):
        """IO failures during append are logged, not raised."""
        cfg = RuntimeEventsConfig(enabled=True, dir=str(tmp_path))
        writer = RuntimeEventWriter(cfg)
        event = RuntimeEvent(
            ts="2026-05-01T12:00:00.000Z",
            event_type="test.resilience",
            severity="error",
            session_id=None,
            source_file=__name__,
            function="test_resilience",
            line=1,
            message="fail test",
            payload=None,
        )
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            with caplog.at_level(logging.WARNING, logger="telegram_bot.runtime_events"):
                writer.append(event)
        assert "disk full" in caplog.text or "Failed to append" in caplog.text


class TestEmitRuntimeEventHelper:
    """Test high-level emit_runtime_event() helper."""

    def test_emit_creates_event_and_appends(self, tmp_path, monkeypatch):
        """emit_runtime_event() builds a RuntimeEvent and appends it."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "1")
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", str(tmp_path))
        # Reset singleton so it picks up new env
        from telegram_bot.runtime_events import _reset_writer

        _reset_writer()
        try:
            emit_runtime_event(
                event_type="integration.fallback",
                severity="warning",
                source_file=__name__,
                function="_fetch_prompt_core",
                message="Langfuse prompt fetch failed, using fallback",
                payload={"prompt_name": "name", "exception_type": "TimeoutError"},
            )
            today = dt.now(UTC).date().isoformat()
            path = tmp_path / f"{today}.jsonl"
            assert path.exists()
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            parsed = json.loads(lines[0])
            assert parsed["event_type"] == "integration.fallback"
            assert parsed["severity"] == "warning"
            assert parsed["source_file"] == __name__
            assert parsed["function"] == "_fetch_prompt_core"
            assert parsed["message"] == "Langfuse prompt fetch failed, using fallback"
            assert parsed["payload"]["prompt_name"] == "name"
            assert parsed["payload"]["exception_type"] == "TimeoutError"
            assert parsed["ts"] is not None
        finally:
            _reset_writer()

    def test_emit_disabled_is_no_op(self, tmp_path, monkeypatch):
        """emit_runtime_event() does nothing when disabled."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "0")
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", str(tmp_path))
        from telegram_bot.runtime_events import _reset_writer

        _reset_writer()
        try:
            emit_runtime_event(
                event_type="test.disabled",
                severity="info",
                source_file=__name__,
                function="test",
                message="noop",
                payload=None,
            )
            assert list(tmp_path.iterdir()) == []
        finally:
            _reset_writer()

    def test_emit_scrubs_payload(self, tmp_path, monkeypatch):
        """emit_runtime_event() scrubs payload before writing."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "1")
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", str(tmp_path))
        from telegram_bot.runtime_events import _reset_writer

        _reset_writer()
        try:
            emit_runtime_event(
                event_type="test.scrub",
                severity="info",
                source_file=__name__,
                function="test",
                message="scrub",
                payload={"user_id": "123", "safe": "ok"},
            )
            today = dt.now(UTC).date().isoformat()
            path = tmp_path / f"{today}.jsonl"
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            parsed = json.loads(lines[0])
            assert parsed["payload"]["user_id"] == "<redacted>"
            assert parsed["payload"]["safe"] == "ok"
        finally:
            _reset_writer()

    def test_emit_failure_logged(self, tmp_path, monkeypatch, caplog):
        """emit_runtime_event() logs failures via std logging."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "1")
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", str(tmp_path))
        from telegram_bot.runtime_events import _reset_writer

        _reset_writer()
        try:
            with patch.object(Path, "open", side_effect=OSError("write fail")):
                with caplog.at_level(logging.WARNING, logger="telegram_bot.runtime_events"):
                    emit_runtime_event(
                        event_type="test.fail",
                        severity="error",
                        source_file=__name__,
                        function="test",
                        message="fail",
                        payload=None,
                    )
            assert "write fail" in caplog.text or "Failed to append" in caplog.text
        finally:
            _reset_writer()


class TestWriterSingleton:
    """Test module-level writer singleton behavior."""

    def test_get_writer_returns_same_instance(self, monkeypatch, tmp_path):
        """_get_writer() caches the writer instance."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "1")
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", str(tmp_path))
        from telegram_bot.runtime_events import _reset_writer

        _reset_writer()
        try:
            w1 = _get_writer()
            w2 = _get_writer()
            assert w1 is w2
        finally:
            _reset_writer()

    def test_get_writer_disabled_returns_noop(self, monkeypatch, tmp_path):
        """_get_writer() returns a noop writer when disabled."""
        monkeypatch.setenv("RUNTIME_EVENTS_ENABLED", "0")
        monkeypatch.setenv("RUNTIME_EVENTS_DIR", str(tmp_path))
        from telegram_bot.runtime_events import _reset_writer

        _reset_writer()
        try:
            writer = _get_writer()
            # Should not raise or create files
            writer.append(None)  # type: ignore[arg-type]
            assert list(tmp_path.iterdir()) == []
        finally:
            _reset_writer()
