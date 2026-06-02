"""Contract: every integration/smoke test file must carry a service-dependency marker (#2324 Phase 1.1).

``no_services`` and ``requires_services`` are pytest custom markers registered in
``pyproject.toml``. This contract walks ``tests/integration/test_*.py`` and
``tests/smoke/test_*.py`` and enforces:

1. Every file has exactly one file-level service-dependency marker.
2. No file has both markers simultaneously.
3. All markers in use are registered in ``pyproject.toml``.
4. The marker set in this contract stays synced with the registered set.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATION_DIR = REPO_ROOT / "tests" / "integration"
SMOKE_DIR = REPO_ROOT / "tests" / "smoke"

# The two registered service-dependency markers.
SERVICE_DEPENDENCY_MARKERS = frozenset({"no_services", "requires_services"})

# Other markers that are harmless at module level and don't signal service dependency.
# These are either injected by conftest or are unrelated lane/behavior markers.
_IGNORED_MODULE_MARKERS = frozenset(
    {
        "unit",
        "integration",
        "smoke",
        "slow",
        "chaos",
        "load",
        "e2e",
        "benchmark",
        "contract",
        "baseline",
        "performance",
        "regression",
        "requires_extras",
        "kommo",
        "asyncio",
        "xdist_group",
        "legacy_api",
        "skipif",
        "skip",
    }
)


def _parse_pytest_markers(
    source: str,
) -> tuple[set[str], int | None, int | None]:
    """Parse an AST to discover module-level pytestmark assignments.

    Returns ``(marker_names, pytestmark_line, import_line)`` where
    ``import_line`` is the line number of ``import pytest`` (if present)
    and ``pytestmark_line`` is the line number of any top-level
    ``pytestmark`` assignment.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return (set(), None, None)

    markers: set[str] = set()
    pytestmark_line: int | None = None
    import_line: int | None = None

    for node in ast.walk(tree):
        # Find `import pytest`
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "pytest":
                        import_line = node.lineno
            elif node.module == "pytest":
                import_line = node.lineno

    # Walk top-level statements for pytestmark assignments
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                pytestmark_line = node.lineno

                # Single marker: pytestmark = pytest.mark.X(...)
                if isinstance(node.value, ast.Call) and _is_pytestmark_attr(node.value.func):
                    markers.add(_pytestmark_attr_name(node.value.func))
                # List of markers: pytestmark = [pytest.mark.X, pytest.mark.Y(...)]
                elif isinstance(node.value, ast.List):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Call) and _is_pytestmark_attr(elt.func):
                            markers.add(_pytestmark_attr_name(elt.func))
                        elif isinstance(elt, ast.Attribute) and _is_pytestmark_attr(elt):
                            markers.add(_pytestmark_attr_name(elt))
                # pytestmark = pytest.mark.X  (no call parens)
                elif isinstance(node.value, ast.Attribute) and _is_pytestmark_attr(node.value):
                    markers.add(_pytestmark_attr_name(node.value))

    return (markers, pytestmark_line, import_line)


def _is_pytestmark_attr(node: ast.expr) -> bool:
    """True if node is ``pytest.mark.X`` or ``pytest.mark.X(...)``."""
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _pytestmark_attr_name(node: ast.expr) -> str:
    """Return ``X`` from ``pytest.mark.X``."""
    assert isinstance(node, ast.Attribute)
    return node.attr


def _collect_issues() -> list[str]:
    """Return a list of human-readable issues found across integration/smoke dirs."""
    issues: list[str] = []
    for directory, _label in [
        (INTEGRATION_DIR, "integration"),
        (SMOKE_DIR, "smoke"),
    ]:
        if not directory.exists():
            continue
        for path in sorted(directory.glob("test_*.py")):
            rel = path.relative_to(REPO_ROOT)
            source = path.read_text(encoding="utf-8")
            markers, _marker_line, _import_line = _parse_pytest_markers(source)

            sd_markers = markers & SERVICE_DEPENDENCY_MARKERS

            if len(sd_markers) == 0:
                issues.append(
                    f"  - {rel}: MISSING service-dependency marker "
                    f"(add exactly one of: no_services, requires_services)"
                )
            elif len(sd_markers) > 1:
                issues.append(f"  - {rel}: has BOTH {sorted(sd_markers)}; keep exactly one")

            # Check for unregistered markers in pytestmark
            unknown = markers - SERVICE_DEPENDENCY_MARKERS - _IGNORED_MODULE_MARKERS
            if unknown:
                issues.append(f"  - {rel}: uses unregistered module marker(s): {sorted(unknown)}")

    return issues


def test_service_dependency_marker_registration_synced() -> None:
    """SERVICE_DEPENDENCY_MARKERS must match what's registered in pyproject.toml."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Extract marker names from the markers list
    found = set(re.findall(r'"([a-z0-9_]+): ', pyproject))
    expected = SERVICE_DEPENDENCY_MARKERS
    assert expected <= found, (
        "SERVICE_DEPENDENCY_MARKERS must be a subset of registered markers in "
        f"pyproject.toml. Expected {sorted(expected)}, found {sorted(found)}."
    )


def test_all_integration_and_smoke_files_are_classified() -> None:
    """Every integration/smoke test file must carry exactly one service marker."""
    issues = _collect_issues()
    if issues:
        raise AssertionError(
            "Service-dependency marker violations in tests/integration/ and "
            "tests/smoke/:\n\n"
            + "\n".join(issues)
            + "\n\nAdd exactly one file-level service-dependency marker "
            "(pytestmark = pytest.mark.no_services or "
            "pytestmark = pytest.mark.requires_services) to each file listed "
            "above."
        )
