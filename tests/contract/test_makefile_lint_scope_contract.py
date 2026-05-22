"""Contract test for issue #1949 — `make` quality-gate targets must cover
all first-class Python packages.

Historically `make lint` / `make format` / `make pylint` / `make security`
only covered `src/` and `telegram_bot/`, leaving real production code in
`mini_app/`, `services/` (`bge-m3-api`, `user-base`, `docling`), and
`scripts/` (e.g. `scripts/e2e/`) outside the local quality gate. The
pre-commit hook covers everything, so a developer who skips pre-commit
could land unformatted code in the missing scopes (a `ruff format --check`
on `scripts/` originally surfaced one such drift).

This test asserts the Makefile expresses the union scope through a single
`LINT_PATHS` variable, and that every quality-gate target invokes its tool
on `$(LINT_PATHS)`. It also asserts CI mirrors the same scope so PR CI
honestly gates what the local target gates.

The list of required paths is the union from issue #1949.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MAKEFILE = REPO / "Makefile"
CI_YML = REPO / ".github" / "workflows" / "ci.yml"

REQUIRED_PATHS = ["src/", "telegram_bot/", "mini_app/", "services/", "scripts/"]


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def test_makefile_declares_lint_paths_variable_with_full_scope() -> None:
    text = _makefile_text()
    match = re.search(r"^LINT_PATHS\s*:?=\s*(.+?)$", text, re.MULTILINE)
    assert match, (
        "Makefile must declare a LINT_PATHS variable so all quality-gate "
        "targets share a single scope"
    )
    declared = match.group(1).split()
    for required in REQUIRED_PATHS:
        assert required in declared, f"LINT_PATHS missing {required!r}; current value: {declared}"


def _assert_target_uses_lint_paths(text: str, target: str, tool_token: str) -> None:
    """Find a make target's recipe block and assert the relevant tool line
    references $(LINT_PATHS).
    """

    pattern = rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_-]+:|\Z)"
    block_match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert block_match, f"Makefile must define a {target!r} target"
    block = block_match.group(0)
    tool_line_re = rf"\b{re.escape(tool_token)}\b[^\n]*"
    tool_lines = re.findall(tool_line_re, block)
    assert tool_lines, f"target {target!r} must contain at least one {tool_token!r} command"
    assert any("$(LINT_PATHS)" in line for line in tool_lines), (
        f"target {target!r} must invoke {tool_token!r} on $(LINT_PATHS); "
        f"found tool lines: {tool_lines}"
    )


def test_makefile_lint_target_uses_lint_paths() -> None:
    _assert_target_uses_lint_paths(_makefile_text(), "lint", "ruff check")


def test_makefile_format_target_uses_lint_paths() -> None:
    _assert_target_uses_lint_paths(_makefile_text(), "format", "ruff format")


def test_makefile_format_check_target_uses_lint_paths() -> None:
    _assert_target_uses_lint_paths(_makefile_text(), "format-check", "ruff format")


def test_makefile_type_check_target_uses_lint_paths() -> None:
    _assert_target_uses_lint_paths(_makefile_text(), "type-check", "mypy")


def test_makefile_pylint_target_uses_lint_paths() -> None:
    _assert_target_uses_lint_paths(_makefile_text(), "pylint", "pylint")


def test_makefile_security_target_uses_lint_paths_for_bandit_and_vulture() -> None:
    text = _makefile_text()
    _assert_target_uses_lint_paths(text, "security", "bandit")
    _assert_target_uses_lint_paths(text, "security", "vulture")


def test_ci_workflow_mirrors_full_lint_scope() -> None:
    """CI's static-only ruff lane must use the same scope as `make lint`.

    The CI job invokes `uvx ruff check ... --output-format=github` and
    `uvx ruff format ... --check`. We assert both lines reference each
    of the canonical paths, otherwise PR CI is silently narrower than
    the local gate.
    """

    text = CI_YML.read_text(encoding="utf-8")
    # Find the ruff check and ruff format lines; they live in `run:` blocks.
    ruff_check_lines = [line for line in text.splitlines() if "ruff check" in line]
    ruff_format_lines = [line for line in text.splitlines() if "ruff format" in line]
    assert ruff_check_lines, "ci.yml must run `ruff check`"
    assert ruff_format_lines, "ci.yml must run `ruff format ... --check`"
    for required in REQUIRED_PATHS:
        assert any(required in line for line in ruff_check_lines), (
            f"ci.yml ruff check lane is missing scope: {required!r}"
        )
        assert any(required in line for line in ruff_format_lines), (
            f"ci.yml ruff format lane is missing scope: {required!r}"
        )
