"""Contract: DEPS-9 keeps Boto3/GCS packages out of runtime dependencies."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_LOCK = ROOT / "uv.lock"
TELEGRAM_LOCK = ROOT / "telegram_bot" / "uv.lock"
AUDIT_DOC = ROOT / "docs" / "engineering" / "dependency-audits" / "boto-google-cloud-deps.md"
FORBIDDEN_DIRECT_PACKAGES = {
    "boto3",
    "botocore",
    "google-cloud-storage",
    "google-auth",
    "google-cloud-core",
    "google-crc32c",
    "google-resumable-media",
}
GOOGLEAPIS_COMMON_PROTOS = "googleapis-common-protos"
ALLOWED_GOOGLEAPIS_PARENTS = {
    "opentelemetry-exporter-otlp-proto-grpc",
    "opentelemetry-exporter-otlp-proto-http",
}
RUNTIME_DIRS = (ROOT / "src", ROOT / "telegram_bot")


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _lock_package_names(path: Path) -> set[str]:
    data = _load_toml(path)
    return {package["name"] for package in data.get("package", [])}


def _reverse_lock_dependencies(path: Path) -> dict[str, set[str]]:
    data = _load_toml(path)
    reverse: dict[str, set[str]] = {}
    for package in data.get("package", []):
        parent = package["name"]
        for dep in package.get("dependencies", []) or []:
            reverse.setdefault(dep["name"], set()).add(parent)
    return reverse


def _project_dependencies(path: Path) -> set[str]:
    data = _load_toml(path)
    deps = data["project"].get("dependencies", [])
    return {dep.split("[", 1)[0].split("<", 1)[0].split(">", 1)[0].split("=", 1)[0].lower() for dep in deps}


def test_root_and_telegram_base_deps_do_not_include_boto_or_gcs_packages() -> None:
    for pyproject in (ROOT / "pyproject.toml", ROOT / "telegram_bot" / "pyproject.toml"):
        deps = _project_dependencies(pyproject)
        assert deps.isdisjoint(FORBIDDEN_DIRECT_PACKAGES | {GOOGLEAPIS_COMMON_PROTOS})


def test_root_lock_excludes_boto_and_google_cloud_storage_packages() -> None:
    packages = _lock_package_names(ROOT_LOCK)
    assert packages.isdisjoint(FORBIDDEN_DIRECT_PACKAGES)


def test_googleapis_common_protos_is_only_transitive_from_otel_exporters_when_present() -> None:
    for lock_path in (ROOT_LOCK, TELEGRAM_LOCK):
        packages = _lock_package_names(lock_path)
        if GOOGLEAPIS_COMMON_PROTOS not in packages:
            continue
        parents = _reverse_lock_dependencies(lock_path).get(GOOGLEAPIS_COMMON_PROTOS, set())
        assert parents
        assert parents <= ALLOWED_GOOGLEAPIS_PARENTS


def test_runtime_code_does_not_import_boto_or_google_cloud_modules() -> None:
    violations: list[str] = []
    for base in RUNTIME_DIRS:
        for py_file in base.rglob("*.py"):
            rel = py_file.relative_to(ROOT)
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in {"boto3", "botocore"} or alias.name.startswith(("google.cloud", "google.auth")):
                            violations.append(f"{rel}:{node.lineno} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module in {"boto3", "botocore"} or module.startswith(("google.cloud", "google.auth")):
                        violations.append(f"{rel}:{node.lineno} imports from {module}")
    assert violations == []


def test_dependency_audit_document_records_transitive_owner() -> None:
    text = AUDIT_DOC.read_text(encoding="utf-8")
    assert "docling-serve[ui]" in text
    assert "opentelemetry-exporter-otlp-proto-http" in text
    assert "PR #2447" in text
