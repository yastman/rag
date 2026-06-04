"""Contract: live core E2E is not part of fast PR/local gates.

The simplification plan keeps fast PR validation deterministic and service-free.
``make e2e-core-live`` is the protected product live gate for release/nightly or
manual validation, not a dependency of local PR readiness or pull-request CI.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

FAST_LOCAL_TARGETS = (
    "local-pr-ready",
    "check",
    "check-frozen",
    "candidate-check",
    "test",
    "test-unit",
)
LIVE_GATE_TOKENS = ("e2e-core-live", "E2E_CORE_REAL_LLM", "requires_services")


def _target_body(text: str, target: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t.*\n|[ \t].*\n|\\\n)*)",
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


def test_fast_local_targets_do_not_run_live_core_e2e() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")

    for target in FAST_LOCAL_TARGETS:
        body = _target_body(text, target)
        offenders = [token for token in LIVE_GATE_TOKENS if token in body]
        assert not offenders, (
            f"{target} is a fast/local PR gate and must not run live-service E2E. "
            f"Offending tokens: {offenders}"
        )


def test_pull_request_ci_workflow_does_not_run_live_core_e2e() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in text, "ci.yml must remain a PR workflow"
    offenders = [token for token in LIVE_GATE_TOKENS if token in text]
    assert not offenders, (
        "pull_request CI must stay deterministic and service-free; live core E2E "
        f"belongs to release/nightly/manual validation. Offending tokens: {offenders}"
    )
