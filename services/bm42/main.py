"""BM42 Sparse Embedding Service.

FastAPI service for generating BM42 sparse vectors.
Model is loaded once at startup and reused for all requests.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastembed import SparseTextEmbedding
from pydantic import BaseModel


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model instance
sparse_model: SparseTextEmbedding | None = None


class EmbedRequest(BaseModel):
    """Request for sparse embedding."""

    text: str


class EmbedBatchRequest(BaseModel):
    """Request for batch sparse embedding."""

    texts: list[str]


class EmbedResponse(BaseModel):
    """Sparse vector response."""

    indices: list[int]
    values: list[float]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    model: str


class EmbedBatchResponse(BaseModel):
    """Batch sparse vector response."""

    vectors: list[EmbedResponse]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, cleanup on shutdown."""
    global sparse_model
    logger.info("Loading BM42 model...")
    sparse_model = SparseTextEmbedding(model_name="Qdrant/bm42-all-minilm-l6-v2-attentions")
    logger.info("BM42 model loaded successfully")
    yield
    logger.info("Shutting down BM42 service")


app = FastAPI(
    title="BM42 Sparse Embedding Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if sparse_model else "loading",
        model="Qdrant/bm42-all-minilm-l6-v2-attentions",
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """Generate sparse vector for text."""
    if not sparse_model:
        raise RuntimeError("Model not loaded")

    result = next(iter(sparse_model.embed([request.text])))
    return EmbedResponse(
        indices=result.indices.tolist(),
        values=result.values.tolist(),
    )


@app.post("/embed_batch", response_model=EmbedBatchResponse)
async def embed_batch(request: EmbedBatchRequest):
    """Generate sparse vectors for a batch of texts."""
    if not sparse_model:
        raise RuntimeError("Model not loaded")

    results = list(sparse_model.embed(request.texts))
    vectors = [
        EmbedResponse(indices=result.indices.tolist(), values=result.values.tolist())
        for result in results
    ]
    return EmbedBatchResponse(vectors=vectors)
