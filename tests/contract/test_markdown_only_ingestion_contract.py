"""Contract: Markdown-only production ingestion authority (#3235).

Ensures the Docling-removal invariants hold permanently:

- src/ingestion accepts exactly ``.md`` (UnifiedConfig.supported_extensions
  and the parser suffix gate agree, and no converter suffix survives).
- The Docling adapter modules are gone and no production module imports
  ``docling`` or the removed ``src.ingestion.docling_*`` modules.
- No docling/docling-core/fastembed/transformers/torch/torchvision dependency
  remains in pyproject.toml or uv.lock (root lock has no CUDA wheels either).
- Dockerfile.ingestion installs no converter extra and carries no
  Docling/HuggingFace model pre-warm.
- services/docling and the old HTTP client stay absent; compose files never
  define a docling service or DOCLING_URL.

All tests are static (no live services required).
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_PACKAGES = (
    "docling",
    "docling-core",
    "docling-serve",
    "fastembed",
    "transformers",
    "torch",
    "torchvision",
)

REMOVED_INGESTION_MODULES = (
    "src/ingestion/docling_native.py",
    "src/ingestion/docling_common.py",
    "src/ingestion/docling_client.py",
)

FORBIDDEN_SUFFIXES = frozenset(
    {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".txt", ".html", ".htm", ".csv"}
)

# Compose files to scan for docling services and DOCLING_URL.
_COMPOSE_CANDIDATES = [
    "compose.yml",
    "compose.dev.yml",
    "compose.core.yml",
    "compose.vps.yml",
]


def _existing_compose_files() -> list[Path]:
    return [REPO_ROOT / name for name in _COMPOSE_CANDIDATES if (REPO_ROOT / name).exists()]


# ---------------------------------------------------------------------------
# 1. Supported extensions are exactly Markdown
# ---------------------------------------------------------------------------


def test_unified_config_supports_only_markdown() -> None:
    """UnifiedConfig.supported_extensions must be exactly {'.md'}."""
    from src.ingestion.unified.config import UnifiedConfig

    config = UnifiedConfig()
    assert config.supported_extensions == frozenset({".md"}), (
        "UnifiedConfig.supported_extensions must be exactly {'.md'} — "
        "production ingestion is Markdown-only (#3235)."
    )


def test_config_no_forbidden_suffixes() -> None:
    """No converter-era suffix may re-enter the supported set."""
    from src.ingestion.unified.config import UnifiedConfig

    extra = UnifiedConfig().supported_extensions & FORBIDDEN_SUFFIXES
    assert not extra, f"Converter-era suffixes re-appeared in supported_extensions: {extra!r}"


def test_markdown_parser_is_importable_without_converter_stack() -> None:
    """The parser must import cleanly with only the stdlib + core deps."""
    from src.ingestion.markdown import SUPPORTED_MARKDOWN_SUFFIXES, MarkdownParser

    assert {".md"} == SUPPORTED_MARKDOWN_SUFFIXES
    assert MarkdownParser is not None


def test_flow_has_no_converter_factory() -> None:
    """``_make_docling`` must stay gone; the parser factory is the authority."""
    import src.ingestion.unified.flow as flow_module

    assert not hasattr(flow_module, "_make_docling"), (
        "flow._make_docling was removed with Docling (#3235); "
        "flow._make_parser is the only parse-path factory."
    )
    assert hasattr(flow_module, "_make_parser")


# ---------------------------------------------------------------------------
# 2. Removed modules and import edges
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_path", REMOVED_INGESTION_MODULES)
def test_removed_ingestion_module_is_absent(module_path: str) -> None:
    target = REPO_ROOT / module_path
    assert not target.exists(), (
        f"{module_path} still exists; #3235 removed the Docling ingestion "
        "modules — they must stay deleted."
    )


def test_no_docling_import_edges_in_production_code() -> None:
    """No production module may import docling or the removed ingestion modules."""
    forbidden_imports = {
        "docling",
        "docling.document_converter",
        "docling_core",
        "src.ingestion.docling_native",
        "src.ingestion.docling_common",
        "src.ingestion.docling_client",
    }
    roots = ("src", "telegram_bot", "services", "scripts")
    violations: list[str] = []

    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in py_file.parts):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "") in forbidden_imports:
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}: {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_imports:
                            violations.append(f"{py_file.relative_to(REPO_ROOT)}: {alias.name}")

    assert not violations, (
        "Production modules still import the removed Docling stack:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# 3. Dependency authority — pyproject and uv.lock
# ---------------------------------------------------------------------------


def test_pyproject_has_no_docling_extra() -> None:
    """The docling-native extra must stay removed."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data.get("project", {}).get("optional-dependencies", {})
    for forbidden in ("docling-native", "ingest", "ingestion"):
        assert forbidden not in extras, (
            f"pyproject.toml re-introduced the '{forbidden}' extra; ingestion "
            "is Markdown-only and needs no converter dependencies (#3235)."
        )


