"""Contract: the disabled client-direct duplicate pipeline is removed (#3215).

``CLIENT_DIRECT_PIPELINE_ENABLED`` defaulted to false. When enabled, the client
pipeline sent an answer that the supervisor then sent again, duplicated
classify/cache/retrieve/generate work, and carried a keyword intent branch.
#3215 deletes that alternate so the supervisor runs the assistant core for
every text query (mirroring the ARCH-16 removal pinned in
``test_telegram_text_path_convergence_contract.py``).

Pins:
- ``telegram_bot/pipelines/client.py`` no longer exists.
- The ``CLIENT_DIRECT_PIPELINE_ENABLED`` / ``client_direct_pipeline_enabled``
  flag no longer appears in bot source, ``.env.example``, or ``compose.yml``.
- The supervisor and ``bot.py`` no longer define the client-direct handler or
  the free-text apartment fast path it dispatched.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

CLIENT_PIPELINE = REPO_ROOT / "telegram_bot" / "pipelines" / "client.py"
SUPERVISOR = REPO_ROOT / "telegram_bot" / "pipeline" / "supervisor.py"
BOT = REPO_ROOT / "telegram_bot" / "bot.py"

FLAG_STRINGS = ("CLIENT_DIRECT_PIPELINE_ENABLED", "client_direct_pipeline_enabled")
REMOVED_FUNCTIONS = ("_handle_client_direct_pipeline", "_handle_apartment_fast_path")
REMOVED_CALLABLES = ("run_client_pipeline", "infer_agent_intent", "detect_agent_intent")


def _defined_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_client_pipeline_module_removed() -> None:
    """telegram_bot/pipelines/client.py must not exist."""
    assert not CLIENT_PIPELINE.exists(), (
        "#3215: telegram_bot/pipelines/client.py was reintroduced. The disabled "
        "client-direct duplicate pipeline stays deleted; route text queries "
        "through the assistant core."
    )


def test_client_direct_flag_removed_from_surface() -> None:
    """The flag must not appear in bot source, .env.example, or compose.yml."""
    surfaces = [
        REPO_ROOT / ".env.example",
        REPO_ROOT / "compose.yml",
        REPO_ROOT / "telegram_bot" / "config.py",
        SUPERVISOR,
        BOT,
    ]
    for surface in surfaces:
        text = surface.read_text(encoding="utf-8")
        for flag in FLAG_STRINGS:
            assert flag not in text, (
                f"#3215: {flag} still present in {surface.relative_to(REPO_ROOT)}. "
                "The client-direct flag surface stays removed."
            )


def test_supervisor_and_bot_do_not_define_removed_handlers() -> None:
    """The client-direct handler and its apartment fast path must stay gone."""
    for path in (SUPERVISOR, BOT):
        defined = _defined_function_names(path)
        for name in REMOVED_FUNCTIONS:
            assert name not in defined, (
                f"#3215: {path.relative_to(REPO_ROOT)} redefines {name}. "
                "The duplicate send/generation branch stays removed."
            )


def test_bot_source_does_not_call_client_pipeline() -> None:
    """No telegram_bot module may reference the removed client pipeline callables."""
    for path in (REPO_ROOT / "telegram_bot").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for callable_name in REMOVED_CALLABLES:
            assert callable_name not in text, (
                f"#3215: {path.relative_to(REPO_ROOT)} references {callable_name}. "
                "The client pipeline entrypoints stay removed."
            )
