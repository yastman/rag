"""Contract: assistant core boundaries must not grow Telegram/runtime coupling.

The simplification roadmap is moving core orchestration behind explicit
runtime contracts. Until that migration is complete, ``src/core`` has a small
known set of compatibility imports. This ratchet prevents new static or dynamic
imports from creeping into the assistant core while later PRs shrink the
allowlist.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = REPO_ROOT / "src" / "core"

ALLOWED_TELEGRAM_IMPORTS = {
    "src/core/assistant.py": {
        "telegram_bot.agents.rag_pipeline",
        "telegram_bot.pipelines.state_contract",
        "telegram_bot.services.generate_response",
    },
}

FORBIDDEN_RUNTIME_PREFIXES = (
    "aiogram",
    "fastapi",
    "k8s",
    "mini_app",
    "src.api",
    "src.voice",
    "telegram_bot",
)


def _module_roots(module: str) -> tuple[str, ...]:
    parts = module.split(".")
    if not parts:
        return ()
    if parts[0] == "src" and len(parts) >= 2:
        return (parts[0], f"{parts[0]}.{parts[1]}")
    return (parts[0],)


def _is_forbidden(module: str) -> bool:
    roots = _module_roots(module)
    return any(
        module == prefix or module.startswith(f"{prefix}.") or prefix in roots
        for prefix in FORBIDDEN_RUNTIME_PREFIXES
    )


def _literal_import_module_name(node: ast.Call) -> str | None:
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    ):
        return None
    return node.args[0].value


def _collect_forbidden_imports() -> dict[str, list[str]]:
    violations: dict[str, set[str]] = {}
    for path in sorted(CORE_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = ALLOWED_TELEGRAM_IMPORTS.get(rel, set())

        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.append(node.module)
            elif isinstance(node, ast.Call):
                dynamic_module = _literal_import_module_name(node)
                if dynamic_module:
                    modules.append(dynamic_module)

            for module in modules:
                if _is_forbidden(module) and module not in allowed:
                    violations.setdefault(rel, set()).add(module)

    return {path: sorted(modules) for path, modules in violations.items()}


def test_src_core_has_no_new_runtime_surface_imports() -> None:
    violations = _collect_forbidden_imports()
    assert not violations, (
        "src/core must not add Telegram, transport, API, voice, Mini App, or k8s "
        "coupling. Move shared runtime behavior under src.runtime or add a "
        f"documented shrink-only exception. Violations: {violations}"
    )


def test_core_telegram_allowlist_stays_small_and_explicit() -> None:
    assert {
        "src/core/assistant.py": {
            "telegram_bot.agents.rag_pipeline",
            "telegram_bot.pipelines.state_contract",
            "telegram_bot.services.generate_response",
        },
    } == ALLOWED_TELEGRAM_IMPORTS
