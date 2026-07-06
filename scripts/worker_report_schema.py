#!/usr/bin/env python3
"""Worker-report schema — single code-level source of truth (#2305 P1).

Machine mirror of the human-readable contract in
``.kiro/steering/swarm-worker-contract.md``. A contract test
(``scripts/tests/test_swarm_acceptance_mechanical_contract.py``) asserts the
required code-changing field set here equals the steering contract, so the
schema can never silently drift from the prose.

Boundary (agreed in ``SWARM_AUDIT_REPORT.md``):

- ``schema-valid != accepted``. This model validates *structure* only. It is a
  mechanical check, never a semantic acceptance verdict.
- Strict Pydantic validation is reserved for the legacy strict path
  (``KIRO_STRICT_REPORT=1``). The default Markdown mechanical-facts path is
  pure-python and does NOT require pydantic (so it runs under bare ``python3``
  without the project venv).
"""

from __future__ import annotations


try:  # pydantic is only needed for strict-mode structural validation
    from pydantic import BaseModel, Field

    _HAVE_PYDANTIC = True
except ModuleNotFoundError:  # mechanical-facts path is pure-python
    _HAVE_PYDANTIC = False

# The six fields acceptance tooling scans verbatim. Keep in lockstep with the
# table in ``.kiro/steering/swarm-worker-contract.md`` §"Worker Report Schema".
_CODE_CHANGING_REQUIRED: tuple[str, ...] = (
    "superpowers_used",
    "skipped_superpowers",
    "changed_files",
    "tests_run",
    "verification_evidence",
    "evidence_commands",
)

# Read-only / research workers do not change behaviour: no tests/verification.
_READ_ONLY_REQUIRED: tuple[str, ...] = (
    "superpowers_used",
    "skipped_superpowers",
    "evidence_commands",
)

# Read-only PR review reports (PR_REVIEW shape): a decision + head + evidence.
# No superpowers fields — the review report shape does not carry them.
_PR_REVIEW_REQUIRED: tuple[str, ...] = (
    "review_decision",
    "head_sha",
    "evidence_commands",
)


def code_changing_required_fields() -> tuple[str, ...]:
    """Required field names for a code-changing worker report (source of truth)."""
    return _CODE_CHANGING_REQUIRED


def read_only_required_fields() -> tuple[str, ...]:
    """Required field names for a read-only / research worker report."""
    return _READ_ONLY_REQUIRED


def pr_review_required_fields() -> tuple[str, ...]:
    """Required field names for a read-only PR review report."""
    return _PR_REVIEW_REQUIRED


def required_fields_for_role(role: str) -> tuple[str, ...]:
    """Map a worker role to its required field set."""
    if role in ("implementation", "review-fix"):
        return _CODE_CHANGING_REQUIRED
    if role == "pr-review":
        return _PR_REVIEW_REQUIRED
    return _READ_ONLY_REQUIRED


if _HAVE_PYDANTIC:

    class WorkerReport(BaseModel):
        """Structural contract for a code-changing worker finish report.

        Strict-mode only. Optional bookkeeping fields are allowed but not
        required; the required set is what acceptance tooling mechanically
        checks for presence.
        """

        model_config = {"extra": "allow"}

        superpowers_used: list[str] = Field(..., description="Superpowers actually executed.")
        skipped_superpowers: list[str] = Field(
            ..., description="Required superpowers skipped, with justification. [] if none."
        )
        changed_files: list[str] = Field(..., description="Repo-relative paths touched.")
        tests_run: list[str] = Field(..., description="Test selectors invoked, with pass/fail.")
        verification_evidence: str = Field(..., description="Summary linking change to fresh runs.")
        evidence_commands: list[str] = Field(..., description="Replayable shell commands.")

    class ReadOnlyReport(BaseModel):
        """Structural contract for a read-only / research worker finish report."""

        model_config = {"extra": "allow"}

        superpowers_used: list[str] = Field(...)
        skipped_superpowers: list[str] = Field(...)
        evidence_commands: list[str] = Field(...)
