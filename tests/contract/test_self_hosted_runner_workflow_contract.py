"""Contract: self-hosted runner verification artifacts for nightly-heavy.yml (#1531).

The ``.github/workflows/nightly-heavy.yml`` workflow runs heavy-tier tests
(``requires_extras``/``load``/``chaos``/``e2e``/``benchmark``) on a
self-hosted GitHub Actions runner. If the runner goes offline or its labels
drift, the nightly job silently queues forever or fails.

There is no in-repo way to query a runner registration from CI (admin scope
is needed). The mitigation is to ship operator-runnable artifacts that make
"is the runner alive?" cheap to verify and well-documented:

1. A diagnostic script ``scripts/check_self_hosted_runner.sh`` that calls
   the GitHub Actions runners API via ``gh``.
2. A runbook ``docs/runbooks/SELF_HOSTED_RUNNER.md`` that documents
   resource requirements, registration, verification, common failure modes,
   and the temporary-disable procedure.

This contract pins those artifacts so they cannot silently disappear and
cannot fall out of cross-link sync with the workflow file they describe.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly-heavy.yml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "SELF_HOSTED_RUNNER.md"
SCRIPT = REPO_ROOT / "scripts" / "check_self_hosted_runner.sh"


def test_nightly_heavy_workflow_exists() -> None:
    assert WORKFLOW.exists(), (
        f"Expected {WORKFLOW.relative_to(REPO_ROOT)} to exist; this contract "
        "covers the self-hosted runner that workflow depends on."
    )


def test_nightly_heavy_uses_self_hosted_runner() -> None:
    """Parse the workflow YAML and assert at least one job uses self-hosted."""
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = data.get("jobs") or {}
    assert jobs, "nightly-heavy.yml must define at least one job"

    runs_on_values: list[object] = []
    for job_def in jobs.values():
        if isinstance(job_def, dict) and "runs-on" in job_def:
            runs_on_values.append(job_def["runs-on"])

    assert runs_on_values, "no job in nightly-heavy.yml declares runs-on"

    def _is_self_hosted(value: object) -> bool:
        if isinstance(value, str):
            return value.strip() == "self-hosted"
        if isinstance(value, list):
            return any(
                isinstance(v, str) and v.strip() == "self-hosted" for v in value
            )
        return False

    assert any(_is_self_hosted(v) for v in runs_on_values), (
        "nightly-heavy.yml must keep at least one job pinned to "
        f"runs-on: self-hosted; got {runs_on_values!r}. The diagnostic "
        "script and runbook this contract guards exist precisely for that "
        "self-hosted dependency."
    )


def test_runbook_exists() -> None:
    assert RUNBOOK.exists(), (
        f"Expected runbook {RUNBOOK.relative_to(REPO_ROOT)} to document "
        "self-hosted runner registration, resources, and failure modes "
        "(#1531)."
    )


def test_diagnostic_script_exists() -> None:
    assert SCRIPT.exists(), (
        f"Expected diagnostic script {SCRIPT.relative_to(REPO_ROOT)} to "
        "exist so operators can verify runner health (#1531)."
    )


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX executable bit not meaningful on Windows checkouts",
)
def test_diagnostic_script_is_executable() -> None:
    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR, (
        f"{SCRIPT.relative_to(REPO_ROOT)} must be executable "
        "(chmod +x) so operators can run it directly."
    )


def test_diagnostic_script_has_safe_bash_header() -> None:
    """First two non-empty lines must be the bash shebang and ``set -euo pipefail``."""
    text = SCRIPT.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines, "diagnostic script is empty"
    assert lines[0] == "#!/usr/bin/env bash", (
        f"first line of {SCRIPT.relative_to(REPO_ROOT)} must be "
        f"'#!/usr/bin/env bash'; got {lines[0]!r}"
    )
    # set -euo pipefail must appear before any logic; allow comments/blank
    # lines between the shebang and the set call.
    head_lines = []
    for line in lines[1:30]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            head_lines.append(stripped)
            continue
        head_lines.append(stripped)
        break
    assert "set -euo pipefail" in head_lines, (
        f"{SCRIPT.relative_to(REPO_ROOT)} must call 'set -euo pipefail' "
        "near the top to fail fast on errors and unset variables."
    )


def test_diagnostic_script_supports_help_flag() -> None:
    """Script must expose a ``--help`` (or ``-h``) handler."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--help" in text, (
        f"{SCRIPT.relative_to(REPO_ROOT)} must accept a '--help' flag so "
        "operators can discover usage without reading the source."
    )


def test_diagnostic_script_calls_runners_api() -> None:
    """Script must call the GitHub Actions runners API via ``gh api``."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "actions/runners" in text, (
        f"{SCRIPT.relative_to(REPO_ROOT)} must query "
        "'repos/.../actions/runners' to verify runner registration."
    )
    assert "gh api" in text, (
        f"{SCRIPT.relative_to(REPO_ROOT)} must invoke 'gh api' so it works "
        "with the same auth flow operators already use."
    )


def test_runbook_links_to_diagnostic_script() -> None:
    """Cross-link sanity: runbook must reference the script path."""
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "scripts/check_self_hosted_runner.sh" in text, (
        f"{RUNBOOK.relative_to(REPO_ROOT)} must reference "
        "'scripts/check_self_hosted_runner.sh' so operators can find the "
        "diagnostic command from the runbook."
    )


def test_runbook_references_workflow() -> None:
    """Cross-link sanity: runbook must reference the workflow it gates."""
    text = RUNBOOK.read_text(encoding="utf-8")
    assert ".github/workflows/nightly-heavy.yml" in text, (
        f"{RUNBOOK.relative_to(REPO_ROOT)} must reference "
        "'.github/workflows/nightly-heavy.yml' so the dependency between "
        "the runner and the workflow is explicit."
    )


def test_script_references_workflow() -> None:
    """Cross-link sanity: script must reference the workflow it guards."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "nightly-heavy.yml" in text, (
        f"{SCRIPT.relative_to(REPO_ROOT)} must mention 'nightly-heavy.yml' "
        "(comment or help text) so operators reading the script know which "
        "workflow depends on the runner."
    )


def test_runbook_documents_resource_requirements() -> None:
    """Runbook must mention the heavy-tier markers so resource sizing is grounded."""
    text = RUNBOOK.read_text(encoding="utf-8").lower()
    # The workflow runs the union of these pytest markers.
    for marker in ("requires_extras", "load", "chaos", "e2e", "benchmark"):
        assert marker in text, (
            f"runbook must document the '{marker}' heavy-tier marker so "
            "resource expectations are anchored to real test commands."
        )


def test_runbook_documents_disable_procedure() -> None:
    """Runbook must explain how to mute/disable the workflow during maintenance."""
    text = RUNBOOK.read_text(encoding="utf-8").lower()
    # Accept any of the standard mute mechanisms.
    assert any(
        token in text
        for token in ("workflow_dispatch", "disable", "mute", "comment out")
    ), (
        "runbook must describe how to temporarily mute or disable "
        "nightly-heavy.yml when the runner is down for maintenance."
    )
