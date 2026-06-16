"""Contract tests for .kiro/skills/ swarm skill files.

Verifies that every adapted swarm skill:
1. Has valid YAML frontmatter with required `name` and `description` fields.
2. Contains required report-field literals for its role.
3. Does NOT contain opencode/codex-specific artefacts (tmux send-keys, ORCH_TARGET,
   launch_opencode_worker.sh, SWARM_CONTRACT=, opencode run).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


SKILLS_DIR = Path(__file__).resolve().parents[2] / ".kiro" / "skills"

SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body) from a SKILL.md."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]
    return fm, body


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_valid_frontmatter(skill_path: Path) -> None:
    text = skill_path.read_text(encoding="utf-8")
    fm, _ = _parse_frontmatter(text)
    assert "name" in fm, f"{skill_path}: missing 'name' in frontmatter"
    assert "description" in fm, f"{skill_path}: missing 'description' in frontmatter"
    assert isinstance(fm["name"], str) and fm["name"].strip(), f"{skill_path}: 'name' is empty"
    assert isinstance(fm["description"], str) and fm["description"].strip(), (
        f"{skill_path}: 'description' is empty"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_skill_has_no_opencode_codex_artefacts(skill_path: Path) -> None:
    """Kiro-adapted skills must not contain opencode/codex hard runtime paths."""
    text = skill_path.read_text(encoding="utf-8")
    # Hard runtime artefacts that must NOT appear (execution paths, not mentions in "do not use X")
    forbidden = [
        "launch_opencode_worker.sh",
        "$ORCH_PANE",
        'tmux send-keys -t "$ORCH_PANE"',
    ]
    for pattern in forbidden:
        assert pattern not in text, (
            f"{skill_path.parent.name}: contains forbidden codex artefact: {pattern!r}"
        )


# --- Per-skill required literals ---

WORKER_CONTRACT_REQUIRED = [
    "superpowers_used",
    "skipped_superpowers",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
    "reserved_files",
    "changed_files",
    "head_sha",
    "Do not push",
    "Do not create or update PRs",
    "unless the prompt explicitly assigns that operation",
    "bug_class_registry_evidence",
    ".github/bug-classes.yml",
]

PR_FINISH_REQUIRED = [
    "superpowers_used",
    "skipped_superpowers",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
    "changed_files",
    "head_sha",
    "Do not push",
    "[DONE]",
    "[FAILED]",
    "[BLOCKED]",
]

SECRETARY_INTAKE_REQUIRED = [
    "INTAKE_BRIEF",
    "confidence",
    "task_kind",
    "summary",
    "top_facts",
    "evidence_commands",
    "[DONE]",
    "Forbidden",
]

REVIEW_FIX_REQUIRED = [
    "PR_REVIEW",
    "review_decision",
    "blockers",
    "evidence_commands",
    "REVIEW_FIX",
    "fixed_blockers",
    "changed_files",
]

BUG_REPORTING_REQUIRED = [
    "BUG_REPORT",
    "evidence",
    "impact",
    "recommended_disposition",
    "fix_now",
    "follow_up_issue",
    "[DONE]",
]

SDK_BASELINE_REQUIRED = [
    "SDK_ADVISORY",
    "gate_result",
    "plan_revision_required",
    "classification",
    "implementation_recommendation",
    "pass",
    "change_required",
    "blocked",
]

DISPATCHING_REQUIRED = [
    "subagent",
    "depends_on",
    "Self-contained",
    "loop_to",
]

SUBAGENT_DRIVEN_REQUIRED = [
    "DONE",
    "DONE_WITH_CONCERNS",
    "BLOCKED",
    "NEEDS_CONTEXT",
    "spec",
    "quality",
    "subagent",
    "writing-plans",
    "test-driven-development",
]

SWARM_ORCHESTRATOR_REQUIRED = [
    "control plane",
    "swarm-plan",
    "swarm-acceptance",
    "swarm-recovery",
    "DONE",
    "FAILED",
    "BLOCKED",
    "./scripts/launch_kiro_worker.sh",
]

SWARM_PLAN_REQUIRED = [
    "SWARM_PLAN",
    "worktree",
    "base_branch",
    "target_branch",
    "reserved_files",
    "required_superpowers",
    "forbidden_superpowers",
    "superpowers:executing-plans",
    "superpowers:test-driven-development",
    "superpowers:verification-before-completion",
    "Finish Report Must Include:",
    "changed_files",
    "superpowers_used",
    "skipped_superpowers",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
    "bug_class_registry_evidence",
    ".github/bug-classes.yml",
    "not sufficient by itself",
]

SWARM_ACCEPTANCE_REQUIRED = [
    "ACCEPTANCE_DECISION",
    "changed_files",
    "bug_class_registry_evidence",
    "scripts/close_markdown_worker_window.py",
    "disposition",
    "merge_done",
    "keep_worktree",
    "discard_with_confirmation",
    "artifact_trust",
    "needs_fix",
    "needs_review",
]

SWARM_RECOVERY_REQUIRED = [
    "RECOVERY_REPORT",
    "safe_to_continue",
    "./scripts/set_orchestrator_window.sh",
]

SWARM_PR_REVIEW_FLOW_REQUIRED = [
    "MERGE_READINESS",
    "review_decision",
    "merge_ready",
    "pr-review-fix",
    "blockers",
    "superpowers:receiving-code-review",
    "anti_regression_evidence",
]

PER_SKILL_CHECKS: dict[str, list[str]] = {
    "swarm-worker-contract": WORKER_CONTRACT_REQUIRED,
    "swarm-pr-finish": PR_FINISH_REQUIRED,
    "swarm-secretary-intake": SECRETARY_INTAKE_REQUIRED,
    "swarm-review-fix": REVIEW_FIX_REQUIRED,
    "swarm-bug-reporting": BUG_REPORTING_REQUIRED,
    "swarm-sdk-baseline": SDK_BASELINE_REQUIRED,
    "dispatching-parallel-agents": DISPATCHING_REQUIRED,
    "subagent-driven-development": SUBAGENT_DRIVEN_REQUIRED,
    "swarm-orchestrator": SWARM_ORCHESTRATOR_REQUIRED,
    "swarm-plan": SWARM_PLAN_REQUIRED,
    "swarm-acceptance": SWARM_ACCEPTANCE_REQUIRED,
    "swarm-recovery": SWARM_RECOVERY_REQUIRED,
    "swarm-pr-review-flow": SWARM_PR_REVIEW_FLOW_REQUIRED,
}


@pytest.mark.parametrize(
    "skill_name,required_literals",
    list(PER_SKILL_CHECKS.items()),
    ids=lambda x: x if isinstance(x, str) else "literals",
)
def test_skill_contains_required_literals(skill_name: str, required_literals: list[str]) -> None:
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_path.exists(), f".kiro/skills/{skill_name}/SKILL.md does not exist"
    text = skill_path.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    for literal in required_literals:
        assert literal in normalized, f"{skill_name}: required literal missing: {literal!r}"


def test_all_expected_skills_exist() -> None:
    expected = set(PER_SKILL_CHECKS.keys())
    found = {p.parent.name for p in SKILL_FILES}
    missing = expected - found
    assert not missing, f"Missing skills: {missing}"


# --- Script tests ---

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

EXPECTED_SCRIPTS = [
    "validate_worker_prompt.py",
    "validate_worker_signal.py",
    "close_markdown_worker_window.py",
    "route_constants.py",
    "launch_kiro_worker.sh",
    "set_orchestrator_window.sh",
]


@pytest.mark.parametrize("script_name", EXPECTED_SCRIPTS)
def test_swarm_script_exists(script_name: str) -> None:
    assert (SCRIPTS_DIR / script_name).exists(), f"scripts/{script_name} does not exist"


def test_validate_worker_prompt_importable() -> None:
    """validate_worker_prompt.py must be importable and expose validate()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_worker_prompt", SCRIPTS_DIR / "validate_worker_prompt.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(getattr(module, "validate", None))
    assert callable(getattr(module, "validate_content_safety", None))


