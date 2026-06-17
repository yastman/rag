"""Contract test: Required Superpowers chain is consistent across all three sources.

Pins that:
- .kiro/steering/swarm-worker-contract.md
- .kiro/skills/shared/superpowers-map.md
- scripts/validate_worker_prompt.py (FORBIDDEN_WORKER_SUPERPOWERS + enforcement)

all agree that the implementation chain = {executing-plans, test-driven-development,
verification-before-completion} and that using-git-worktrees /
finishing-a-development-branch are NOT required for ordinary workers.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

STEERING_CONTRACT = REPO / ".kiro" / "steering" / "swarm-worker-contract.md"
SUPERPOWERS_MAP = REPO / ".kiro" / "skills" / "shared" / "superpowers-map.md"
VALIDATOR = REPO / "scripts" / "validate_worker_prompt.py"

# The canonical three-step implementation chain
REQUIRED_TRIO = [
    "executing-plans",
    "test-driven-development",
    "verification-before-completion",
]

# These must NOT appear as required for ordinary (implementation) workers
FORBIDDEN_IN_IMPL_CHAIN = [
    "using-git-worktrees",
    "finishing-a-development-branch",
]


def _steering_impl_row(text: str) -> str:
    """Extract the implementation worker row from the markdown table."""
    for line in text.splitlines():
        if "implementation" in line and "feature" in line and "|" in line:
            return line
    return ""


def test_steering_contract_impl_chain_has_trio() -> None:
    """swarm-worker-contract.md implementation row must list the three required superpowers."""
    text = STEERING_CONTRACT.read_text(encoding="utf-8")
    row = _steering_impl_row(text)
    assert row, "Could not find implementation worker row in swarm-worker-contract.md"
    for skill in REQUIRED_TRIO:
        assert skill in row, (
            f"swarm-worker-contract.md implementation chain missing: {skill!r}\n"
            f"Row: {row}"
        )


def test_steering_contract_impl_chain_no_forbidden() -> None:
    """swarm-worker-contract.md implementation row must NOT list forbidden superpowers."""
    text = STEERING_CONTRACT.read_text(encoding="utf-8")
    row = _steering_impl_row(text)
    assert row, "Could not find implementation worker row in swarm-worker-contract.md"
    for skill in FORBIDDEN_IN_IMPL_CHAIN:
        assert skill not in row, (
            f"swarm-worker-contract.md implementation chain must NOT include: {skill!r}\n"
            f"Row: {row}"
        )


def test_steering_contract_worker_prompt_schema_example_no_forbidden() -> None:
    """The Worker Prompt Schema example block in swarm-worker-contract.md must not show forbidden superpowers."""
    text = STEERING_CONTRACT.read_text(encoding="utf-8")
    # Find the code block under ## Worker Prompt Schema
    schema_start = text.find("## Worker Prompt Schema")
    assert schema_start >= 0, "## Worker Prompt Schema section not found"
    schema_section = text[schema_start : schema_start + 800]
    for skill in FORBIDDEN_IN_IMPL_CHAIN:
        assert skill not in schema_section, (
            f"Worker Prompt Schema example must not include forbidden skill: {skill!r}"
        )


def _superpowers_map_impl_row(text: str) -> str:
    for line in text.splitlines():
        if "implementation" in line and "feature" in line and "|" in line:
            return line
    return ""


def test_superpowers_map_impl_chain_has_trio() -> None:
    """superpowers-map.md implementation row must list the three required superpowers."""
    text = SUPERPOWERS_MAP.read_text(encoding="utf-8")
    row = _superpowers_map_impl_row(text)
    assert row, "Could not find implementation worker row in superpowers-map.md"
    for skill in REQUIRED_TRIO:
        assert skill in row, (
            f"superpowers-map.md implementation chain missing: {skill!r}\n"
            f"Row: {row}"
        )


def test_superpowers_map_impl_chain_no_forbidden() -> None:
    """superpowers-map.md implementation row must NOT list forbidden superpowers."""
    text = SUPERPOWERS_MAP.read_text(encoding="utf-8")
    row = _superpowers_map_impl_row(text)
    assert row, "Could not find implementation worker row in superpowers-map.md"
    for skill in FORBIDDEN_IN_IMPL_CHAIN:
        assert skill not in row, (
            f"superpowers-map.md implementation chain must NOT include: {skill!r}\n"
            f"Row: {row}"
        )


def test_superpowers_map_forbids_worktrees_note() -> None:
    """superpowers-map.md must explicitly say not to require using-git-worktrees."""
    text = SUPERPOWERS_MAP.read_text(encoding="utf-8")
    assert "using-git-worktrees" in text, "superpowers-map.md must mention using-git-worktrees"
    # The note that says NOT to require it
    assert "Do not require" in text or "not require" in text.lower(), (
        "superpowers-map.md must say 'Do not require' using-git-worktrees for ordinary workers"
    )


def test_validator_forbids_worktrees_and_finishing() -> None:
    """validate_worker_prompt.py FORBIDDEN_WORKER_SUPERPOWERS must include using-git-worktrees and finishing-a-development-branch."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_worker_prompt", VALIDATOR)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    forbidden = module.FORBIDDEN_WORKER_SUPERPOWERS
    assert "superpowers:using-git-worktrees" in forbidden, (
        "validate_worker_prompt.py must forbid superpowers:using-git-worktrees"
    )
    assert "superpowers:finishing-a-development-branch" in forbidden, (
        "validate_worker_prompt.py must forbid superpowers:finishing-a-development-branch"
    )


def test_validator_enforces_trio_for_implementation() -> None:
    """validate_worker_prompt.py must enforce the three-step chain for implementation workers."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("validate_worker_prompt", VALIDATOR)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    # A prompt with only the trio (no forbidden superpowers) must pass the superpowers check
    valid_prompt = """Worker type: implementation
Worker agent: kiro-worker
Worker model: claude-sonnet-4.6

WORKER_NAME=test-worker
REPORT_FILE=logs/test-worker.md

Required Superpowers: superpowers:executing-plans, superpowers:test-driven-development, superpowers:verification-before-completion
Forbidden Superpowers: superpowers:using-superpowers, superpowers:using-git-worktrees, superpowers:finishing-a-development-branch
Finish Report Must Include:
- changed_files
- superpowers_used
- skipped_superpowers
- tests_run
- verification_evidence
- evidence_commands

tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
sleep 0.25
tmux send-keys -t "$ORCH_TARGET" C-m
"""
    errors = module.validate(valid_prompt, contract="markdown")
    assert errors == [], f"Valid trio prompt must not produce errors: {errors}"

    # A prompt that includes using-git-worktrees in Required Superpowers must be rejected
    invalid_prompt = valid_prompt.replace(
        "Required Superpowers: superpowers:executing-plans",
        "Required Superpowers: superpowers:using-git-worktrees, superpowers:executing-plans",
    )
    errors = module.validate(invalid_prompt, contract="markdown")
    assert any("using-git-worktrees" in e for e in errors), (
        "Validator must reject prompts with superpowers:using-git-worktrees in Required Superpowers"
    )


def test_no_dangling_swarm_notify_orchestrator_reference() -> None:
    """validate_worker_prompt.py must not reference the non-existent swarm_notify_orchestrator.py."""
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "swarm_notify_orchestrator.py" not in text, (
        "validate_worker_prompt.py references non-existent scripts/swarm_notify_orchestrator.py; "
        "replace with tmux send-keys -t \"$ORCH_TARGET\" wake-up mechanism"
    )
