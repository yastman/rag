"""Contract: trace/Langfuse checks are optional diagnostics for simplification.

Product reliability is gated by ``make e2e-core-live``. Langfuse and trace
validation targets may remain useful diagnostics, but they must not be named or
wired as required release/PR gates for the simplified assistant core.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

OPTIONAL_TRACE_TARGETS = (
    "e2e-test-traces",
    "e2e-test-traces-core",
    "langfuse-latest-trace-audit",
)
OBSOLETE_TRACE_TARGETS = (
    "validate-traces",
    "validate-traces-fast",
    "validate-voice-traces",
    "langfuse-latency-audit",
)
REQUIRED_WORDS = ("required", "must", "gate")
TRACE_GATE_TOKENS = (
    "e2e-test-traces",
    "E2E_VALIDATE_LANGFUSE",
)


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_header(text: str, target: str) -> str:
    match = re.search(rf"^{re.escape(target)}:[^\n]*$", text, re.MULTILINE)
    assert match is not None, f"Makefile must define {target!r}"
    return match.group(0)


def _target_body(text: str, target: str) -> str:
    match = re.search(rf"^{re.escape(target)}:[^\n]*$", text, re.MULTILINE)
    assert match is not None, f"Makefile must define {target!r}"
    body_lines: list[str] = []
    for line in text[match.end() :].splitlines():
        if line and not line.startswith(("\t", " ", "\\")):
            break
        body_lines.append(line)
    return "\n".join(body_lines)



def test_obsolete_trace_targets_are_removed() -> None:
    text = _makefile_text()

    for target in OBSOLETE_TRACE_TARGETS:
        assert not re.search(rf"^{re.escape(target)}:", text, re.MULTILINE), (
            f"{target} should not remain as a Makefile target"
        )


def test_trace_targets_are_named_optional_diagnostics() -> None:
    text = _makefile_text()

    for target in OPTIONAL_TRACE_TARGETS:
        header = _target_header(text, target)
        assert "Optional diagnostic" in header, (
            f"{target} must be labelled as an optional diagnostic in Makefile help"
        )


def test_trace_targets_are_not_described_as_required_gates() -> None:
    text = _makefile_text()

    for target in OPTIONAL_TRACE_TARGETS:
        header = _target_header(text, target)
        body = _target_body(text, target)
        combined = f"{header}\n{body}".lower()
        offenders = [word for word in REQUIRED_WORDS if word in combined]
        assert not offenders, (
            f"{target} is optional diagnostics and must not be described as a "
            f"required gate. Offending words: {offenders}"
        )


def test_pr_ci_does_not_run_trace_diagnostics() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")

    offenders = [token for token in TRACE_GATE_TOKENS if token in text]
    assert not offenders, (
        "pull_request CI must not run Langfuse/trace diagnostics as mandatory gates. "
        f"Offending tokens: {offenders}"
    )


def test_core_live_gate_does_not_enable_langfuse_validation() -> None:
    text = _makefile_text()

    body = _target_body(text, "e2e-core-live")
    assert "E2E_VALIDATE_LANGFUSE" not in body
    assert "langfuse" not in body.lower()
