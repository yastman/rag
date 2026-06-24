"""Regression tests for Docling service Dockerfile."""

import tomllib
from pathlib import Path


def test_docling_dockerfile_uses_uv_sync_with_lockfile() -> None:
    text = Path("services/docling/Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen --no-dev --no-install-project --extra docling" in text, (
        "services/docling/Dockerfile must use lockfile-backed uv sync with docling extra"
    )


def test_docling_dockerfile_copies_lockfile_artifacts() -> None:
    text = Path("services/docling/Dockerfile").read_text(encoding="utf-8")
    assert "pyproject.toml" in text, (
        "services/docling/Dockerfile must copy pyproject.toml for uv sync"
    )
    assert "uv.lock" in text, (
        "services/docling/Dockerfile must copy uv.lock for reproducible builds"
    )


def test_docling_dockerfile_has_dockerignore() -> None:
    assert Path("services/docling/.dockerignore").exists(), (
        "services/docling/.dockerignore must exist"
    )


def test_docling_service_lock_uses_cpu_only_pytorch() -> None:
    """Docling image must not regress to CUDA PyTorch wheels."""
    pyproject = tomllib.loads(Path("services/docling/pyproject.toml").read_text())
    sources = pyproject["tool"]["uv"]["sources"]
    indexes = pyproject["tool"]["uv"]["index"]

    assert any(
        index["name"] == "pytorch-cpu"
        and index["url"] == "https://download.pytorch.org/whl/cpu"
        and index["explicit"] is True
        for index in indexes
    )
    assert sources["torch"] == [{"index": "pytorch-cpu"}]
    assert sources["torchvision"] == [{"index": "pytorch-cpu"}]

    lock_text = Path("services/docling/uv.lock").read_text(encoding="utf-8")
    locked_package_names = {
        package["name"] for package in tomllib.loads(lock_text).get("package", [])
    }
    assert "https://download.pytorch.org/whl/cpu" in lock_text
    assert "+cpu" in lock_text
    forbidden_cuda_packages = (
        "cuda-bindings",
        "cuda-toolkit",
        "nvidia-cublas",
        "nvidia-cudnn",
        "nvidia-cufft",
        "nvidia-cusolver",
        "nvidia-cusparse",
        "nvidia-nccl",
        "triton",
    )
    assert not locked_package_names.intersection(forbidden_cuda_packages)
    assert not any(name.startswith("nvidia-") for name in locked_package_names)


def test_compose_docling_uses_canonical_pdf_backend() -> None:
    """compose.yml DOCLING_PDF_BACKEND must use canonical docling_parse, not alias dlparse_v4."""
    text = Path("compose.yml").read_text(encoding="utf-8")
    assert "DOCLING_PDF_BACKEND: docling_parse" in text
    assert "dlparse_v4" not in text
    assert "dlparse_v2" not in text


def test_compose_docling_table_mode_is_fast() -> None:
    """compose.yml DOCLING_TABLE_MODE must be fast (per-request overrides for heavy profiles)."""
    text = Path("compose.yml").read_text(encoding="utf-8")
    assert "DOCLING_TABLE_MODE: fast" in text


def test_docling_client_profiles_use_canonical_pdf_backend() -> None:
    """All docling_client.py profiles must use canonical docling_parse backend."""
    text = Path("src/ingestion/docling_client.py").read_text(encoding="utf-8")
    assert "dlparse_v4" not in text
    assert "dlparse_v2" not in text


def test_dockerfile_docling_no_dlparse_backend() -> None:
    """services/docling/Dockerfile must not reference deprecated dlparse_v* backends."""
    import re

    text = Path("services/docling/Dockerfile").read_text(encoding="utf-8")
    assert not re.search(r"dlparse_v[0-9]", text), (
        "services/docling/Dockerfile must not contain deprecated dlparse_v* backend references"
    )
