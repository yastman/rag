"""Tests for optional native Docling adapter."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.ingestion.docling_native import DoclingNativeConfig, DoclingNativeConverter


def test_chunk_text_splits_by_token_window(tmp_path: Path):
    converter = DoclingNativeConverter(DoclingNativeConfig(max_tokens=3))

    class _Doc:
        def export_to_markdown(self) -> str:
            return "one two three four five six"

    class _Converter:
        def convert(self, _path: str):
            return SimpleNamespace(document=_Doc())

    with patch.object(
        DoclingNativeConverter,
        "_create_document_converter",
        return_value=_Converter(),
    ):
        chunks = converter.chunk_file_sync(tmp_path / "test.md")

    assert len(chunks) == 2
    assert chunks[0].text == "one two three"
    assert chunks[1].text == "four five six"


def test_chunk_file_sync_raises_when_docling_missing(tmp_path: Path):
    converter = DoclingNativeConverter()
    with patch.object(
        DoclingNativeConverter,
        "_create_document_converter",
        side_effect=ImportError("missing"),
    ):
        with pytest.raises(RuntimeError, match="not installed"):
            converter.chunk_file_sync(tmp_path / "test.md")
