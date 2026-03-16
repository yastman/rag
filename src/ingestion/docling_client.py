"""Docling-serve HTTP client for document conversion and chunking.

Integrates with docling-serve container for PDF/DOCX/HTML parsing
and HybridChunker for RAG-optimized chunking.
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx

from src.ingestion.chunker import Chunk


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile presets for docling-serve conversion
# ---------------------------------------------------------------------------

_PROFILE_SETTINGS: dict[str, dict[str, Any]] = {
    "speed": {
        "do_ocr": False,
        "force_ocr": False,
        "ocr_engine": None,
        "table_mode": "fast",
        "pdf_backend": "dlparse_v4",
        "pipeline": None,
    },
    "quality": {
        "do_ocr": True,
        "force_ocr": False,
        "ocr_engine": "easyocr",
        "table_mode": "accurate",
        "pdf_backend": "dlparse_v4",
        "pipeline": None,
    },
    "scan": {
        "do_ocr": True,
        "force_ocr": True,
        "ocr_engine": "easyocr",
        "table_mode": "accurate",
        "pdf_backend": "dlparse_v4",
        "pipeline": None,
    },
    "vlm": {
        "do_ocr": False,
        "force_ocr": False,
        "ocr_engine": None,
        "table_mode": "accurate",
        "pdf_backend": "dlparse_v4",
        "pipeline": "vlm",
    },
}

VALID_PROFILES = frozenset(_PROFILE_SETTINGS)


def get_profile_settings(profile: str) -> dict[str, Any]:
    """Return docling-serve conversion settings for *profile*.

    Args:
        profile: One of "speed", "quality", "scan", "vlm".

    Returns:
        Dict with keys: do_ocr, force_ocr, ocr_engine, table_mode,
        pdf_backend, pipeline.

    Raises:
        ValueError: If *profile* is not recognised.
    """
    if profile not in _PROFILE_SETTINGS:
        raise ValueError(
            f"Unknown docling profile {profile!r}. "
            f"Valid profiles: {', '.join(sorted(VALID_PROFILES))}"
        )
    # Return a copy so callers cannot mutate the module-level dict.
    return dict(_PROFILE_SETTINGS[profile])


@dataclass
class DoclingConfig:
    """Configuration for docling-serve client."""

    base_url: str = "http://localhost:5001"
    timeout: float = 300.0  # Long timeout for large documents
    max_tokens: int = 512  # Optimal for Voyage-4-large
    merge_peers: bool = True  # Merge undersized peer chunks
    # docling-serve expects a HuggingFace model name (string) for `chunking_tokenizer`.
    # If omitted, docling-serve uses its server-side default tokenizer.
    #
    # NOTE: Earlier versions of this client used values like "word" / "huggingface",
    # but the HTTP API does not support those and may return 0 chunks while still
    # responding with HTTP 200.
    tokenizer: str | None = None
    pdf_backend: str = "dlparse_v4"  # Best table parsing (2026)
    table_mode: str = "accurate"  # accurate | fast
    do_ocr: bool = False  # Enable for scanned documents

    # Profile-based settings (from DOCLING_PROFILE env, default "speed")
    profile: str = field(default_factory=lambda: os.getenv("DOCLING_PROFILE", "speed"))
    ocr_engine: str | None = None  # auto, easyocr, rapidocr, tesserocr, tesseract
    force_ocr: bool = False  # Replace existing text with OCR output
    pipeline: str | None = None  # Processing pipeline (None = standard, "vlm" = VLM)

    def __post_init__(self) -> None:
        """Apply profile defaults for fields left at their init defaults."""
        if self.profile not in _PROFILE_SETTINGS:
            logger.warning(
                "Unknown DOCLING_PROFILE %r, falling back to 'speed'",
                self.profile,
            )
            self.profile = "speed"

        settings = get_profile_settings(self.profile)
        # Profile sets defaults — explicit constructor args take priority.
        # We detect "not explicitly set" by checking against the dataclass
        # field defaults.  For mutable/factory defaults this is tricky, so
        # we simply always apply the profile for the new fields that had no
        # previous presence in the config.
        if not self.force_ocr and settings["force_ocr"]:
            self.force_ocr = settings["force_ocr"]
        if self.ocr_engine is None:
            self.ocr_engine = settings["ocr_engine"]
        if self.pipeline is None:
            self.pipeline = settings["pipeline"]
        # do_ocr / table_mode / pdf_backend have dataclass defaults that may
        # differ from the chosen profile.  Override them when the current value
        # still matches the dataclass default (i.e. the caller didn't pass a
        # custom value via the constructor).
        if not self.do_ocr and settings["do_ocr"]:
            self.do_ocr = settings["do_ocr"]
        if self.table_mode == "accurate" and settings["table_mode"] != "accurate":
            self.table_mode = settings["table_mode"]
        if self.pdf_backend == "dlparse_v4" and settings["pdf_backend"] != "dlparse_v4":
            self.pdf_backend = settings["pdf_backend"]

        logger.debug(
            "DoclingConfig profile=%s do_ocr=%s force_ocr=%s ocr_engine=%s "
            "pipeline=%s table_mode=%s pdf_backend=%s",
            self.profile,
            self.do_ocr,
            self.force_ocr,
            self.ocr_engine,
            self.pipeline,
            self.table_mode,
            self.pdf_backend,
        )


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
    page_range: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DoclingClient:
    """Client for docling-serve HTTP API.

    Provides:
    - Document conversion (PDF, DOCX, HTML, etc.)
    - HybridChunker with contextualization
    - Batch processing support
    """

    SUPPORTED_FORMATS = {".pdf", ".docx", ".doc", ".html", ".htm", ".md", ".txt", ".xlsx", ".csv"}

    def __init__(self, config: DoclingConfig | None = None):
        """Initialize client.

        Args:
            config: Client configuration (defaults to DoclingConfig())
        """
        self.config = config or DoclingConfig()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "DoclingClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            transport=httpx.AsyncHTTPTransport(retries=3),
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
            raise RuntimeError(
                "Client not initialized. Use 'async with DoclingClient()' or call connect()"
            )
        return self._client

    async def connect(self) -> None:
        """Connect client (alternative to context manager)."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
            transport=httpx.AsyncHTTPTransport(retries=3),
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
        async_path = anyio.Path(file_path)
        if not await async_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        # Prepare multipart form data - read file into memory to avoid
        # async context issues with file handles
        file_content = await async_path.read_bytes()
        files = {"files": (file_path.name, file_content, self._get_mime_type(suffix))}

        response = await self.client.post(
            "/v1/convert/file",
            files=files,
            data=self._build_convert_form_data(),
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
        async_path = anyio.Path(file_path)
        if not await async_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {suffix}")

        # Prepare multipart form data - read file into memory to avoid
        # async context issues with file handles
        file_content = await async_path.read_bytes()
        files = {"files": (file_path.name, file_content, self._get_mime_type(suffix))}

        data = self._build_chunking_form_data()
        response = await self.client.post(
            "/v1/chunk/hybrid/file",
            files=files,
            data=data,
        )

        response.raise_for_status()
        result = response.json()

        # Parse chunks
        chunks: list[DoclingChunk] = []
        raw_chunks = result.get("chunks", [])

        if raw_chunks == []:
            logger.warning(
                "Docling returned 0 chunks for %s (status=%s). "
                "This often happens when sending an invalid `chunking_tokenizer` value. "
                "Sent form fields: %s",
                file_path.name,
                response.status_code,
                sorted(data.keys()),
            )

        for raw_chunk in raw_chunks:
            # Respect caller preference: contextualized text or raw text.
            text = (
                raw_chunk.get("contextualized_text") if contextualize else raw_chunk.get("text")
            ) or raw_chunk.get("text", "")
            if not text:
                continue

            chunk = DoclingChunk(
                text=text,
                seq_no=raw_chunk.get("seq_no", raw_chunk.get("chunk_index", len(chunks))),
                headings=raw_chunk.get("headings", []),
                page_range=self._parse_page_range_from_chunk(raw_chunk),
                metadata=raw_chunk.get("meta") or raw_chunk.get("metadata", {}),
            )
            chunks.append(chunk)

        logger.info(f"Chunked {file_path.name}: {len(chunks)} chunks")
        return chunks

    def chunk_file_sync(
        self,
        file_path: Path,
        contextualize: bool = True,
    ) -> list[DoclingChunk]:
        """Sync version of chunk_file() for CocoIndex target.

        Uses a fresh httpx client per call to avoid loop mismatch issues.
        Does NOT reuse self._client (which is async and bound to another loop).

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

        # Use sync httpx client (NOT self._client which is async)
        with httpx.Client(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        ) as client:
            file_content = file_path.read_bytes()
            files = {"files": (file_path.name, file_content, self._get_mime_type(suffix))}
            data = self._build_chunking_form_data()

            response = client.post("/v1/chunk/hybrid/file", files=files, data=data)
            response.raise_for_status()
            result = response.json()

        # Parse chunks
        chunks: list[DoclingChunk] = []
        raw_chunks = result.get("chunks", [])

        if raw_chunks == []:
            logger.warning(
                "Docling returned 0 chunks for %s (status=%s).",
                file_path.name,
                response.status_code,
            )

        for raw_chunk in raw_chunks:
            text = (
                raw_chunk.get("contextualized_text") if contextualize else raw_chunk.get("text")
            ) or raw_chunk.get("text", "")
            if not text:
                continue

            chunk = DoclingChunk(
                text=text,
                seq_no=raw_chunk.get("seq_no", raw_chunk.get("chunk_index", len(chunks))),
                headings=raw_chunk.get("headings", []),
                page_range=self._parse_page_range_from_chunk(raw_chunk),
                metadata=raw_chunk.get("meta") or raw_chunk.get("metadata", {}),
            )
            chunks.append(chunk)

        logger.info(f"Chunked (sync) {file_path.name}: {len(chunks)} chunks")
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
        created_at = datetime.now(UTC).isoformat()

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
    def _parse_page_range(meta: dict[str, Any]) -> tuple[int, int] | None:
        """Parse page range from chunk metadata."""
        page_start = meta.get("page_start") or meta.get("page")
        page_end = meta.get("page_end") or page_start

        if page_start is not None:
            return (int(page_start), int(page_end or page_start))
        return None

    def _build_convert_form_data(self) -> dict[str, str]:
        """Build multipart form fields for /v1/convert/file."""
        data: dict[str, str] = {
            "convert_do_ocr": str(self.config.do_ocr).lower(),
            "convert_pdf_backend": self.config.pdf_backend,
            "convert_table_mode": self.config.table_mode,
        }
        if self.config.force_ocr:
            data["convert_force_ocr"] = "true"
        if self.config.ocr_engine:
            data["convert_ocr_engine"] = self.config.ocr_engine
        if self.config.pipeline:
            data["convert_pipeline"] = self.config.pipeline
        return data

    def _build_chunking_form_data(self) -> dict[str, str]:
        """Build multipart form fields for /v1/chunk/hybrid/file."""
        data = self._build_convert_form_data()
        data.update(
            {
                "chunking_max_tokens": str(self.config.max_tokens),
                "chunking_merge_peers": str(self.config.merge_peers).lower(),
                "include_converted_doc": "false",
            }
        )

        # docling-serve expects a HF model id, not "word"/"huggingface".
        tokenizer = (self.config.tokenizer or "").strip()
        if tokenizer and tokenizer not in {"word", "huggingface"}:
            data["chunking_tokenizer"] = tokenizer

        return data

    def _parse_page_range_from_chunk(self, raw_chunk: dict[str, Any]) -> tuple[int, int] | None:
        """Parse page range from a docling-serve chunk payload."""
        # Current docling-serve returns `page_numbers: []` on each chunk.
        page_numbers = raw_chunk.get("page_numbers")
        if isinstance(page_numbers, list) and page_numbers:
            try:
                nums = [int(p) for p in page_numbers if p is not None]
            except (TypeError, ValueError):
                nums = []
            if nums:
                return (min(nums), max(nums))

        # Backward/alternate formats
        meta = raw_chunk.get("meta") or raw_chunk.get("metadata") or {}
        if isinstance(meta, dict):
            return self._parse_page_range(meta)

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
