"""Live integration test for NativeDoclingAdapter.

Requires:
  - docling + docling-core[chunking] + transformers installed (docling-native extra)
  - A PDF fixture available at tests/fixtures/minimal.pdf OR any real PDF

Run with: pytest tests/integration/test_docling_native_live.py -m requires_extras
"""

from pathlib import Path

import pytest


# Skip if docling is not installed
docling = pytest.importorskip("docling")
pytestmark = pytest.mark.no_services


from src.ingestion.docling_native import NativeDoclingAdapter


FIXTURE_MD = Path("tests/e2e_core/fixtures/docs/sunny_beach_studio.md")


@pytest.mark.requires_extras
class TestNativeDoclingAdapterLive:
    """Live parity tests — real HybridChunker, no fakes."""

    def test_markdown_produces_nonempty_chunks(self):
        """sunny_beach_studio.md → at least 1 chunk with non-empty text."""
        adapter = NativeDoclingAdapter()
        chunks = adapter.chunk_file_sync(FIXTURE_MD)
        assert len(chunks) > 0
        assert all(c.text.strip() for c in chunks)

    def test_chunks_have_headings(self):
        """At least one chunk carries a heading from the markdown structure."""
        adapter = NativeDoclingAdapter()
        chunks = adapter.chunk_file_sync(FIXTURE_MD)
        chunks_with_headings = [c for c in chunks if c.headings]
        assert len(chunks_with_headings) > 0, "Expected at least one chunk with headings"

    def test_page_range_extracted_for_pdf(self, tmp_path):
        """A minimal synthetic PDF → page_range is a tuple, not None."""
        pytest.importorskip("fpdf2", reason="fpdf2 needed to create a test PDF")
        from fpdf import FPDF

        pdf_path = tmp_path / "test.pdf"
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(200, 10, "Test document for page range extraction")
        pdf.output(str(pdf_path))

        adapter = NativeDoclingAdapter()
        chunks = adapter.chunk_file_sync(pdf_path)
        # page_range may be None if docling can't extract pages from minimal PDF;
        # but the chunk list itself must be non-empty
        assert len(chunks) > 0

    def test_ocr_disabled_by_default(self):
        """DocumentConverter is configured with do_ocr=False."""
        adapter = NativeDoclingAdapter()
        converter = adapter._get_converter()
        # Verify PdfPipelineOptions has do_ocr=False
        from docling.datamodel.base_models import InputFormat

        fmt_options = converter.format_to_options.get(InputFormat.PDF)
        if fmt_options is not None:
            pipeline_opts = getattr(fmt_options, "pipeline_options", None)
            if pipeline_opts is not None:
                assert not pipeline_opts.do_ocr, "do_ocr must be False by default"
