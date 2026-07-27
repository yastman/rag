"""Contract: local meeting-RAG SDK pins and supported API seams."""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import inspect
import os
import tomllib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ROOT_PYPROJECT = ROOT / "pyproject.toml"
ROOT_LOCK = ROOT / "uv.lock"
BGE_PYPROJECT = ROOT / "services" / "bge-m3-api" / "pyproject.toml"
BGE_LOCK = ROOT / "services" / "bge-m3-api" / "uv.lock"

BASELINE = {
    "docling": "2.115.0",
    "docling-core": "2.87.1",
    "litellm": "1.93.0",
    "qdrant-client": "1.18.0",
    "fastapi": "0.140.0",
    "uvicorn": "0.51.0",
    "aiohttp": "3.14.3",
}
ROOT_DIRECT = {
    "qdrant-client",
    "litellm",
    "aiohttp",
}
ROOT_EXTRAS = {
    "docling-native": {"docling", "docling-core"},
    "bge-extras": {"fastapi", "uvicorn"},
}
BGE_DIRECT = {"fastapi", "uvicorn"}
SDK_ROOTS = {"aiohttp", "docling", "docling_core", "fastapi", "litellm", "qdrant_client", "uvicorn"}
SOURCE_TREES = (
    ROOT / "src",
    ROOT / "scripts",
    ROOT / "telegram_bot",
    ROOT / "services" / "bge-m3-api",
)


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _requirement_versions(requirements: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for requirement in requirements:
        name = requirement.split("[", 1)[0].split("=", 1)[0].split(">", 1)[0].split("<", 1)[0]
        versions[name.strip().lower()] = requirement.partition("==")[2]
    return versions


def _locked_versions(path: Path) -> dict[str, str]:
    return {package["name"]: package["version"] for package in _load_toml(path)["package"]}


def _imported_sdk_symbols() -> set[tuple[str, str]]:
    symbols: set[tuple[str, str]] = set()
    ignored_directories = {".tox", ".venv", "__pycache__", "venv"}
    for source_tree in SOURCE_TREES:
        for directory, directories, filenames in os.walk(source_tree):
            directories[:] = [name for name in directories if name not in ignored_directories]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                path = Path(directory) / filename
                module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(module):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.split(".", 1)[0] in SDK_ROOTS:
                                symbols.add((alias.name, ""))
                    elif (
                        isinstance(node, ast.ImportFrom)
                        and node.module
                        and node.module.split(".", 1)[0] in SDK_ROOTS
                    ):
                        symbols.update((node.module, alias.name) for alias in node.names)
    return symbols


def _assert_importable_sdk_symbols(*roots: str) -> None:
    allowed_roots = set(roots)
    for module_name, symbol_name in sorted(_imported_sdk_symbols()):
        if module_name.split(".", 1)[0] not in allowed_roots:
            continue
        module = importlib.import_module(module_name)
        if symbol_name:
            assert hasattr(module, symbol_name), (
                f"{module_name}.{symbol_name} is required by source"
            )


def test_manifests_pin_the_local_rag_sdk_baseline() -> None:
    root = _load_toml(ROOT_PYPROJECT)["project"]
    root_direct = _requirement_versions(root["dependencies"])
    for name in ROOT_DIRECT:
        assert root_direct[name] == BASELINE[name]

    extras = root["optional-dependencies"]
    for extra, names in ROOT_EXTRAS.items():
        versions = _requirement_versions(extras[extra])
        for name in names:
            assert versions[name] == BASELINE[name]

    bge_direct = _requirement_versions(_load_toml(BGE_PYPROJECT)["project"]["dependencies"])
    for name in BGE_DIRECT:
        assert bge_direct[name] == BASELINE[name]


def test_root_and_bge_locks_resolve_the_same_sdk_baseline() -> None:
    root_versions = _locked_versions(ROOT_LOCK)
    bge_versions = _locked_versions(BGE_LOCK)

    for name, version in BASELINE.items():
        if name in {"fastapi", "uvicorn"}:
            assert root_versions[name] == version
            assert bge_versions[name] == version
        else:
            assert root_versions[name] == version


def _require_modules(*modules: str) -> None:
    missing = [module for module in modules if importlib.util.find_spec(module) is None]
    if missing:
        pytest.skip(f"Install the matching SDK extra to verify imports: {', '.join(missing)}")


def _assert_versions(*distributions: str) -> None:
    for distribution in distributions:
        assert importlib.metadata.version(distribution) == BASELINE[distribution]


def test_docling_sdk_import_and_api_contract() -> None:
    _require_modules("docling", "docling_core")
    _assert_importable_sdk_symbols("docling", "docling_core")

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling_core.transforms.chunker import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    assert InputFormat.PDF
    assert callable(DocumentConverter)
    assert callable(PdfFormatOption)
    assert {"do_ocr", "do_table_structure"}.issubset(
        inspect.signature(PdfPipelineOptions).parameters
    )
    assert callable(HybridChunker)
    assert {"tokenizer", "merge_peers"}.issubset(inspect.signature(HybridChunker).parameters)
    assert callable(HuggingFaceTokenizer.from_pretrained)
    _assert_versions("docling", "docling-core")


def test_litellm_sdk_import_and_api_contract() -> None:
    _require_modules("litellm")
    _assert_importable_sdk_symbols("litellm")

    from litellm import Router, acompletion

    assert callable(acompletion)
    assert callable(Router.acompletion)
    _assert_versions("litellm")


def test_qdrant_sdk_import_and_api_contract() -> None:
    _require_modules("qdrant_client")
    _assert_importable_sdk_symbols("qdrant_client")

    from qdrant_client import AsyncQdrantClient, QdrantClient

    for method in ("count", "create_payload_index", "get_collection"):
        assert callable(getattr(QdrantClient, method))
    for method in (
        "get_aliases",
        "query_points",
        "query_points_groups",
        "update_collection",
        "update_collection_aliases",
    ):
        assert callable(getattr(AsyncQdrantClient, method))
    assert {"api_key", "prefer_grpc", "timeout", "url"}.issubset(
        inspect.signature(AsyncQdrantClient).parameters
    )
    _assert_versions("qdrant-client")


def test_fastapi_sdk_import_and_api_contract() -> None:
    _require_modules("fastapi")
    _assert_importable_sdk_symbols("fastapi")

    from fastapi import FastAPI

    assert "lifespan" in inspect.signature(FastAPI).parameters
    _assert_versions("fastapi")


def test_uvicorn_sdk_import_and_api_contract() -> None:
    _require_modules("uvicorn")
    _assert_importable_sdk_symbols("uvicorn")

    uvicorn = importlib.import_module("uvicorn")
    assert {"app", "host", "port"}.issubset(inspect.signature(uvicorn.run).parameters)
    _assert_versions("uvicorn")


def test_aiohttp_sdk_import_and_api_contract() -> None:
    _require_modules("aiohttp")

    from aiohttp import ClientSession

    assert callable(ClientSession.close)
    _assert_versions("aiohttp")
