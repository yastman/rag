"""USER2-base Dense Embedding Service.

FastAPI service for generating dense vectors using deepvk/USER2-base.
Best-in-class Russian semantic matching.
Model is loaded once at startup and reused for all requests.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model instance
model: SentenceTransformer | None = None
MODEL_NAME = "deepvk/USER2-base"


class EmbedRequest(BaseModel):
    """Request for dense embedding."""

    text: str


class EmbedBatchRequest(BaseModel):
    """Request for batch dense embeddings."""

    texts: list[str]


class EmbedResponse(BaseModel):
    """Dense vector response (768-dim)."""

    embedding: list[float]


class EmbedBatchResponse(BaseModel):
    """Batch dense vectors response."""

    embeddings: list[list[float]]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    model: str
    dimension: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, cleanup on shutdown."""
    global model
    logger.info(f"Loading {MODEL_NAME} model...")
    model = SentenceTransformer(MODEL_NAME)
    logger.info(
        f"{MODEL_NAME} model loaded successfully (dim={model.get_sentence_embedding_dimension()})"
    )
    yield
    logger.info("Shutting down USER2-base service")


app = FastAPI(
    title="USER2-base Dense Embedding Service",
    version="1.0.0",
    description="Russian semantic embeddings with deepvk/USER2-base",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if model else "loading",
        model=MODEL_NAME,
        dimension=768,
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """Generate dense vector for single text."""
    if not model:
        raise RuntimeError("Model not loaded")

    embedding = model.encode(request.text, normalize_embeddings=True)
    return EmbedResponse(embedding=embedding.tolist())


@app.post("/embed_batch", response_model=EmbedBatchResponse)
async def embed_batch(request: EmbedBatchRequest):
    """Generate dense vectors for batch of texts."""
    if not model:
        raise RuntimeError("Model not loaded")

    embeddings = model.encode(request.texts, normalize_embeddings=True)
    return EmbedBatchResponse(embeddings=embeddings.tolist())
