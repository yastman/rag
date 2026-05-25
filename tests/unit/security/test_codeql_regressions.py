"""Regression coverage for GitHub CodeQL security alerts."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_qdrant_test_helpers_do_not_print_api_key_fragments() -> None:
    """Qdrant diagnostics may show presence, never API key suffixes."""
    checked_paths = [
        "tests/benchmark/test_colbert_rerank.py",
        "tests/benchmark/test_dbsf_colbert.py",
        "tests/smoke/test_basic_connection.py",
        "tests/integration/test_hybrid_search_sparse.py",
        "tests/integration/test_qdrant_read.py",
    ]

    for relative_path in checked_paths:
        source = _read(relative_path)
        assert "QDRANT_API_KEY[-10:]" not in source, relative_path
        assert "qdrant_api_key[-10:]" not in source, relative_path


def test_phone_collector_logs_do_not_include_raw_phone_placeholder() -> None:
    """Phone numbers belong in CRM payloads, not application log messages."""
    source = _read("telegram_bot/handlers/phone_collector.py")

    assert "phone=%s" not in source


def test_e2e_report_template_uses_autoescape() -> None:
    """HTML report rendering must use a Jinja environment with autoescape."""
    from scripts.e2e.report_generator import build_html_template

    template = build_html_template()

    assert template.environment.autoescape is True


@pytest.mark.asyncio
async def test_remote_log_does_not_emit_raw_user_payload(caplog: pytest.LogCaptureFixture) -> None:
    """Frontend log text is untrusted and must not be copied into backend logs."""
    pytest.importorskip("fastapi")

    from httpx import ASGITransport, AsyncClient

    from mini_app.api import app

    caplog.set_level(logging.INFO, logger="mini_app.api")
    raw_message = "line1\nERROR injected +380501234567"

    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "TEST"}, clear=False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/log",
                json={"level": "info", "message": raw_message, "data": {"phone": "+380501234567"}},
                headers={"X-Init-Data": "test-init-data"},
            )

    assert response.status_code == 200
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert raw_message not in rendered_logs
    assert "+380501234567" not in rendered_logs


def test_remote_log_handler_level_is_not_raw_user_controlled() -> None:
    """CodeQL #17: request.level must not be passed as a log format argument.

    The remote_log handler maps ``request.level`` through a validated
    constant lookup (_LEVEL_MAP).  The mapped integer level (e.g. ``lvl``)
    is safe, but CodeQL still flags the raw ``request.level`` string when
    it appears as a positional argument inside the ``logger.log`` call.
    This regression guard asserts that the ``logger.log`` call-site does
    not contain ``request.level``.
    """
    source = _read("mini_app/api.py")

    # Locate the logger call that contains the [REMOTE:] format tag
    fmt_idx = source.find("[REMOTE:")
    assert fmt_idx != -1, "Format string [REMOTE:] not found"

    # Find the enclosing logger.log(...) call
    log_start = source.rfind("logger.log", 0, fmt_idx)
    assert log_start != -1, "logger.log call before [REMOTE:] not found"

    paren_start = source.find("(", log_start)
    assert paren_start != -1, "Opening paren after logger.log not found"

    # Match the closing paren of logger.log(...)
    depth = 0
    paren_end = paren_start
    for j in range(paren_start, len(source)):
        if source[j] == "(":
            depth += 1
        elif source[j] == ")":
            depth -= 1
            if depth == 0:
                paren_end = j
                break

    # Arguments of the logger.log call
    log_call_body = source[paren_start + 1 : paren_end]

    assert "request.level" not in log_call_body, (
        "request.level must not be a log format argument inside logger.log (CodeQL #17). "
        "Use a constant-mapped level name derived from _LEVEL_MAP instead."
    )
