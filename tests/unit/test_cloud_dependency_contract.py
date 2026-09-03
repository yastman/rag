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

# #3227: litellm 1.98.0 promoted boto3 from its optional "proxy" extra to a hard
# dependency (`boto3<2.0,>=1.43.1`), so the AWS cohort is now unavoidably present
# in the lock as a LiteLLM transitive. The product still must not declare or
# import it (guards below), and the Google Cloud cohort remains fully banned.
LITELLM_TRANSITIVE_AWS_EXEMPT = {"boto3", "botocore", "s3transfer", "jmespath"}


def _dependency_names() -> set[str]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
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
    text = LOCKFILE.read_text(encoding="utf-8")
    for package in FORBIDDEN_LOCKED_STORAGE_CLIENTS:
        if package in LITELLM_TRANSITIVE_AWS_EXEMPT:
            continue  # #3227: litellm 1.98.0 hard-requires boto3; see LITELLM_TRANSITIVE_AWS_EXEMPT
        assert f'name = "{package}"' not in text


def test_aws_sdk_is_locked_only_as_litellm_transitive() -> None:
    """The exempted AWS cohort must stay transitive: litellm pulls it, we never declare it."""
    import importlib.metadata as metadata

    requires = {r.split(";")[0].strip().lower() for r in metadata.requires("litellm") or []}
    assert any(r.startswith("boto3") for r in requires), (
        "Exemption assumes boto3 is a litellm requirement; if litellm drops it, "
        "remove LITELLM_TRANSITIVE_AWS_EXEMPT and re-ban the AWS cohort in the lock guard."
    )


def test_runtime_code_does_not_import_cloud_storage_sdks() -> None:
    offenders: list[str] = []
    for root in RUNTIME_ROOTS:
        for path in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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
