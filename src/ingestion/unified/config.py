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

    # Database
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "INGESTION_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cocoindex"
        )
    )

    ***REMOVED***
    qdrant_url: str = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_api_key: str | None = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    collection_name: str = field(
        default_factory=lambda: os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_bge")
    )

    # Docling
    docling_url: str = field(
        default_factory=lambda: os.getenv("DOCLING_URL", "http://localhost:5001")
    )
    docling_timeout: float = 300.0
    max_tokens_per_chunk: int = 512

    ***REMOVED***
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
