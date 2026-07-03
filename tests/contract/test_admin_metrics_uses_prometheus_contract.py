"""Contract test for issue #2058 — /metrics admin command uses structured logging.

#2058 originally planned to rewrite ``cmd_metrics`` to use Prometheus
``generate_latest``. That plan was superseded: in-process Prometheus was
disabled and the /metrics command was updated to direct operators to
structured JSON logs (``event=pipeline_latency``, ``event=pipeline_counter``)
instead of emitting Prometheus text format.

This contract enforces the current architecture:

1. ``cmd_metrics`` directs operators to structured JSON logs (not Prometheus).
2. ``cmd_metrics`` does not invoke the deprecated
   ``PipelineMetrics.format_text()`` rolling-window dump.
3. ``cmd_metrics`` does not call ``prometheus_client.generate_latest``
   (in-process Prometheus is disabled).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
COMMAND_HANDLERS = REPO / "telegram_bot" / "handlers" / "command_handlers.py"


def _cmd_metrics_body() -> str:
    text = COMMAND_HANDLERS.read_text(encoding="utf-8")
    match = re.search(
        r"async def cmd_metrics\(.*?\)(.*?)(?=^async def |^def |\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert match, "cmd_metrics() not found in telegram_bot/handlers/command_handlers.py"
    body = match.group(1)
    # Strip the function docstring so it doesn't false-match this contract
    # (the docstring legitimately *names* the deprecated symbols it replaces).
    return re.sub(r'""".*?"""', "", body, count=1, flags=re.DOTALL)


def test_cmd_metrics_directs_to_structured_logs() -> None:
    """cmd_metrics must respond with a message directing operators to structured logs.

    In-process Prometheus was disabled; the command now points operators to
    structured JSON log events (event=pipeline_latency, event=pipeline_counter).
    """
    body = _cmd_metrics_body()
    assert "message.answer(" in body, (
        "cmd_metrics() must call message.answer() to reply to the operator."
    )
    # The response must mention structured JSON logs or the log event names.
    assert any(
        token in body for token in ("structured", "pipeline_latency", "pipeline_counter", "JSON")
    ), (
        "cmd_metrics() must direct operators to structured JSON log events "
        "(event=pipeline_latency / event=pipeline_counter). "
        "In-process Prometheus /metrics is disabled."
    )


def test_cmd_metrics_does_not_use_deprecated_format_text() -> None:
    body = _cmd_metrics_body()
    assert "format_text" not in body, (
        "cmd_metrics() must not call the deprecated "
        "PipelineMetrics.format_text() rolling-window dump (issue #2058)."
    )


def test_cmd_metrics_does_not_call_generate_latest() -> None:
    """In-process Prometheus is disabled; generate_latest must not be called."""
    body = _cmd_metrics_body()
    assert "generate_latest(" not in body, (
        "cmd_metrics() must not call prometheus_client.generate_latest() — "
        "in-process Prometheus /metrics is disabled. "
        "Operators are directed to structured JSON logs instead."
    )
