"""Contract test for issue #2058 — /metrics admin command uses Prometheus.

Slice 1/2 of #2058 rewrites the bot's ``/metrics`` admin command in
``telegram_bot/handlers/command_handlers.py::cmd_metrics`` to emit the
SDK-native :func:`prometheus_client.generate_latest` text format. The
deprecated rolling-window dump
(``PipelineMetrics.get().format_text()``) is no longer the source of
truth for that command.

Class removal (the rest of #2058 acceptance) is a follow-up slice that
must migrate ~7 remaining ``PipelineMetrics.get()`` call-sites and a
batch of unit tests; locking the admin path here protects the user-
facing surface independently of that work.

This contract enforces:

1. ``cmd_metrics`` calls :func:`prometheus_client.generate_latest`.
2. ``cmd_metrics`` does not invoke the deprecated
   ``PipelineMetrics.format_text()`` rolling-window dump.
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


def test_cmd_metrics_calls_generate_latest() -> None:
    body = _cmd_metrics_body()
    assert "generate_latest(" in body, (
        "cmd_metrics() must call prometheus_client.generate_latest(...) "
        "to emit the SDK-native text format (issue #2058 slice 1/2)."
    )


def test_cmd_metrics_does_not_use_deprecated_format_text() -> None:
    body = _cmd_metrics_body()
    assert "format_text" not in body, (
        "cmd_metrics() must not call the deprecated "
        "PipelineMetrics.format_text() rolling-window dump (issue #2058)."
    )
