"""
BGE-M3 Embeddings API
Multi-vector embeddings: dense + sparse + colbert
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from FlagEmbedding import BGEM3FlagModel
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel, Field

from config import settings


# Logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

# Prometheus metrics
encode_requests_total = Counter(
    "bge_encode_requests_total", "Total encoding requests", ["encode_type"]
)
encode_duration = Histogram("bge_encode_seconds", "Encoding duration", ["encode_type"])
encode_batch_size = Histogram("bge_encode_batch_size", "Batch size per request")
model_loaded = Gauge("bge_model_loaded", "Model loaded status (1=loaded, 0=not loaded)")

# Global model instance
_model = None
_warmed_up = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eager model loading + warmup encode at startup."""
    global _warmed_up
    logger.info("Starting model warmup...")
    start = time.time()
    model = get_model()
    model.encode(
        ["warmup query"],
        batch_size=1,
        max_length=64,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=True,
    )
    elapsed = time.time() - start
    _warmed_up = True
    logger.info("Warmup complete in %.2fs", elapsed)
    yield


app = FastAPI(
    title="BGE-M3 Embeddings API",
    description="Multi-vector embeddings API (dense + sparse + colbert)",
    version="1.0.0",
    lifespan=lifespan,
)


def get_model():
    """Lazy model loading"""
    global _model
    if _model is None:
        logger.info(f"Loading BGE-M3 model: {settings.MODEL_NAME}")
        logger.info(f"FP16: {settings.USE_FP16}, Cache dir: {settings.MODEL_CACHE_DIR}")

        start_time = time.time()
        _model = BGEM3FlagModel(settings.MODEL_NAME, use_fp16=settings.USE_FP16)
        load_time = time.time() - start_time

        logger.info(f"Model loaded successfully in {load_time:.2f}s")
        model_loaded.set(1)

    return _model


# Pydantic models
class EncodeRequest(BaseModel):
    texts: list[str] = Field(..., description="List of texts to encode")
    max_length: int = Field(settings.MAX_LENGTH, description="Max token length")
    batch_size: int = Field(settings.BATCH_SIZE, description="Batch size for processing")


class DenseResponse(BaseModel):
    dense_vecs: list[list[float]] = Field(..., description="Dense embeddings (1024-dim)")
    processing_time: float


class SparseResponse(BaseModel):
    lexical_weights: list[dict[str, Any]] = Field(
        ..., description="Sparse vectors (indices + values)"
    )
    processing_time: float


class ColbertResponse(BaseModel):
    colbert_vecs: list[list[list[float]]] = Field(..., description="ColBERT multivectors")
    processing_time: float


class HybridResponse(BaseModel):
    dense_vecs: list[list[float]]
    lexical_weights: list[dict[str, Any]]
    colbert_vecs: list[list[list[float]]]
    processing_time: float


class RerankResult(BaseModel):
    """Single rerank result."""

    index: int = Field(..., description="Original document index")
    score: float = Field(..., description="MaxSim relevance score")


class RerankRequest(BaseModel):
    """Request for ColBERT reranking."""

    query: str = Field(..., description="Query text")
    documents: list[str] = Field(..., description="Documents to rerank", min_length=1)
    top_k: int = Field(
        settings.RERANK_DEFAULT_TOP_K,
        description="Number of top results",
        ge=1,
        le=settings.RERANK_MAX_DOCS,
    )
    max_length: int = Field(
        settings.RERANK_MAX_LENGTH,
        description="Max token length",
        ge=1,
        le=settings.RERANK_MAX_LENGTH,
    )


class RerankResponse(BaseModel):
    """Rerank response with scored results."""

    results: list[RerankResult] = Field(..., description="Ranked results")
    processing_time: float


def compute_maxsim_scores(query_vecs: np.ndarray, doc_vecs_list: list[np.ndarray]) -> list[float]:
    """Compute MaxSim scores between query and documents.

    MaxSim: for each query token, find max similarity with any doc token,
    then sum across all query tokens.

    Args:
        query_vecs: Query ColBERT vectors (num_query_tokens, dim)
        doc_vecs_list: List of document ColBERT vectors

    Returns:
        List of MaxSim scores for each document
    """
    scores = []
    for doc_vecs in doc_vecs_list:
        # Cosine similarity matrix: (num_query_tokens, num_doc_tokens)
        # Vectors are already normalized by BGE-M3
        sim_matrix = query_vecs @ doc_vecs.T
        # MaxSim: max over doc tokens for each query token, then sum
        max_sims = sim_matrix.max(axis=1)
        score = float(max_sims.sum())
        scores.append(score)
    return scores


# Endpoints
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "model_loaded": _model is not None, "warmed_up": _warmed_up}


@app.post("/encode/dense", response_model=DenseResponse)
async def encode_dense(request: EncodeRequest):
    """
    Encode texts to dense vectors (1024-dim)

    For semantic similarity search
    """
    encode_requests_total.labels(encode_type="dense").inc()
    encode_batch_size.observe(len(request.texts))

    try:
        model = get_model()
        start_time = time.time()

        embeddings = model.encode(
            request.texts,
            batch_size=request.batch_size,
            max_length=request.max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="dense").observe(processing_time)

        return DenseResponse(
            dense_vecs=embeddings["dense_vecs"].tolist(), processing_time=processing_time
        )

    except Exception as e:
        logger.error(f"Dense encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/encode/sparse", response_model=SparseResponse)
