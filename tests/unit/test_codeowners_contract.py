"""Contract: CODEOWNERS must cover all risky zones.

Risky zones are files that, if changed in a PR without review from the
appropriate owner, can break CI infrastructure, deployment, observability,
or contract guarantees. This test ensures the CODEOWNERS file is present
and covers each mandated zone.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"


# -- Risky zones that MUST be covered ------------------------------------------
# Pattern: (zone_pattern, zone_description)
# The pattern is matched as a substring anywhere in the CODEOWNERS file,
# so glob-style patterns like `.github/workflows/*` must appear literally.
RISKY_ZONES: list[tuple[str, str]] = [
    (".github/CODEOWNERS", "CODEOWNERS file itself (governance self-ownership)"),
    (".github/workflows/*", "CI/CD workflow files"),
    ("compose*.yml", "Compose files (compose.yml, compose.dev.yml, compose.vps.yml)"),
    ("Makefile", "Makefile (CI contract, lint/fast-lane gates)"),
    ("tests/contract/*", "Contract test suite"),
    ("tests/unit/observability/", "Observability unit tests"),
    ("docs/observability", "Observability documentation"),
    ("src/observability/", "Observability source modules"),
    ("telegram_bot/observability", "Telegram bot observability module"),
]


def test_codeowners_file_exists() -> None:
    """CODEOWNERS file must exist under .github/."""
    assert CODEOWNERS.exists(), (
        ".github/CODEOWNERS file must exist to define review ownership for risky zones."
    )


def test_codeowners_is_non_empty() -> None:
    """CODEOWNERS must not be empty."""
    if not CODEOWNERS.exists():
        return  # skip -- covered by test_codeowners_file_exists
    text = CODEOWNERS.read_text(encoding="utf-8").strip()
    assert text, ".github/CODEOWNERS must not be empty."


def test_codeowners_covers_all_risky_zones() -> None:
    """Every risky zone pattern must appear in CODEOWNERS."""
    if not CODEOWNERS.exists():
        return  # skip -- covered by test_codeowners_file_exists

    text = CODEOWNERS.read_text(encoding="utf-8")

    missing: list[str] = []
    for pattern, description in RISKY_ZONES:
        if pattern not in text:
            missing.append(f"{pattern!r} ({description})")

    assert not missing, (
        "CODEOWNERS is missing coverage for these risky zones:\n  "
        + "\n  ".join(missing)
        + "\n\nThese zones must have an assigned owner to gate "
        "infrastructure, observability, and contract changes."
    )


def test_codeowners_has_valid_syntax() -> None:
    """CODEOWNERS lines must follow the pattern: <pattern> @owner."""
    if not CODEOWNERS.exists():
        return  # skip -- covered by test_codeowners_file_exists

    text = CODEOWNERS.read_text(encoding="utf-8")
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert lines, "CODEOWNERS must contain at least one non-comment rule."

    for line_num, line in enumerate(lines, start=1):
        # Each line must have a file pattern followed by at least one @owner or team
        tokens = line.split()
        assert len(tokens) >= 2, (
            f"CODEOWNERS line {line_num} must have a pattern and at least one owner: {line!r}"
        )
        pattern, *owners = tokens
        # Pattern must not start with @ (that's an owner, not a path)
        assert not pattern.startswith("@"), (
            f"CODEOWNERS line {line_num}: first token {pattern!r} looks like "
            f"an owner, not a file pattern."
        )
        # At least one owner must start with @ (user, team, or org)
        assert any(o.startswith("@") for o in owners), (
            f"CODEOWNERS line {line_num}: no @owner found in {owners!r}."
        )
