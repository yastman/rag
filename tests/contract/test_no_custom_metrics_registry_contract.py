"""Contract: DEPS-OBS3 removes custom Prometheus metrics from monolith core."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [REPO_ROOT / "src", REPO_ROOT / "telegram_bot"]
_ALLOWED_PROMETHEUS_TEXT = {
    Path("src/evaluation/metrics_logger.py"),  # eval-only text export helper
}


def _dependencies(path: Path) -> list[str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return list(data["project"].get("dependencies", []))


def test_root_base_dependencies_do_not_include_prometheus_client() -> None:
    assert not any(dep.startswith("prometheus-client") for dep in _dependencies(REPO_ROOT / "pyproject.toml"))


def test_telegram_base_dependencies_do_not_include_prometheus_client() -> None:
    assert not any(
        dep.startswith("prometheus-client")
        for dep in _dependencies(REPO_ROOT / "telegram_bot" / "pyproject.toml")
    )


def test_core_runtime_does_not_import_prometheus_client() -> None:
    violations: list[str] = []
    for base in SCAN_DIRS:
        for py_file in base.rglob("*.py"):
            rel = py_file.relative_to(REPO_ROOT)
            if rel in _ALLOWED_PROMETHEUS_TEXT:
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "prometheus_client" or alias.name.startswith("prometheus_client."):
                            violations.append(f"{rel}:{node.lineno} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "prometheus_client" or module.startswith("prometheus_client."):
                        violations.append(f"{rel}:{node.lineno} imports from {module}")
    assert violations == []


def test_pipeline_metrics_use_product_event_logs() -> None:
    text = (REPO_ROOT / "src/runtime/services/metrics.py").read_text(encoding="utf-8")
    assert "from src.utils.product_events import log_event" in text
    assert "prometheus_client" not in text
    assert "pipeline_latency" in text
    assert "pipeline_counter" in text
