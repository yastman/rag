"""Structured runtime event writer.

Emits compact JSONL to daily files under ``logs/runtime_events/YYYY-MM-DD.jsonl``.
Disabled by default (``RUNTIME_EVENTS_ENABLED=0``) and performs no I/O when off.

This module is intentionally dependency-free (stdlib only).
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from telegram_bot.runtime_events_config import RuntimeEventsConfig


logger = logging.getLogger(__name__)

_BANNED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
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
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Single structured runtime event."""

    ts: str
    event_type: str
    severity: str
    session_id: str | None
    source_file: str
    function: str
    line: int | None
    message: str
    payload: dict[str, Any] | None

    def to_json(self) -> str:
        """Serialize to compact JSON (single line)."""
        return json.dumps(asdict(self), ensure_ascii=False, default=str, separators=(",", ":"))


class _NoOpWriter:
    """Writer substitute used when runtime events are disabled."""

    def append(self, event: RuntimeEvent | None) -> None:
        """No-op: do nothing."""
        return

    def _scrub_payload(self, payload: Any) -> Any:
        """No-op scrubbing: return payload unchanged."""
        return payload


class RuntimeEventWriter:
    """Appends :class:`RuntimeEvent` instances as JSONL lines."""

    def __init__(self, config: RuntimeEventsConfig) -> None:
        self._config = config
        self._dir = Path(config.dir)

    def _current_path(self) -> Path:
        """Return the JSONL file path for the current UTC day."""
        today = date.today().isoformat()
        return self._dir / f"{today}.jsonl"

    def _scrub_payload(self, payload: Any) -> Any:
        """Recursively redact banned keys from *payload*.

        Returns the scrubbed structure.  Non-dict payloads are returned
        unchanged so that the writer never crashes on unexpected input.
        """
        if payload is None:
            return None
        if isinstance(payload, dict):
            result: dict[str, Any] = {}
            for key, value in payload.items():
                if key in _BANNED_PAYLOAD_KEYS:
                    result[key] = "<redacted>"
                elif isinstance(value, dict):
                    result[key] = self._scrub_payload(value)
                elif isinstance(value, list):
                    result[key] = [self._scrub_payload(item) for item in value]
                else:
                    result[key] = value
            return result
        if isinstance(payload, list):
            return [self._scrub_payload(item) for item in payload]
        return payload

    def append(self, event: RuntimeEvent | None) -> None:
        """Serialize *event* and append it to today's JSONL file.

        Write failures are caught and logged; they are never re-raised.
        """
        if event is None or not self._config.enabled:
            return
        try:
            scrubbed_payload = self._scrub_payload(event.payload)
            # Build a new event with scrubbed payload so the original stays immutable
            event = RuntimeEvent(
                ts=event.ts,
                event_type=event.event_type,
                severity=event.severity,
                session_id=event.session_id,
                source_file=event.source_file,
                function=event.function,
                line=event.line,
                message=event.message,
                payload=scrubbed_payload,
            )
            line = event.to_json() + "\n"
            path = self._current_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", errors="replace") as fh:
                fh.write(line)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to append runtime event: %s", exc)


# Module-level singleton cache
_writer_instance: RuntimeEventWriter | _NoOpWriter | None = None


def _get_writer() -> RuntimeEventWriter | _NoOpWriter:
    """Return the cached writer instance, creating it if necessary."""
    global _writer_instance
    if _writer_instance is None:
        cfg = RuntimeEventsConfig()
        _writer_instance = RuntimeEventWriter(cfg) if cfg.enabled else _NoOpWriter()
    return _writer_instance


def _reset_writer() -> None:
    """Clear the cached writer so the next call re-reads env vars.

    Intended for tests only.
    """
    global _writer_instance
    _writer_instance = None


def emit_runtime_event(
    *,
    event_type: str,
    severity: str,
    source_file: str,
    function: str,
    message: str,
    payload: dict[str, Any] | None = None,
    session_id: str | None = None,
    line: int | None = None,
) -> None:
    """Emit a structured runtime event.

    This helper is the primary API for instrumentation points.  It builds a
    :class:`RuntimeEvent`, scrubs the payload, and appends it to today's
    JSONL file.  When runtime events are disabled this is a no-op.

    Any failure during write is logged via standard Python logging and is
    never raised to the caller.
    """
    writer = _get_writer()
    event = RuntimeEvent(
        ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        event_type=event_type,
        severity=severity,
        session_id=session_id,
        source_file=source_file,
        function=function,
        line=line,
        message=message,
        payload=payload,
    )
    writer.append(event)