async def encode_sparse(request: EncodeRequest):
    """
    Encode texts to sparse vectors (BM25-style)

    For keyword matching
    """
    encode_requests_total.labels(encode_type="sparse").inc()
    encode_batch_size.observe(len(request.texts))

    try:
        model = get_model()
        start_time = time.time()

        embeddings = model.encode(
            request.texts,
            batch_size=request.batch_size,
            max_length=request.max_length,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="sparse").observe(processing_time)

        # Convert sparse vectors to Qdrant format
        lexical_weights = []
        for row in embeddings["lexical_weights"]:
            indices = []
            values = []
            for idx, val in row.items():
                indices.append(int(idx))
                values.append(float(val))
            lexical_weights.append({"indices": indices, "values": values})

        return SparseResponse(lexical_weights=lexical_weights, processing_time=processing_time)

    except Exception as e:
        logger.error(f"Sparse encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/encode/colbert", response_model=ColbertResponse)
async def encode_colbert(request: EncodeRequest):
    """
    Encode texts to ColBERT multivectors

    For late-interaction reranking (MaxSim)
    """
    encode_requests_total.labels(encode_type="colbert").inc()
    encode_batch_size.observe(len(request.texts))

    try:
        model = get_model()
        start_time = time.time()

        embeddings = model.encode(
            request.texts,
            batch_size=request.batch_size,
            max_length=request.max_length,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="colbert").observe(processing_time)

        # Convert to nested lists
        colbert_vecs = [vec.tolist() for vec in embeddings["colbert_vecs"]]

        return ColbertResponse(colbert_vecs=colbert_vecs, processing_time=processing_time)

    except Exception as e:
        logger.error(f"ColBERT encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/encode/hybrid", response_model=HybridResponse)
async def encode_hybrid(request: EncodeRequest):
    """
    Encode texts to all three representations at once

    Returns: dense + sparse + colbert
    Most efficient for RAG pipeline
    """
    encode_requests_total.labels(encode_type="hybrid").inc()
    encode_batch_size.observe(len(request.texts))

    try:
        model = get_model()
        start_time = time.time()

        embeddings = model.encode(
            request.texts,
            batch_size=request.batch_size,
            max_length=request.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="hybrid").observe(processing_time)

        # Convert sparse vectors
        lexical_weights = []
        for row in embeddings["lexical_weights"]:
            indices = []
            values = []
            for idx, val in row.items():
                indices.append(int(idx))
                values.append(float(val))
            lexical_weights.append({"indices": indices, "values": values})

        # Convert colbert vectors
        colbert_vecs = [vec.tolist() for vec in embeddings["colbert_vecs"]]

        return HybridResponse(
            dense_vecs=embeddings["dense_vecs"].tolist(),
            lexical_weights=lexical_weights,
            colbert_vecs=colbert_vecs,
            processing_time=processing_time,
        )

    except Exception as e:
        logger.error(f"Hybrid encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    """
    Rerank documents using ColBERT MaxSim.

    Returns documents sorted by relevance score (highest first).
    """
    encode_requests_total.labels(encode_type="rerank").inc()

    # Validate limits
    if len(request.documents) > settings.RERANK_MAX_DOCS:
        raise HTTPException(
            400,
            f"Too many documents: {len(request.documents)} > {settings.RERANK_MAX_DOCS}",
        )

    query = request.query.strip()
    if not query:
        raise HTTPException(400, "Query must be non-empty")

    documents = [d for d in (doc.strip() for doc in request.documents) if d]
    if not documents:
        return RerankResponse(results=[], processing_time=0.0)

    try:
        model = get_model()
        start_time = time.time()

        # Encode query and documents with ColBERT
        all_texts = [query, *documents]
        embeddings = model.encode(
            all_texts,
            batch_size=min(len(all_texts), 12),
            max_length=request.max_length,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )

        colbert_vecs = embeddings["colbert_vecs"]
        query_vecs = colbert_vecs[0]  # First is query
        doc_vecs_list = colbert_vecs[1:]  # Rest are documents

        # Compute MaxSim scores
        scores = compute_maxsim_scores(query_vecs, doc_vecs_list)

        # Sort by score descending and take top_k
        indexed_scores = [(i, s) for i, s in enumerate(scores)]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        top_k = min(request.top_k, len(indexed_scores))
        top_results = indexed_scores[:top_k]

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="rerank").observe(processing_time)

        results = [RerankResult(index=idx, score=score) for idx, score in top_results]

        return RerankResponse(results=results, processing_time=processing_time)

    except Exception as e:
        logger.error(f"Rerank error: {e!s}")
        raise HTTPException(500, f"Rerank failed: {e!s}")


# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level=settings.LOG_LEVEL.lower())
