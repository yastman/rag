"""Contract for card_9c05aee6022f — tier-based superpower requirements.

A trivial code change must not be forced through the full TDD chain. The
validator derives a tier from the worker type:
  trivial  (`quick`)                                  → verification only
  standard                                            → executing-plans + verification
  risky    (`implementation`/`plan-execution`/`review-fix`) → full chain incl. TDD

This was a red repro (no tiering existed); it is now the positive contract that
pins the tier policy in ``scripts/validate_worker_prompt.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

validator = pytest.importorskip(
    "validate_worker_prompt",
    reason="scripts/validate_worker_prompt.py not importable",
)


def _superpower_errors(prompt: str) -> list[str]:
    errors: list[str] = []
    validator.validate_superpowers_policy(prompt, errors)
    return errors


# A groomed TRIVIAL task (one-file docs/config/skill edge) routed to `quick`.
TRIVIAL_QUICK_PROMPT = (
    "Worker type: quick\n"
    "Required Superpowers: superpowers:verification-before-completion\n"
    "Forbidden Superpowers: superpowers:using-superpowers\n"
)

# A risky implementation task declaring only verification (missing TDD + plans).
RISKY_IMPL_UNDERSPECIFIED_PROMPT = (
    "Worker type: implementation\n"
    "Required Superpowers: superpowers:verification-before-completion\n"
    "Forbidden Superpowers: superpowers:using-superpowers\n"
)


def test_trivial_quick_worker_not_forced_into_full_tdd_chain() -> None:
    """A trivial `quick` worker that declares only verification must NOT be
    rejected for missing TDD / executing-plans (card_9c05aee6022f)."""
    errors = _superpower_errors(TRIVIAL_QUICK_PROMPT)
    assert not any("test-driven-development" in e for e in errors), (
        f"trivial `quick` worker should not require TDD; errors: {errors!r}"
    )
    assert not any("executing-plans" in e for e in errors), (
        f"trivial `quick` worker should not require executing-plans; errors: {errors!r}"
    )


def test_risky_implementation_still_requires_full_chain() -> None:
    """A risky `implementation` worker must still be held to the full chain."""
    errors = _superpower_errors(RISKY_IMPL_UNDERSPECIFIED_PROMPT)
    assert any("test-driven-development" in e for e in errors), (
        f"risky implementation worker must still require TDD; errors: {errors!r}"
    )
    assert any("executing-plans" in e for e in errors), (
        f"risky implementation worker must still require executing-plans; errors: {errors!r}"
    )


def test_tier_mapping_is_coherent() -> None:
    """The tier model exists and maps `quick`→trivial with a strictly lighter
    requirement set than the risky chain."""
    assert validator.WORKER_TYPE_TIER["quick"] == "trivial"
    assert validator.WORKER_TYPE_TIER["implementation"] == "risky"

    trivial = set(validator.WORKER_TIER_REQUIRED_SUPERPOWERS["trivial"])
    risky = set(validator.WORKER_TIER_REQUIRED_SUPERPOWERS["risky"])

    assert "superpowers:verification-before-completion" in trivial
    assert "superpowers:test-driven-development" not in trivial
    assert "superpowers:test-driven-development" in risky
    assert trivial < risky, "trivial tier must be strictly lighter than risky"

    # Every code-changing type resolves to a defined tier (default risky).
    for wtype in validator.CODE_CHANGING_WORKER_TYPES:
        tier = validator.WORKER_TYPE_TIER.get(wtype, "risky")
        assert tier in validator.WORKER_TIER_REQUIRED_SUPERPOWERS