def test_validate_worker_prompt_accepts_valid_markdown_prompt() -> None:
    """A well-formed markdown worker prompt must pass validation."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_worker_prompt", SCRIPTS_DIR / "validate_worker_prompt.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    prompt = """Worker type: implementation
OpenCode agent: kiro_default
OpenCode model: claude-sonnet-4.6

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
    errors = module.validate(prompt, contract="markdown")
    assert errors == [], f"Unexpected validation errors: {errors}"


def test_validate_worker_prompt_rejects_missing_superpowers() -> None:
    """A prompt missing Required Superpowers must fail validation."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "validate_worker_prompt", SCRIPTS_DIR / "validate_worker_prompt.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    prompt = """Worker type: implementation
OpenCode agent: kiro_default
OpenCode model: claude-sonnet-4.6

WORKER_NAME=test-worker
REPORT_FILE=logs/test-worker.md

tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
sleep 0.25
tmux send-keys -t "$ORCH_TARGET" C-m
"""
    errors = module.validate(prompt, contract="markdown")
    assert any("Required Superpowers" in e for e in errors)


def test_close_markdown_worker_window_importable() -> None:
    """close_markdown_worker_window.py must be importable."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "close_markdown_worker_window", SCRIPTS_DIR / "close_markdown_worker_window.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "FORBIDDEN_PREFIXES")


def test_route_constants_importable() -> None:
    """route_constants.py must be importable and expose required constants."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "route_constants", SCRIPTS_DIR / "route_constants.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert hasattr(module, "CANONICAL_WORKER_ROUTES")
    assert hasattr(module, "SECRETARY_AGENT_MODELS")
    assert hasattr(module, "DEFAULT_WORKER_MODEL")


def test_launch_kiro_worker_sh_has_orch_target_logic() -> None:
    """launch_kiro_worker.sh must read ORCH_TARGET from marker when not set."""
    text = (SCRIPTS_DIR / "launch_kiro_worker.sh").read_text(encoding="utf-8")
    assert "ORCH_TARGET" in text
    assert "orchestrator-window.json" in text
    assert "tmux send-keys" in text
    assert "[FAILED]" in text
    assert "STATUS_LINE" in text
    assert "ORCH_TARGET" in text


def test_set_orchestrator_window_sh_creates_unique_name() -> None:
    """set_orchestrator_window.sh must create unique orch-* window name."""
    text = (SCRIPTS_DIR / "set_orchestrator_window.sh").read_text(encoding="utf-8")
    assert "tmux rename-window" in text
    assert "orch-" in text
    assert "orchestrator-window.json" in text
    assert "ORCH_TARGET" in text
