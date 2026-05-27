"""Contract: ``EMBEDDING_SERVICE_FAILURE.md`` documents the canonical
BGE-M3 endpoint recovery procedure for issue #2188.

Issue #2188 ("Restore canonical BGE-M3 compose endpoint on
``localhost:8000``") describes a recurring local-development failure
mode: the canonical compose service ``dev-bge-m3-1`` cannot bind
``127.0.0.1:8000`` because Docker Desktop's port-forwarding API is
stuck (tracked under #2182), so an operator side-loads a temporary
``bge-m3-tmp`` container on ``127.0.0.1:8888`` and overrides
``BGE_M3_URL=http://localhost:8888`` in ``.env``.

The acceptance criteria call for an operational restore:

* recreate the canonical compose service so port ``8000`` is bound;
* verify ``curl -fsS http://localhost:8000/health`` returns healthy;
* stop / remove the temporary ``bge-m3-tmp`` container;
* remove the ``BGE_M3_URL=http://localhost:8888`` override;
* re-run ``make test-bot-health`` and confirm preflight passes.

For the recovery to be reproducible across operators and shifts, the
existing embedding-service runbook must spell out these steps verbatim.
This contract pins the runbook so future edits cannot silently drop the
recovery procedure or its diagnostic markers.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "EMBEDDING_SERVICE_FAILURE.md"


REQUIRED_MARKERS: tuple[tuple[str, str], ...] = (
    # Issue references: anchor the section to the tracked work.
    ("#2188", "links the recovery section to issue #2188"),
    ("#2182", "links the recovery section to the upstream Docker forwarding bug"),
    # Section heading: operators should be able to grep for the failure name.
    (
        "Canonical bge-m3 endpoint",
        "section heading naming the canonical-endpoint recovery procedure",
    ),
    # Diagnostic markers: surface the symptoms before the fix.
    (
        "127.0.0.1:8000",
        "names the canonical host:port operators must restore",
    ),
    (
        "bge-m3-tmp",
        "names the temporary side-loaded container that must be removed",
    ),
    (
        "BGE_M3_URL=http://localhost:8888",
        "calls out the temporary .env override that must be removed",
    ),
    # Recovery commands: pinned verbatim so on-call can copy/paste.
    (
        "docker compose --env-file .env -f compose.yml -f compose.dev.yml up -d --force-recreate --no-deps bge-m3",
        "documents the canonical recreate command from the issue",
    ),
    (
        "curl -fsS http://localhost:8000/health",
        "documents the canonical health probe command from the issue",
    ),
    (
        "make test-bot-health",
        "documents the post-restore validation step",
    ),
)


@pytest.fixture(scope="module")
def runbook_text() -> str:
    assert RUNBOOK.exists(), f"runbook missing at {RUNBOOK}"
    return RUNBOOK.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("marker", "purpose"),
    REQUIRED_MARKERS,
    ids=[purpose for _, purpose in REQUIRED_MARKERS],
)
def test_runbook_documents_canonical_endpoint_recovery(
    runbook_text: str, marker: str, purpose: str
) -> None:
    assert marker in runbook_text, (
        f"{RUNBOOK.relative_to(REPO_ROOT)} is missing required marker for "
        f"#2188 canonical-endpoint recovery: {purpose!r}. "
        f"Expected substring not found: {marker!r}."
    )


def _extract_recovery_section(runbook_text: str) -> str:
    """Return the substring covering the #2188 recovery section.

    The section is delimited by its named ``###`` heading and the next
    sibling ``##`` heading (typically ``## Prevention``). Scoping the
    ordering assertion to this slice prevents earlier mentions of
    ``make test-bot-health`` (e.g. the Fast-Path Diagnosis block) from
    bleeding into the check.
    """
    heading = "### Canonical bge-m3 endpoint"
    start = runbook_text.find(heading)
    assert start >= 0, (
        "recovery section heading not found in "
        f"{RUNBOOK.relative_to(REPO_ROOT)}; expected to start with {heading!r}."
    )
    rest = runbook_text[start:]
    # Stop at the next sibling ``## ``-level heading.
    next_section = rest.find("\n## ", 1)
    return rest if next_section < 0 else rest[:next_section]


def test_runbook_recovery_section_lists_acceptance_steps(runbook_text: str) -> None:
    """The recovery section must enumerate the issue's acceptance steps in order.

    The section may use any prose, but the canonical recreate command must
    appear *before* the canonical health probe, which must appear before the
    .env override removal, which must appear before ``make test-bot-health``.
    This mirrors the operational order from the issue body.
    """
    section = _extract_recovery_section(runbook_text)
    recreate = (
        "docker compose --env-file .env -f compose.yml -f compose.dev.yml "
        "up -d --force-recreate --no-deps bge-m3"
    )
    health = "curl -fsS http://localhost:8000/health"
    override = "BGE_M3_URL=http://localhost:8888"
    revalidate = "make test-bot-health"

    positions = {
        name: section.find(token)
        for name, token in (
            ("recreate", recreate),
            ("health", health),
            ("override", override),
            ("revalidate", revalidate),
        )
    }
    missing = [name for name, pos in positions.items() if pos < 0]
    assert not missing, (
        f"recovery section is missing acceptance-step tokens: {missing}. "
        "All four steps from #2188 must appear in the recovery section."
    )
    assert positions["recreate"] < positions["health"] < positions["revalidate"], (
        "Recovery steps appear out of order in "
        f"{RUNBOOK.relative_to(REPO_ROOT)} #2188 section; expected: "
        f"recreate -> health -> revalidate. Got positions: {positions}."
    )
    assert positions["override"] < positions["revalidate"], (
        "The .env override removal must be documented before the post-restore "
        f"`make test-bot-health` step in {RUNBOOK.relative_to(REPO_ROOT)}."
    )
