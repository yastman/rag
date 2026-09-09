"""Regression coverage for GitHub CodeQL security alerts.

Only real behavior regressions belong here. The historical substring
scanners that used to live in this module (Qdrant API-key fragments,
raw phone placeholders) were removed in #3402: source-level leak
detection is owned natively by CodeQL (security-extended) and the
Gitleaks CI/pre-commit scans, while runtime log privacy is owned by the
canary-based behavior contract in
tests/contract/test_log_privacy_contract.py (#3356).
"""

from __future__ import annotations


def test_e2e_report_template_uses_autoescape() -> None:
    """HTML report rendering must use a Jinja environment with autoescape."""
    from scripts.e2e.report_generator import build_html_template

    template = build_html_template()

    assert template.environment.autoescape is True
