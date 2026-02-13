"""Test that no global sys.modules pollution occurs during test runs."""

import sys

import pytest


def test_no_global_sys_modules_patching():
    """Verify tests don't pollute sys.modules at import time.

    All sys.modules mocking MUST be fixture-scoped, not global.
    Rationale:
    - Global patching affects test isolation
    - Prevents pytest-xdist from working correctly
    - Can cause flaky tests due to import order
    """
    # These modules should only exist if actually installed
    forbidden_mocks = [
        "redisvl",
        "redisvl.query",
        "redisvl.query.filter",
    ]

    for module_name in forbidden_mocks:
        if module_name in sys.modules:
            module = sys.modules[module_name]
            # Real redisvl has __file__ attribute
            if not hasattr(module, "__file__"):
                pytest.fail(
                    f"Global sys.modules mock detected: {module_name}. "
                    f"Use @pytest.fixture with monkeypatch instead."
                )


def test_langfuse_not_globally_mocked():
    """Langfuse mock must be fixture-scoped, not global."""
    if "langfuse" in sys.modules:
        module = sys.modules["langfuse"]
        # Real langfuse has __version__ attribute
        if not hasattr(module, "__version__"):
            pytest.fail(
                "Global langfuse mock detected. Use @pytest.fixture(autouse=True) "
                "with monkeypatch.setitem(sys.modules, ...) instead."
            )
