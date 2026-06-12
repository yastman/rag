"""Contract: simplification core live gate stays on the protected core path.

The product simplification plan makes ``make e2e-core-live`` the reliability
gate for the assistant core. Optional runtime surfaces such as Telegram,
voice, mini-app, k8s, and Langfuse diagnostics must not become prerequisites
for that gate.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"

CORE_LIVE_TARGETS = ("e2e-core-live", "e2e-core-live-real-llm")
CORE_TEST_PATH = "tests/e2e/test_core_live_ingest_answer.py"
CORE_TEST_VARIABLE = "CORE_LIVE_TEST_PATH"
OPTIONAL_SURFACE_TOKENS = (
    "e2e-telegram",
    "telegram",
    "telethon",
    "voice",
    "livekit",
    "mini_app",
    "k8s",
    "langfuse",
)


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_body(text: str, target: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(target)}:.*?\n((?:\t.*\n|@\$\(.+\).*?\n|[ \t].*\n|\\\n)*)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    assert match is not None, f"Makefile must define {target!r}"

    body_lines: list[str] = []
    for line in text[match.start() :].splitlines()[1:]:
        if line and not line.startswith(("\t", " ", "\\")):
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def test_core_live_targets_exist_and_run_core_e2e_file() -> None:
    text = _makefile_text()
    assert f"{CORE_TEST_VARIABLE} := {CORE_TEST_PATH}" in text
    for target in CORE_LIVE_TARGETS:
        body = _target_body(text, target)
        assert "$(CORE_LIVE_PYTEST)" in body, (
            f"{target} must run the shared protected core E2E command"
        )
        assert "requires_services" in text, f"{target} must keep the live-service marker gate"


def test_core_live_targets_do_not_require_optional_surfaces() -> None:
    text = _makefile_text()
    for target in CORE_LIVE_TARGETS:
        body = _target_body(text, target)
        normalized = body.lower()
        offenders = [token for token in OPTIONAL_SURFACE_TOKENS if token.lower() in normalized]
        assert not offenders, (
            f"{target} must stay on the protected assistant-core path and not require "
            f"optional surfaces. Offending tokens: {offenders}"
        )


def test_core_live_real_llm_target_is_explicit_opt_in() -> None:
    body = _target_body(_makefile_text(), "e2e-core-live-real-llm")

    assert "E2E_CORE_REAL_LLM=1" in body
    assert "LLM_MODEL" in body
    assert "LLM_API_KEY" in body
    assert "OPENAI_API_KEY" in body


def test_core_live_targets_use_no_sync_pytest_command() -> None:
    text = _makefile_text()

    assert "CORE_LIVE_PYTEST := $(UV_RUN_NO_SYNC) pytest $(CORE_LIVE_TEST_PATH)" in text
