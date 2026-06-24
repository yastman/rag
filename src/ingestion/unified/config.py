# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

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
            # Prefer neutral ``SYNC_DIR``; fall back to legacy ``GDRIVE_SYNC_DIR``
            os.getenv(
                "SYNC_DIR",
                os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync")),
            )
        )
    )
    manifest_dir: Path | None = field(
        default_factory=lambda: Path(v) if (v := os.getenv("MANIFEST_DIR")) else None
    )

    # Qdrant
    qdrant_url: str = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_api_key: str | None = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    collection_name: str = field(
        default_factory=lambda: (
            # Prefer neutral collection name env vars; fall back to legacy GDRIVE_COLLECTION_NAME
            os.getenv(
                "COLLECTION_NAME",
                os.getenv(
                    "UNIFIED_COLLECTION_NAME",
                    os.getenv("GDRIVE_COLLECTION_NAME", "file_documents_bge"),
                ),
            )
        )
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

    # BGE-M3 API (dense + sparse embeddings)
    bge_m3_url: str = field(
        default_factory=lambda: os.getenv("BGE_M3_URL", "http://localhost:8000")
    )
    bge_m3_timeout: float = field(default_factory=lambda: float(os.getenv("BGE_M3_TIMEOUT", "300")))
    bge_m3_concurrency: int = field(
        default_factory=lambda: int(os.getenv("BGE_M3_CONCURRENCY", "1"))
    )

    # Pipeline
    # Watch mode polls sync_dir every ``poll_interval_seconds`` (see flow.run_watch).
    poll_interval_seconds: int = 60
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
