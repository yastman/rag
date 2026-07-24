"""Regression coverage for GitHub CodeQL security alerts."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_qdrant_test_helpers_do_not_print_api_key_fragments() -> None:
    """Qdrant diagnostics may show presence, never API key suffixes."""
    checked_paths = [
        "tests/smoke/test_basic_connection.py",
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
