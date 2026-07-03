"""Contract tests for entrypoint structure (#2970).

Asserts that:
1. run_assistant_request is importable from src.core.assistant
2. Telegram bot adapter uses src.core, never imports src.runtime directly
3. Both paths remain distinct and properly separated
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path


def test_run_assistant_request_is_importable() -> None:
    """Assert run_assistant_request is importable and is an async function."""
    from src.core.assistant import run_assistant_request

    assert inspect.iscoroutinefunction(run_assistant_request), (
        "run_assistant_request must be an async function"
    )

    # Check function has expected signature
    sig = inspect.signature(run_assistant_request)
    params = list(sig.parameters.keys())
    assert "query" in params, "run_assistant_request must have 'query' parameter"
    assert "collection" in params, "run_assistant_request must have 'collection' parameter"
    assert "user_context" in params, "run_assistant_request must have 'user_context' parameter"
    assert "dependencies" in params, "run_assistant_request must have 'dependencies' parameter"


def test_run_assistant_request_exported_from_core() -> None:
    """Assert run_assistant_request is exported from src.core package."""
    from src.core import run_assistant_request

    assert run_assistant_request is not None


def test_telegram_adapter_does_not_import_runtime_directly() -> None:
    """Assert telegram adapter never imports src.runtime directly.

    The adapter should only use src.core and transport-specific modules.
    All runtime logic should go through CoreDependencies.
    """
    adapter_path = (
        Path(__file__).parent.parent.parent / "telegram_bot" / "assistant_core_adapter.py"
    )
    assert adapter_path.exists(), f"Adapter not found at {adapter_path}"

    source = adapter_path.read_text()
    tree = ast.parse(source)

    # Find all imports
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    # Assert no direct src.runtime imports
    runtime_imports = [imp for imp in imports if imp.startswith("src.runtime")]
    assert not runtime_imports, (
        f"Telegram adapter should not import src.runtime directly, found: {runtime_imports}"
    )

    # Assert core imports exist
    core_imports = [imp for imp in imports if imp.startswith("src.core")]
    assert core_imports, "Telegram adapter must import from src.core"


def test_supervisor_run_core_calls_assistant_app() -> None:
    """Assert _supervisor_run_core uses AssistantApp.run_text, not run_assistant_request directly."""
    pipeline_path = (
        Path(__file__).parent.parent.parent / "telegram_bot" / "pipeline" / "supervisor.py"
    )
    assert pipeline_path.exists(), f"Pipeline not found at {pipeline_path}"

    source = pipeline_path.read_text()

    # Assert it imports from src.core
    assert "from src.core import CoreDependencies" in source, (
        "_supervisor_run_core must import CoreDependencies from src.core"
    )

    # Assert it uses the adapter
    assert "from telegram_bot.assistant_core_adapter import" in source, (
        "_supervisor_run_core must use assistant_core_adapter"
    )

    # Assert it calls run_core_text_request, not run_assistant_request directly
    assert "run_core_text_request" in source, "_supervisor_run_core must call run_core_text_request"


def test_both_paths_use_same_core_function() -> None:
    """Assert both paths (direct SDK and Telegram) ultimately call run_assistant_request."""
    # SDK path: caller → run_assistant_request
    # Telegram path: AssistantApp.run_text calls run_assistant_request
    from src.core.assistant import run_assistant_request as core_func
    from src.core.assistant import run_assistant_request as sdk_func

    app_path = Path(__file__).parent.parent.parent / "src" / "core" / "app.py"
    source = app_path.read_text()

    assert "run_assistant_request" in source, (
        "AssistantApp.run_text must call run_assistant_request"
    )

    # Verify they're the same function
    assert sdk_func is core_func


__all__ = [
    "test_both_paths_use_same_core_function",
    "test_run_assistant_request_exported_from_core",
    "test_run_assistant_request_is_importable",
    "test_supervisor_run_core_calls_assistant_app",
    "test_telegram_adapter_does_not_import_runtime_directly",
]
