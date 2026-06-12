"""Contract: enforce the modular-monolith architecture law.

The full adapter migration is incremental, but the reusable layers must not gain
new reverse dependencies. These checks cover rules that can be enforced without
allowlists: provider/client code must not import runtime orchestration, and the
runtime graph builder default must stay runtime-owned rather than adapter-owned.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.runtime.graph import builder


REPO_ROOT = Path(__file__).resolve().parents[2]
PROVIDER_CLIENT_ROOTS = (
    REPO_ROOT / "src" / "services",
    REPO_ROOT / "src" / "providers",
)


def _imports_runtime(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "src.runtime" or module.startswith("src.runtime."):
                found.add(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "src.runtime" or alias.name.startswith("src.runtime."):
                    found.add(alias.name)
    return found


def test_provider_and_client_layers_do_not_import_runtime() -> None:
    violations: dict[str, list[str]] = {}
    for root in PROVIDER_CLIENT_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            imports = _imports_runtime(path)
            if imports:
                violations[path.relative_to(REPO_ROOT).as_posix()] = sorted(imports)

    assert not violations, (
        "Architecture law: providers/clients are below runtime and must not "
        f"import src.runtime orchestration. Violations: {violations}"
    )


def test_runtime_graph_default_factory_is_runtime_owned() -> None:
    assert builder.DEFAULT_FACTORY_SPEC.startswith("src.runtime."), (
        "Architecture law: runtime graph default must be runtime-owned; adapters "
        "can opt in with RAG_GRAPH_FACTORY but src.runtime must not default to one."
    )
    assert "telegram_bot" not in builder.DEFAULT_FACTORY_SPEC
