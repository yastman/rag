"""Guard: docling-native extra importability.

Verifies that the critical imports for NativeDoclingAdapter are available
when the docling-native extra is installed.
"""

import importlib

import pytest


pytestmark = pytest.mark.requires_extras


@pytest.mark.no_services
def test_docling_common_importable():
    """src.ingestion.docling_common must always be importable."""
    m = importlib.import_module("src.ingestion.docling_common")
    assert hasattr(m, "DoclingChunk")
    assert hasattr(m, "SUPPORTED_FORMATS")
    assert hasattr(m, "to_ingestion_chunks")


@pytest.mark.no_services
def test_native_adapter_importable():
    """NativeDoclingAdapter must be importable (lazy-loads docling at runtime)."""
    from src.ingestion.docling_native import NativeDoclingAdapter

    assert NativeDoclingAdapter is not None


def test_docling_core_hybrid_chunker_importable():
    """HybridChunker from docling_core must be importable with docling-native extra."""
    pytest.importorskip("docling_core")
    from docling_core.transforms.chunker import HybridChunker

    assert HybridChunker is not None


def test_huggingface_tokenizer_importable():
    """HuggingFaceTokenizer must be importable with docling-native extra."""
    pytest.importorskip("docling_core")
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    assert HuggingFaceTokenizer is not None
