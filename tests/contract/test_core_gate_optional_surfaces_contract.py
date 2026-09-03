"""Contract: the deterministic core gate must not collect optional surfaces.

Optional surface tests remain first-class, but they depend on extras or adapter
SDKs that are intentionally absent from the lean core install. ``make test`` is
therefore limited to the core gate plus the no-service integration/smoke check
(#3220 retired the legacy graph-path lane with the graph-compat runtime).

After #2638: archived surface targets (test-api-adapter, test-legacy-graph-extra,
test-voice-extra, test-eval-extra, test-observability-extra, test-optional-surfaces)
are removed from the Makefile. After #3235 (Markdown-only ingestion) the
tests/unit/ingestion suite no longer needs optional extras and left the
requires-extras surface; the remaining explicit opt-in targets are
test-telegram-adapter and test-ingestion. Exclusion variables remain defined
for the broad test-unit lane to avoid collecting extras-dependent tests.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"
OPTIONAL_REQUIRES_EXTRAS_DIRS = (
    Path("tests/unit/voice"),
    Path("tests/unit/evaluation"),
    Path("tests/unit/observability"),
)
OPTIONAL_SURFACE_TOKENS = (
    "pytest tests/unit/",
    "tests/unit/api",
    "tests/unit/voice",
    "tests/unit/ingestion",
    "tests/unit/evaluation",
    "tests/unit/observability",
    "tests/unit/graph",
    "tests/unit/mini_app",
    "test-telegram-adapter",
    "test-api-adapter",
    "test-legacy-graph-extra",
    "test-ingestion",
)
# Remaining explicit opt-in targets after #2638/#3235 cleanup.
OPTIONAL_TARGETS = (
    "test-telegram-adapter",
    "test-ingestion",
)
OPTIONAL_OBSERVABILITY_DIAGNOSTIC_TARGETS: tuple[str, ...] = ()
REQUIRED_GATE_TARGETS = (
    "test",
    "test-core",
    "test-contract",
)


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_body(text: str, target: str) -> str:
    pattern = re.compile(rf"^{re.escape(target)}:.*?\n", re.MULTILINE)
    match = pattern.search(text)
    assert match is not None, f"Makefile must define {target!r}"

    body_lines: list[str] = []
    for line in text[match.end() :].splitlines():
        if line and not line.startswith(("\t", " ", "\\")):
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def test_make_test_is_deterministic_core_gate_not_broad_unit_collection() -> None:
    body = _target_body(_makefile_text(), "test")

    assert "$(MAKE) test-core" in body
    assert "$(MAKE) test-no-service-lane" in body
    assert "pytest tests/unit/" not in body
    assert "pytest tests/integration" not in body


def test_make_test_does_not_run_optional_surface_paths_or_targets() -> None:
    body = _target_body(_makefile_text(), "test")

    offenders = [token for token in OPTIONAL_SURFACE_TOKENS if token in body]
    assert offenders == []


def test_optional_surface_files_use_registered_requires_extras_marker() -> None:
    missing: list[str] = []
    for rel_dir in OPTIONAL_REQUIRES_EXTRAS_DIRS:
        for test_file in sorted((REPO_ROOT / rel_dir).glob("test*.py")):
            text = test_file.read_text(encoding="utf-8")
            if "pytestmark" not in text or "pytest.mark.requires_extras" not in text:
                missing.append(str(test_file.relative_to(REPO_ROOT)))

    assert missing == []


def test_optional_surface_targets_are_explicit() -> None:
    text = _makefile_text()

    for target in OPTIONAL_TARGETS:
        body = _target_body(text, target)
        assert "pytest" in body or target == "test-optional-surfaces"


def test_langfuse_baseline_diagnostics_are_not_required_gate_dependencies() -> None:
    """Langfuse-backed baseline checks remain explicit optional diagnostics."""

    text = _makefile_text()

    for target in OPTIONAL_OBSERVABILITY_DIAGNOSTIC_TARGETS:
        assert re.search(rf"^{re.escape(target)}:", text, re.MULTILINE), (
            f"Makefile must keep {target!r} as an explicit opt-in diagnostic target."
        )

    for target in REQUIRED_GATE_TARGETS:
        body = _target_body(text, target)
        offenders = [
            optional for optional in OPTIONAL_OBSERVABILITY_DIAGNOSTIC_TARGETS if optional in body
        ]
        assert offenders == [], (
            f"{target!r} must not depend on optional Langfuse diagnostics: {offenders}"
        )


def test_broad_unit_exclusions_are_defined_and_applied() -> None:
    """Exclusion variables must remain defined and applied in the broad test-unit lane.

    After #2638: archived optional targets are removed. Remaining exclusion variables
    keep the broad lane from collecting extras-dependent tests.
    """
    text = _makefile_text()

    # Variables must remain defined so the broad lane still excludes extras-dependent tests.
    required_vars = (
        "PYTEST_TELEGRAM_ADAPTER_PATHS",
        "PYTEST_TELEGRAM_ADAPTER_ROOT_TESTS",
    )
    for var_name in required_vars:
        assert f"$({var_name})" in text or f"{var_name} " in text, (
            f"{var_name} must remain defined in Makefile"
        )

    broad_body = _target_body(text, "test-unit")

    telegram_body = _target_body(text, "test-telegram-adapter")
    assert "--ignore" not in telegram_body
    assert "$(PYTEST_TELEGRAM_ADAPTER_IGNORE_GLOB)" not in telegram_body

    assert "$(PYTEST_OPTIONAL_ADAPTER_IGNORE)" in broad_body
    assert "$(PYTEST_OPTIONAL_ADAPTER_IGNORE_GLOB)" in broad_body
    # PYTEST_OPTIONAL_PROVIDER_IGNORE was retired with the legacy graph lane (#3220).
    assert "$(PYTEST_TELEGRAM_ADAPTER_IGNORE_GLOB)" in text
