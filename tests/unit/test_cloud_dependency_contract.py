"""Regression guard for AWS/Google Cloud dependency audit (#2451)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")
LOCKFILE = Path("uv.lock")
RUNTIME_ROOTS = [Path("src"), Path("telegram_bot")]
FORBIDDEN_DIRECT = {
    "boto3",
    "botocore",
    "google-cloud-storage",
    "google-auth",
    "google-cloud-core",
    "google-crc32c",
    "google-resumable-media",
    "googleapis-common-protos",
}
FORBIDDEN_LOCKED_STORAGE_CLIENTS = FORBIDDEN_DIRECT - {"googleapis-common-protos"}


def _dependency_names() -> set[str]:
    project = tomllib.loads(PYPROJECT.read_text())
    names: set[str] = set()

    def add(deps: list[str]) -> None:
        for dep in deps:
            match = re.match(r"([A-Za-z0-9_.-]+)", dep)
            assert match, f"Could not parse dependency {dep!r}"
            names.add(match.group(1).lower().replace("_", "-"))

    add(project["project"].get("dependencies", []))
    for deps in project["project"].get("optional-dependencies", {}).values():
        add(deps)
    for deps in project.get("dependency-groups", {}).values():
        add(deps)
    return names


def test_aws_google_cloud_sdks_are_not_declared_dependencies() -> None:
    assert _dependency_names().isdisjoint(FORBIDDEN_DIRECT)


def test_aws_google_cloud_storage_clients_are_not_locked() -> None:
    text = LOCKFILE.read_text()
    for package in FORBIDDEN_LOCKED_STORAGE_CLIENTS:
        assert f'name = "{package}"' not in text


def test_googleapis_common_protos_is_only_opentelemetry_transitive() -> None:
    text = LOCKFILE.read_text()

    assert 'name = "googleapis-common-protos"' in text
    assert 'name = "opentelemetry-exporter-otlp-proto-grpc"' in text
    assert 'name = "opentelemetry-exporter-otlp-proto-http"' in text
    assert text.count('{ name = "googleapis-common-protos" }') == 2


def test_runtime_code_does_not_import_cloud_storage_sdks() -> None:
    offenders: list[str] = []
    for root in RUNTIME_ROOTS:
        for path in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                imported: set[str] = set()
                if isinstance(node, ast.Import):
                    imported = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = {node.module}
                if any(
                    name in {"boto3", "botocore", "google.cloud"}
                    or name.startswith(("google.cloud.", "google.auth"))
                    for name in imported
                ):
                    offenders.append(f"{path}:{node.lineno}")
    assert not offenders
