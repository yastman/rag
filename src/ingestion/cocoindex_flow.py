"""CocoIndex flow definitions for document ingestion.

Defines data transformation flows for ingesting documents into Qdrant
using Voyage AI embeddings. Uses CocoIndex's incremental processing
and data lineage features.

Milestone J: Document Ingestion Pipeline (2026-02-02)
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray


try:
    import cocoindex
    from cocoindex import DataScope, FlowBuilder

    COCOINDEX_AVAILABLE = True
except ImportError:
    COCOINDEX_AVAILABLE = False
    cocoindex = None  # type: ignore
    FlowBuilder = Any  # type: ignore
    DataScope = Any  # type: ignore


logger = logging.getLogger(__name__)


@dataclass
class FlowConfig:
    """Configuration for CocoIndex flows."""

    # Qdrant settings
    qdrant_url: str = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    qdrant_api_key: str | None = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    collection_name: str = "documents"

    # Chunking settings
    chunk_size: int = 512  # Tokens per chunk
    chunk_overlap: int = 50  # Overlap between chunks

    # Voyage settings
    voyage_api_key: str | None = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY"))
    voyage_model: str = "voyage-4-large"
    vector_size: int = 1024

    # Refresh interval for watching directories
    refresh_interval_seconds: int = 60


def check_cocoindex_available() -> bool:
    """Check if CocoIndex is available."""
    return COCOINDEX_AVAILABLE


class VoyageEmbedFunction:
    """CocoIndex-compatible embedding function using Voyage AI.

    This class wraps VoyageService for use with CocoIndex's transform system.
    It handles batching and async-to-sync conversion internally.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "voyage-4-large",
    ):
        """Initialize Voyage embedding function.

        Args:
            api_key: Voyage API key (defaults to VOYAGE_API_KEY env var)
            model: Voyage model name
        """
        resolved_api_key = api_key if api_key is not None else os.getenv("VOYAGE_API_KEY")
        self.api_key: str = resolved_api_key or ""
        self.model = model
        self._service: Any | None = None

    @property
    def service(self) -> Any:
        """Lazy-load VoyageService."""
        if self._service is None:
            from telegram_bot.services import VoyageService

            self._service = VoyageService(
                api_key=self.api_key,
                model_docs=self.model,
            )
        return self._service

    def __call__(self, texts: list[str]) -> list[NDArray[np.float32]]:
        """Embed texts using Voyage AI.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        import asyncio

        async def _embed():
            return await self.service.embed_documents(texts)

        # Run async in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a new task
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _embed())
                    embeddings = future.result()
            else:
                embeddings = loop.run_until_complete(_embed())
        except RuntimeError:
            embeddings = asyncio.run(_embed())

        return [np.array(emb, dtype=np.float32) for emb in embeddings]


def create_document_flow(
    config: FlowConfig | None = None,
    source_path: str = "documents",
) -> Any | None:
    """Create a CocoIndex flow for document ingestion.

    This flow:
    1. Reads documents from a local directory
    2. Splits content into chunks
    3. Generates Voyage AI embeddings
    4. Exports to Qdrant vector database

    Args:
        config: Flow configuration (defaults to FlowConfig())
        source_path: Path to document directory

    Returns:
        CocoIndex flow object, or None if CocoIndex not available
    """
    if not COCOINDEX_AVAILABLE:
        logger.warning("CocoIndex not available, cannot create flow")
        return None

    config = config or FlowConfig()

    @cocoindex.flow_def(name="DocumentIngestion")
    def document_ingestion_flow(
        flow_builder: FlowBuilder,
        data_scope: DataScope,
    ) -> None:
        """CocoIndex flow for document ingestion."""
        # Add source: local file directory
        data_scope["documents"] = flow_builder.add_source(
            cocoindex.sources.LocalFile(path=source_path),
            refresh_interval=timedelta(seconds=config.refresh_interval_seconds),
        )

        # Create collector for output
        doc_embeddings = data_scope.add_collector()

        # Process each document
        with data_scope["documents"].row() as doc:
            # Split document into chunks
            doc["chunks"] = doc["content"].transform(
                cocoindex.functions.SplitRecursively(),
                language="markdown",
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
            )

            # Process each chunk
            with doc["chunks"].row() as chunk:
                # Generate embedding using Voyage AI
                embed_fn = VoyageEmbedFunction(
                    api_key=config.voyage_api_key,
                    model=config.voyage_model,
                )

                chunk["embedding"] = chunk["text"].transform(
                    lambda texts: embed_fn(texts if isinstance(texts, list) else [texts])[0]
                )

                # Collect chunk data
                doc_embeddings.collect(
                    file_name=doc["filename"],
                    file_path=doc["path"],
                    location=chunk["location"],
                    text=chunk["text"],
                    embedding=chunk["embedding"],
                )

        # Export to Qdrant
        qdrant_connection = cocoindex.targets.QdrantConnection(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
        )

        doc_embeddings.export(
            "document_embeddings",
            cocoindex.targets.Qdrant(
                collection_name=config.collection_name,
                connection=qdrant_connection,
            ),
            primary_key_fields=["file_name", "location"],
            vector_indexes=[
                cocoindex.VectorIndexDef(
                    field_name="embedding",
                    metric=cocoindex.VectorSimilarityMetric.COSINE_SIMILARITY,
                )
            ],
        )

    return document_ingestion_flow


def setup_and_run_flow(
    source_path: str,
    config: FlowConfig | None = None,
    blocking: bool = True,
) -> dict[str, Any]:
    """Setup and run the document ingestion flow.

    Args:
        source_path: Path to document directory
        config: Flow configuration
        blocking: If True, wait for completion; if False, run async

    Returns:
        Flow execution results
    """
    if not COCOINDEX_AVAILABLE:
        return {"error": "CocoIndex not available", "success": False}

    config = config or FlowConfig()

    try:
        # Initialize CocoIndex
        cocoindex.init()

        # Create and register the flow
        flow_def = create_document_flow(config, source_path)
        if flow_def is None:
            return {"error": "Failed to create flow", "success": False}

        _flow = cocoindex.open_flow("DocumentIngestion", flow_def)

        # Setup backend infrastructure
        cocoindex.setup_all_flows()

        # Run the flow
        if blocking:
            cocoindex.update_all_flows()
        else:
            cocoindex.update_all_flows_async()

        return {
            "success": True,
            "flow_name": "DocumentIngestion",
            "source_path": source_path,
            "collection": config.collection_name,
        }

    except Exception as e:
        logger.error(f"Flow execution failed: {e}", exc_info=True)
        return {"error": str(e), "success": False}
