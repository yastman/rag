"""Contract: ``.kiro/steering/swarm-worker-contract.md`` defines the swarm
worker pipeline contract (#1937).

Issue #1937 demanded a stricter contract for code-changing swarm workers:

* required Superpowers per worker type (read-only / implementation /
  bug-debug / review-fix);
* required worker-prompt and worker-report schema fields
  (``Required Superpowers``, ``superpowers_used``, ``skipped_superpowers``,
  ``changed_files``, ``tests_run``, ``verification_evidence``,
  ``evidence_commands``);
* a separate review gate for P0 / security / destructive lanes;
* fresh evidence checked against worker claims at acceptance time.

The actual contract lives in a steering markdown so it loads on every
agent session (``.kiro/steering/`` files with ``inclusion: always``).
This contract test guards that:

1. The steering file exists.
2. It is marked ``inclusion: always`` so it actually loads.
3. It enumerates each Superpower the issue requires by file name.
4. It enumerates each worker-report schema field the issue requires.
5. It distinguishes read-only / preflight workers from code-changing
   implementation workers and calls out the P0/security review gate.
6. It pins the P10 MIRROR-mode local-loop review surface (card_chat
   verdict + reports(commit_review) record + local-loop-contract ref)
   so review/acceptance cannot silently revert to PR-only.

The check is intentionally a substring scan against the rendered file —
the goal is to keep the contract pinned, not to lint Markdown grammar.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STEERING_PATH = REPO_ROOT / ".kiro" / "steering" / "swarm-worker-contract.md"


REQUIRED_SUPERPOWERS = (
    "executing-plans",
    "test-driven-development",
    "verification-before-completion",
    "systematic-debugging",
    "receiving-code-review",
)


REQUIRED_REPORT_FIELDS = (
    "Required Superpowers",
    "superpowers_used",
    "skipped_superpowers",
    "changed_files",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
)


REQUIRED_LANE_DISTINCTIONS = (
    "read-only",
    "implementation",
    "review",
)


# P10 local-loop migration (decision card_aeb26f262648): the contract must pin
# the MIRROR-mode review surface so review/acceptance cannot silently drift back
# to a PR-only world. Review can be a card_chat verdict + reports(commit_review)
# record, and the file must reference shared/local-loop-contract.md.
REQUIRED_LOCAL_LOOP_TOKENS = (
    "local-loop-contract",
    "card_chat",
    "commit_review",
)


def test_swarm_worker_contract_steering_file_exists() -> None:
    assert STEERING_PATH.exists(), (
        f"Expected swarm worker contract steering doc at "
        f"{STEERING_PATH.relative_to(REPO_ROOT)} (#1937). The file must "
        f"live under .kiro/steering/ so it auto-loads on every agent "
        f"session."
    )


def test_swarm_worker_contract_is_always_included() -> None:
    text = STEERING_PATH.read_text(encoding="utf-8")
    # Front matter must declare ``inclusion: always`` so the contract is
    # loaded for every agent session, not lazily on a keyword match.
    assert "inclusion: always" in text, (
        "swarm-worker-contract.md must declare 'inclusion: always' in its "
        "front matter so agents load the contract on every session "
        "without keyword negotiation."
    )


def test_swarm_worker_contract_lists_each_required_superpower() -> None:
    text = STEERING_PATH.read_text(encoding="utf-8")
    missing = [skill for skill in REQUIRED_SUPERPOWERS if skill not in text]
    assert not missing, (
        f"swarm-worker-contract.md is missing references to the following "
        f"Superpowers required by #1937: {missing}. Each Superpower must "
        f"appear by file-stem name (e.g. 'test-driven-development') so "
        f"workers can resolve them against skills/superpowers/."
    )


def test_swarm_worker_contract_lists_each_required_report_field() -> None:
    text = STEERING_PATH.read_text(encoding="utf-8")
    missing = [field for field in REQUIRED_REPORT_FIELDS if field not in text]
    assert not missing, (
        f"swarm-worker-contract.md is missing the following worker-report "
        f"fields required by #1937: {missing}. Each field must be named "
        f"verbatim so acceptance tooling can scan worker reports for "
        f"compliance."
    )


def test_swarm_worker_contract_distinguishes_lanes_and_review_gate() -> None:
    text = STEERING_PATH.read_text(encoding="utf-8").lower()
    missing = [lane for lane in REQUIRED_LANE_DISTINCTIONS if lane not in text]
    assert not missing, (
        f"swarm-worker-contract.md must distinguish worker types by lane "
        f"(missing: {missing}). #1937 requires read-only / preflight "
        f"workers to differ from code-changing implementation workers, "
        f"and P0/security/destructive lanes must route through a review "
        f"gate before final acceptance."
    )
    # Explicit review gate trigger words.
    assert "p0" in text or "destructive" in text or "security" in text, (
        "swarm-worker-contract.md must explicitly call out the review "
        "gate trigger lanes (P0 / security / destructive) per #1937."
    )


def test_swarm_worker_contract_pins_local_loop_review_surface() -> None:
    text = STEERING_PATH.read_text(encoding="utf-8")
    missing = [tok for tok in REQUIRED_LOCAL_LOOP_TOKENS if tok not in text]
    assert not missing, (
        f"swarm-worker-contract.md must pin the MIRROR-mode local-loop "
        f"review surface (missing: {missing}). P10 (decision "
        f"card_aeb26f262648) decoupled review/acceptance from GitHub: "
        f"review can be a card_chat verdict plus a reports(commit_review) "
        f"record, and the contract must reference "
        f"shared/local-loop-contract.md so the surface cannot drift back "
        f"to PR-only."
    )
