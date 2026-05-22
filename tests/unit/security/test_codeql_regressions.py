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
        "tests/integration/test_basic_connection.py",
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
