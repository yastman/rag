"""Contract: DEPS-OBS1 removes monolith OpenTelemetry auto-instrumentation."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
_AUTO_INSTRUMENTATION_PREFIX = "opentelemetry-instrumentation-"
_ALLOWED_SRC_OTEL_ENV_FILES = {
    Path("src/observability.py"),
    Path("src/observability_bootstrap.py"),
}


def _project_dependencies(path: Path) -> list[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return list(data["project"].get("dependencies", []))


def test_root_base_dependencies_do_not_include_otel_auto_instrumentation() -> None:
    deps = _project_dependencies(ROOT / "pyproject.toml")
    forbidden = [dep for dep in deps if dep.startswith(_AUTO_INSTRUMENTATION_PREFIX)]
    assert forbidden == []


def test_telegram_bot_base_dependencies_do_not_include_otel_auto_instrumentation() -> None:
    deps = _project_dependencies(ROOT / "telegram_bot" / "pyproject.toml")
    forbidden = [dep for dep in deps if dep.startswith(_AUTO_INSTRUMENTATION_PREFIX)]
    assert forbidden == []


def test_src_and_telegram_bot_do_not_import_opentelemetry_runtime_modules() -> None:
    violations: list[str] = []
    for base in (ROOT / "src", ROOT / "telegram_bot"):
        for file_path in base.rglob("*.py"):
            rel = file_path.relative_to(ROOT)
            if rel in _ALLOWED_SRC_OTEL_ENV_FILES:
                # These files may mention OTEL env var names but must not import OTel.
                pass
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(rel))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "opentelemetry" or alias.name.startswith("opentelemetry."):
                            violations.append(f"{rel}:{node.lineno} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "opentelemetry" or module.startswith("opentelemetry."):
                        violations.append(f"{rel}:{node.lineno} imports from {module}")
    assert violations == []


def test_shared_otel_auto_instrumentation_module_is_removed() -> None:
    assert not (ROOT / "src" / "observability_otel.py").exists()