def _pyproject_dependency_names() -> set[str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names: set[str] = set()

    def _scan(deps: list[str]) -> None:
        for dep in deps:
            names.add(dep.split(";")[0].split(">")[0].split("<")[0].split("=")[0].strip().lower())

    _scan(data.get("project", {}).get("dependencies", []))
    for extra_deps in data.get("project", {}).get("optional-dependencies", {}).values():
        _scan(extra_deps)
    return names


def test_pyproject_has_no_converter_dependencies() -> None:
    deps = _pyproject_dependency_names()
    for package in FORBIDDEN_PACKAGES:
        assert package not in deps, (
            f"pyproject.toml still declares '{package}'; #3235 removed the "
            "root converter/ML dependency stack."
        )


def test_uv_lock_has_no_converter_packages() -> None:
    """The frozen lock must not resolve the removed converter/ML stack."""
    lock_path = REPO_ROOT / "uv.lock"
    assert lock_path.exists(), "uv.lock not found in repo root."
    text = lock_path.read_text(encoding="utf-8")

    for line in text.splitlines():
        if line.startswith("name = "):
            name = line.removeprefix("name = ").strip().strip('"').lower()
            for package in FORBIDDEN_PACKAGES:
                assert name != package, (
                    f"uv.lock still resolves '{package}'; #3235 requires it to "
                    "be absent from the root environment."
                )


def test_uv_lock_no_cuda_wheels() -> None:
    """uv.lock must not contain CUDA or nvidia wheel references."""
    lock_path = REPO_ROOT / "uv.lock"
    text = lock_path.read_text(encoding="utf-8")

    violations = [
        line.strip()
        for line in text.splitlines()
        if any(marker in line.lower() for marker in ("nvidia-", "+cu", "+cuda", "cuda"))
    ]
    assert not violations, "uv.lock contains CUDA/nvidia wheel references:\n" + "\n".join(
        f"  {v}" for v in violations[:20]
    )


# ---------------------------------------------------------------------------
# 4. Docker and compose authority
# ---------------------------------------------------------------------------


def test_ingestion_dockerfile_is_converter_free() -> None:
    """Dockerfile.ingestion must not install the converter stack or pre-warm models."""
    path = REPO_ROOT / "Dockerfile.ingestion"
    assert path.exists(), "Dockerfile.ingestion not found in repo root."
    content = path.read_text(encoding="utf-8")

    assert "--extra docling-native" not in content, (
        "Dockerfile.ingestion still installs --extra docling-native; the "
        "extra was removed by #3235."
    )
    for stale_marker in ("docling", "DOCLING", "snapshot_download", "HF_HUB_CACHE"):
        assert stale_marker not in content, (
            f"Dockerfile.ingestion still references '{stale_marker}'; the "
            "Docling/HuggingFace model pre-warm layers were removed by #3235."
        )


def test_ingestion_entrypoint_has_no_model_cache_authority() -> None:
    """The entrypoint must not toggle HuggingFace offline mode anymore."""
    path = REPO_ROOT / "docker" / "ingestion" / "entrypoint.sh"
    assert path.exists(), "docker/ingestion/entrypoint.sh not found."
    content = path.read_text(encoding="utf-8")
    for stale_marker in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_CACHE"):
        assert stale_marker not in content, (
            f"docker/ingestion/entrypoint.sh still references '{stale_marker}'; "
            "the HuggingFace model-cache authority was removed by #3235."
        )


def test_compose_yml_no_docling_service() -> None:
    """compose.yml must not define a 'docling' service."""
    path = REPO_ROOT / "compose.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = data.get("services", {})
    assert "docling" not in services, "compose.yml still defines a 'docling' service."


def test_no_docling_url_in_compose_files() -> None:
    """No compose file may contain a DOCLING_URL environment variable."""
    violations = [
        path.name
        for path in _existing_compose_files()
        if "DOCLING_URL" in path.read_text(encoding="utf-8")
    ]
    assert not violations, f"DOCLING_URL found in compose file(s): {', '.join(violations)}."


def test_services_docling_directory_absent() -> None:
    """services/docling sidecar directory must not exist."""
    assert not (REPO_ROOT / "services" / "docling").exists(), (
        "services/docling/ still exists; it must stay deleted."
    )


def test_bot_dockerfile_no_converter_extra() -> None:
    """The bot image must not install the (removed) converter extra."""
    path = REPO_ROOT / "telegram_bot" / "Dockerfile"
    if not path.exists():
        pytest.skip("telegram_bot/Dockerfile does not exist in this checkout")
    assert "--extra docling-native" not in path.read_text(encoding="utf-8")
