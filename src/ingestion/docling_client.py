"""Docling-serve HTTP client for document conversion and chunking.

Integrates with docling-serve container for PDF/DOCX/HTML parsing
and HybridChunker for RAG-optimized chunking.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from src.ingestion.chunker import Chunk


logger = logging.getLogger(__name__)


@dataclass
class DoclingConfig:
    """Configuration for docling-serve client."""

    base_url: str = "http://localhost:5001"
    timeout: float = 300.0  # Long timeout for large documents
    max_tokens: int = 512  # Optimal for Voyage-4-large
    merge_peers: bool = True  # Merge undersized peer chunks
    tokenizer: str = "word"  # word | huggingface
    pdf_backend: str = "dlparse_v2"  # Best table parsing
    table_mode: str = "accurate"  # accurate | fast
    do_ocr: bool = False  # Enable for scanned documents


@dataclass
class ConvertedDocument:
    """Result of document conversion."""

    content: str
    source: str
    source_type: str
    page_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoclingChunk:
    """Chunk from docling's HybridChunker with rich metadata."""

    text: str
    seq_no: int
    headings: list[str] = field(default_factory=list)
    page_range: Optional[tuple[int, int]] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DoclingClient:
    """Client for docling-serve HTTP API.

    Provides:
    - Document conversion (PDF, DOCX, HTML, etc.)
    - HybridChunker with contextualization
    - Batch processing support
    """

    SUPPORTED_FORMATS = {".pdf", ".docx", ".doc", ".html", ".htm", ".md", ".txt", ".xlsx", ".csv"}

    def __init__(self, config: Optional[DoclingConfig] = None):
        """Initialize client.

        Args:
            config: Client configuration (defaults to DoclingConfig())
        """
        self.config = config or DoclingConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "DoclingClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with DoclingClient()' or call connect()")
        return self._client

    async def connect(self) -> None:
        """Connect client (alternative to context manager)."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )

    async def close(self) -> None:
        """Close client connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check if docling-serve is healthy.

        Returns:
            True if service is healthy
        """
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    async def convert_file(self, file_path: Path) -> ConvertedDocument:
        """Convert document file to text.

        Args:
            file_path: Path to document file

        Returns:
            ConvertedDocument with extracted text and metadata
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        # Prepare multipart form data
        with open(file_path, "rb") as f:
            files = {"files": (file_path.name, f, self._get_mime_type(suffix))}

            response = await self.client.post(
                "/v1/convert/file",
                files=files,
                data={
                    "convert_do_ocr": str(self.config.do_ocr).lower(),
                    "convert_pdf_backend": self.config.pdf_backend,
                },
            )

        response.raise_for_status()
        result = response.json()

        # Extract converted content
        documents = result.get("documents", [])
        if not documents:
            raise ValueError("No documents returned from conversion")

        doc = documents[0]
        return ConvertedDocument(
            content=doc.get("md_content", doc.get("text", "")),
            source=file_path.name,
            source_type=suffix.lstrip("."),
            page_count=doc.get("page_count", 0),
            metadata=doc.get("metadata", {}),
        )

    async def chunk_file(
        self,
        file_path: Path,
        contextualize: bool = True,
    ) -> list[DoclingChunk]:
        """Convert and chunk document file using HybridChunker.

        Args:
            file_path: Path to document file
            contextualize: Whether to add hierarchical context to chunks

        Returns:
            List of DoclingChunk with rich metadata
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        # Prepare multipart form data
        with open(file_path, "rb") as f:
            files = {"files": (file_path.name, f, self._get_mime_type(suffix))}

            response = await self.client.post(
                "/v1/chunk/hybrid/file",
                files=files,
                data={
                    "convert_do_ocr": str(self.config.do_ocr).lower(),
                    "convert_pdf_backend": self.config.pdf_backend,
                    "chunking_max_tokens": str(self.config.max_tokens),
                    "chunking_tokenizer": self.config.tokenizer,
                    "chunking_merge_peers": str(self.config.merge_peers).lower(),
                    "include_converted_doc": "false",
                },
            )

        response.raise_for_status()
        result = response.json()

        # Parse chunks
        chunks = []
        raw_chunks = result.get("chunks", [])

        for raw_chunk in raw_chunks:
            # Extract text - contextualized if available
            text = raw_chunk.get("contextualized_text") or raw_chunk.get("text", "")
            if not text:
                continue

            chunk = DoclingChunk(
                text=text,
                seq_no=raw_chunk.get("seq_no", len(chunks)),
                headings=raw_chunk.get("headings", []),
                page_range=self._parse_page_range(raw_chunk.get("meta", {})),
                metadata=raw_chunk.get("meta", {}),
            )
            chunks.append(chunk)

        logger.info(f"Chunked {file_path.name}: {len(chunks)} chunks")
        return chunks

    def to_ingestion_chunks(
        self,
        docling_chunks: list[DoclingChunk],
        source: str,
        source_type: str = "docling",
    ) -> list[Chunk]:
        """Convert DoclingChunks to standard Chunk objects for indexing.

        Args:
            docling_chunks: Chunks from chunk_file()
            source: Source filename or identifier
            source_type: Type identifier (pdf, docx, gdrive, etc.)

        Returns:
            List of Chunk objects compatible with VoyageIndexer
        """
        # Generate document hash for doc_id
        doc_id = self._generate_doc_id(source)
        created_at = datetime.now(timezone.utc).isoformat()

        chunks = []
        for i, dc in enumerate(docling_chunks):
            # Build extra metadata with unified schema
            extra_metadata = {
                "doc_id": doc_id,
                "source": source,
                "source_type": source_type,
                "created_at": created_at,
                "chunk_order": i,  # Explicit alias for small-to-big
            }

            # Add page range if available
            if dc.page_range:
                extra_metadata["page_range"] = list(dc.page_range)

            # Add section from headings
            if dc.headings:
                extra_metadata["section"] = " > ".join(dc.headings)

            # Include original docling metadata
            if dc.metadata:
                extra_metadata["docling_meta"] = dc.metadata

            chunk = Chunk(
                text=dc.text,
                chunk_id=i,
                document_name=source,
                article_number=doc_id,  # Use doc_id as article_number
                section=" > ".join(dc.headings) if dc.headings else None,
                page_range=dc.page_range,
                order=i,
                extra_metadata=extra_metadata,
            )
            chunks.append(chunk)

        return chunks

    @staticmethod
    def _generate_doc_id(source: str) -> str:
        """Generate document ID from source name (SHA-256 prefix)."""
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    @staticmethod
    def _get_mime_type(suffix: str) -> str:
        """Get MIME type for file extension."""
        mime_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".html": "text/html",
            ".htm": "text/html",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".csv": "text/csv",
        }
        return mime_types.get(suffix, "application/octet-stream")

    @staticmethod
    def _parse_page_range(meta: dict[str, Any]) -> Optional[tuple[int, int]]:
        """Parse page range from chunk metadata."""
        page_start = meta.get("page_start") or meta.get("page")
        page_end = meta.get("page_end") or page_start

        if page_start is not None:
            return (int(page_start), int(page_end or page_start))
        return None


async def chunk_document(
    file_path: Path,
    docling_url: str = "http://localhost:5001",
    max_tokens: int = 512,
) -> list[Chunk]:
    """Convenience function to chunk a document file.

    Args:
        file_path: Path to document file
        docling_url: Docling-serve URL
        max_tokens: Maximum tokens per chunk

    Returns:
        List of Chunk objects ready for indexing
    """
    config = DoclingConfig(base_url=docling_url, max_tokens=max_tokens)

    async with DoclingClient(config) as client:
        docling_chunks = await client.chunk_file(file_path)
        return client.to_ingestion_chunks(
            docling_chunks,
            source=file_path.name,
            source_type=file_path.suffix.lstrip("."),
        )
