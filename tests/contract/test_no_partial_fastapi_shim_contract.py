"""Contract: no test installs a partial fake ``fastapi`` module into ``sys.modules`` (#2009).

Issue #2009 documented a fast-lane regression where
``tests/unit/api/test_rag_api_runtime.py`` installed an incomplete
``_FakeFastAPI`` / ``_FakeJSONResponse`` shim into ``sys.modules`` so it
could import ``src.api.main`` without the optional FastAPI dependency.

Two ways the shim caused trouble:

* If the import after the shim install raised, the cleanup pop never ran
  and the partial module leaked into the rest of the worker, turning
  ``pytest.importorskip("fastapi")`` calls in Mini App tests into
  ``ImportError: cannot import name 'Depends' from 'fastapi'``.
* Even when cleanup ran, the bound classes inside ``src.api.main`` kept
  references to the shim, so any test that re-imported the module later
  in the same worker saw a chimera.

The supported pattern is ``pytest.importorskip("fastapi")`` at module
top, which skips cleanly when the optional dep is missing. This contract
test forbids the pattern that caused the regression so the fast lane
stays deterministic after a plain ``uv sync``.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

# Guard scope: any test that touches FastAPI lives in one of these subtrees.
SCAN_ROOTS = (
    REPO_ROOT / "tests" / "unit" / "api",
    REPO_ROOT / "tests" / "unit" / "mini_app",
    REPO_ROOT / "tests" / "contract",
)


def _python_test_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        files.extend(sorted(root.rglob("test_*.py")))
    # Exclude this contract test itself; it intentionally documents the
    # forbidden patterns.
    self_path = Path(__file__).resolve()
    return [p for p in files if p.resolve() != self_path]


@pytest.mark.parametrize("test_path", _python_test_files(), ids=lambda p: p.name)
def test_no_partial_fastapi_shim_in_sys_modules(test_path: Path) -> None:
    # Patterns that indicate a partial fake-module install. The literal
    # ``sys.modules["fastapi"] =`` assignment is the smoking gun; the
    # ``_FakeFastAPI`` / ``_FakeJSONResponse`` class names came from the
    # regression in tests/unit/api/test_rag_api_runtime.py before #2009.
    #
    # NOTE: keep this tuple inside the test function body. The sibling
    # ``tests/unit/test_module_pollution.py::test_no_module_level_sys_modules_assignment``
    # AST guard scans only top-level statements for the literal
    # ``sys.modules[`` + ``=`` substring, so a module-level constant here
    # would self-trip that guard. Building the tuple inside the function
    # keeps both contracts honest without a guard exemption.
    forbidden_patterns = (
        'sys.modules["fastapi"] =',
        "sys.modules['fastapi'] =",
        'sys.modules["fastapi.responses"] =',
        "sys.modules['fastapi.responses'] =",
        "_FakeFastAPI",
        "_FakeJSONResponse",
    )

    text = test_path.read_text(encoding="utf-8")
    found = [pat for pat in forbidden_patterns if pat in text]
    assert not found, (
        f"#2009: {test_path.relative_to(REPO_ROOT)} installs a partial fake fastapi module "
        f"({found}). Use pytest.importorskip('fastapi', reason=...) at module top instead so "
        "the fast lane skips cleanly when the optional dep is absent."
    )


def test_rag_api_runtime_uses_importorskip() -> None:
    target = REPO_ROOT / "tests" / "unit" / "api" / "test_rag_api_runtime.py"
    assert target.exists(), "expected tests/unit/api/test_rag_api_runtime.py to exist"
    text = target.read_text(encoding="utf-8")
    assert 'pytest.importorskip("fastapi"' in text or "pytest.importorskip('fastapi'" in text, (
        "#2009: tests/unit/api/test_rag_api_runtime.py must use pytest.importorskip('fastapi') "
        "at module top to opt out cleanly when FastAPI is not installed (canonical fast lane)."
    )
