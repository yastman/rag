# src/ingestion/unified/config.py
"""Configuration for unified ingestion pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UnifiedConfig:
    """Unified ingestion pipeline configuration."""

    # Paths
    sync_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync"))
        )
    )
    manifest_dir: Path | None = field(
        default_factory=lambda: Path(v) if (v := os.getenv("MANIFEST_DIR")) else None
    )

    # Database
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "INGESTION_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cocoindex"
        )
    )

    # Qdrant
    qdrant_url: str = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_api_key: str | None = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    collection_name: str = field(
        default_factory=lambda: os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_bge")
    )

    # Docling
    docling_backend: str = field(
        default_factory=lambda: os.getenv("DOCLING_BACKEND", "docling_http")
    )
    docling_url: str = field(
        default_factory=lambda: os.getenv("DOCLING_URL", "http://localhost:5001")
    )
    docling_timeout: float = 300.0
    max_tokens_per_chunk: int = 512

    # Voyage
    voyage_api_key: str = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY", ""))
    voyage_model: str = "voyage-4-large"

    # BGE-M3 API (dense + sparse embeddings)
    bge_m3_url: str = field(
        default_factory=lambda: os.getenv("BGE_M3_URL", "http://localhost:8000")
    )
    bge_m3_timeout: float = field(default_factory=lambda: float(os.getenv("BGE_M3_TIMEOUT", "300")))
    bge_m3_concurrency: int = field(
        default_factory=lambda: int(os.getenv("BGE_M3_CONCURRENCY", "1"))
    )
    use_local_embeddings: bool = field(
        default_factory=lambda: os.getenv("USE_LOCAL_DENSE_EMBEDDINGS", "false").lower() == "true"
    )

    # Pipeline
    # NOTE: Watch mode is handled by CocoIndex FlowLiveUpdater (no manual poll loop).
    poll_interval_seconds: int = 60
    max_retries: int = 3
    pipeline_version: str = "v3.2.1"

    # Supported extensions
    supported_extensions: frozenset[str] = frozenset(
        {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".md", ".txt", ".html", ".htm", ".csv"}
    )

    def __post_init__(self) -> None:
        """Validate config values that must stay within known rollout paths."""
        if self.docling_backend not in {"docling_http", "docling_native"}:
            raise ValueError(
                "DOCLING_BACKEND must be 'docling_http' or 'docling_native', "
                f"got {self.docling_backend!r}"
            )

    def effective_manifest_dir(self) -> Path:
        """Return writable directory for manifest storage.

        Uses MANIFEST_DIR if set, otherwise falls back to sync_dir.
        """
        return self.manifest_dir if self.manifest_dir is not None else self.sync_dir
