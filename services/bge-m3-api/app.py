"""
BGE-M3 Embeddings API
Multi-vector embeddings: dense + sparse + colbert
Pinned hash-verified ONNX artifact (philipchung/bge-m3-onnx @ 92465a6c, fp32)
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
import onnxruntime
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel, Field
from transformers import AutoTokenizer
from verify_artifact import verify_artifact_dir

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
encode_partial_failures_total = Counter(
    "bge_encode_partial_failures_total",
    "Items that failed validation in batch",
    ["encode_type"],
)
model_loaded = Gauge("bge_model_loaded", "Model loaded status (1=loaded, 0=not loaded)")

# Global model instance
_onnx_session = None
_tokenizer = None
_warmed_up = False


class ONNXEmbeddingModel:
    """ONNX INT8 BGE-M3 embedding model wrapper.

    Replaces ``FlagEmbedding.BGEM3FlagModel`` with the same interface:
    ``encode()`` returns a dict with ``dense_vecs``, ``lexical_weights``,
    and ``colbert_vecs`` keys, preserving the existing endpoint contracts.
    """

    EXPECTED_OUTPUTS = ["dense_vecs", "sparse_vecs", "colbert_vecs"]

    def __init__(self, session: onnxruntime.InferenceSession, tokenizer):
        self.session = session
        self.tokenizer = tokenizer
        self._input_names = [inp.name for inp in session.get_inputs()]
        self._output_names = [out.name for out in session.get_outputs()]
        assert self._output_names == self.EXPECTED_OUTPUTS, (
            f"ONNX model output order changed: expected {self.EXPECTED_OUTPUTS}, "
            f"got {self._output_names}"
        )
        logger.info("ONNX inputs: %s, outputs: %s", self._input_names, self._output_names)

    def encode(
        self,
        texts: list[str],
        *,
        max_length: int = 2048,
        return_dense: bool = False,
        return_sparse: bool = False,
        return_colbert_vecs: bool = False,
    ) -> dict[str, Any]:
        """Encode texts to multi-vector embeddings via ONNX INT8.

        Returns a dict with the same shape contract as ``BGEM3FlagModel.encode``:
        - ``dense_vecs``: ``np.ndarray`` of shape ``[B, 1024]`` (float32)
        - ``lexical_weights``: ``list[dict[int, float]]`` (Qdrant sparse format)
        - ``colbert_vecs``: ``list[np.ndarray]``, each ``[seq_len, 1024]`` (float32)

        Note: batch_size param was dropped — ONNX INT8 runs a single session.run
        for the whole request; chunked batching would require re-tokenising.
        """
        result: dict[str, Any] = {}

        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="np",
        )
        input_ids = encoded["input_ids"].astype(np.int64)
        attention_mask = encoded["attention_mask"].astype(np.int64)

        onnx_inputs = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }

        onnx_outputs = self.session.run(None, onnx_inputs)
        # Output order verified: dense_vecs [B, 1024], sparse_vecs [B, L, 1], colbert_vecs [B, L, 1024]
        dense, sparse, colbert = onnx_outputs

        if return_dense:
            result["dense_vecs"] = dense
        if return_sparse:
            result["lexical_weights"] = _onnx_sparse_to_qdrant(sparse, input_ids, self.tokenizer)
        if return_colbert_vecs:
            result["colbert_vecs"] = [colbert[i] for i in range(colbert.shape[0])]

        return result


def _onnx_sparse_to_qdrant(
    sparse_vecs: np.ndarray,
    input_ids: np.ndarray,
    tokenizer,
) -> list[dict[str, list]]:
    """Convert ONNX sparse token weights to Qdrant sparse format (#2209).

    Args:
        sparse_vecs: ONNX ``sparse_vecs`` output ``[batch, seq_len, 1]``.
        input_ids: Tokenized input IDs ``[batch, seq_len]``.
        tokenizer: HuggingFace tokenizer for special-token ID lookups.

    Returns:
        ``[{"indices": [int token ids], "values": [float weights]}, ...]``
        — one dict per batch item. Special tokens (cls/eos/pad/unk) are
        skipped and duplicate token IDs keep the max positive weight.
    """
    batch_size = sparse_vecs.shape[0]
    special_ids: set[int] = set()
    for attr in ("cls_token_id", "eos_token_id", "pad_token_id", "unk_token_id"):
        tid = getattr(tokenizer, attr, None)
        if tid is not None:
            special_ids.add(int(tid))

    converted: list[dict[str, list]] = []
    for i in range(batch_size):
        token_weights: dict[int, float] = {}
        for j, token_id in enumerate(input_ids[i]):
            tid = int(token_id)
            if tid in special_ids:
                continue
            weight = float(sparse_vecs[i, j, 0])
            if weight <= 0:
                continue
            token_weights[tid] = max(token_weights.get(tid, weight), weight)

        indices = list(token_weights.keys())
        values = [token_weights[k] for k in indices]
        converted.append({"indices": indices, "values": values})

    return converted


def compute_maxsim_scores(
    query_vecs: np.ndarray,
    doc_vecs_list: list[np.ndarray],
) -> list[float]:
    """Compute MaxSim (ColBERT late-interaction) scores via numpy.

    Replaces ``BGEM3FlagModel.colbert_score()`` with pure numpy:
    ``(query_vecs @ doc_vecs.T).max(axis=1).sum()`` per document.

    Args:
        query_vecs: Query ColBERT vectors ``(num_query_tokens, dim)``.
        doc_vecs_list: List of document ColBERT vectors.

    Returns:
        List of MaxSim scores, one per document, in input order.
    """
    return [float((query_vecs @ doc_vecs.T).max(axis=1).sum()) for doc_vecs in doc_vecs_list]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eager model loading + bounded warmup encode at startup."""
    global _warmed_up
    logger.info("Starting model warmup...")
    start = time.time()
    model = get_model()
    model.encode(
        ["warmup query"],
        max_length=64,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    elapsed = time.time() - start
    _warmed_up = True
    logger.info("Warmup complete in %.2fs", elapsed)
    yield


app = FastAPI(
    title="BGE-M3 Embeddings API",
    description="Multi-vector embeddings API (dense + sparse + colbert) — pinned offline ONNX artifact",
    version="2.1.0",
    lifespan=lifespan,
)


def get_model():
    """Load the verified ONNX artifact and the baked local tokenizer (lazy, cached)."""
    global _onnx_session, _tokenizer
    if _onnx_session is None:
        logger.info("Loading BGE-M3 ONNX artifact from %s", settings.ONNX_MODEL_DIR)

        # Reject missing, dummy, incomplete, and hash-mismatched artifacts
        # before any inference (manifest sizes + SHA-256).
        verify_artifact_dir(settings.ONNX_MODEL_DIR)

        onnx_path = os.path.join(settings.ONNX_MODEL_DIR, settings.ONNX_MODEL_FILENAME)

        start_time = time.time()

        sess_options = onnxruntime.SessionOptions()
        sess_options.intra_op_num_threads = settings.NUM_THREADS
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        _onnx_session = onnxruntime.InferenceSession(onnx_path, sess_options)
        load_time = time.time() - start_time
        logger.info("ONNX session loaded in %.2fs", load_time)

        # Load the tokenizer baked next to the model — strictly local, no hub.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        logger.info("Loading tokenizer from %s (local-only)", settings.TOKENIZER_DIR)
        _tokenizer = AutoTokenizer.from_pretrained(settings.TOKENIZER_DIR, local_files_only=True)
        logger.info("Tokenizer loaded")
        model_loaded.set(1)

    return ONNXEmbeddingModel(_onnx_session, _tokenizer)


# Encode limits
ENCODE_MAX_ITEMS: int = 64  # Max texts per encode request (unbounded → OOM/DoS on CPU-ONNX)


# Pydantic models
class EncodeRequest(BaseModel):
    texts: list[str] = Field(
        ..., description="List of texts to encode", max_length=ENCODE_MAX_ITEMS
    )
    max_length: int = Field(settings.MAX_LENGTH, description="Max token length")


class PartialFailure(BaseModel):
    index: int
    error: str


class DenseResponse(BaseModel):
    dense_vecs: list[list[float]] = Field(..., description="Dense embeddings (1024-dim)")
    processing_time: float
    partial_failures: list[PartialFailure] = Field(default_factory=list)


class SparseResponse(BaseModel):
    lexical_weights: list[dict[str, Any]] = Field(
        ..., description="Sparse vectors (indices + values)"
    )
    processing_time: float
    partial_failures: list[PartialFailure] = Field(default_factory=list)


class ColbertResponse(BaseModel):
    colbert_vecs: list[list[list[float]]] = Field(..., description="ColBERT multivectors")
    processing_time: float
    partial_failures: list[PartialFailure] = Field(default_factory=list)


class HybridResponse(BaseModel):
    dense_vecs: list[list[float]]
    lexical_weights: list[dict[str, Any]]
    colbert_vecs: list[list[list[float]]]
    processing_time: float
    partial_failures: list[PartialFailure] = Field(default_factory=list)


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


def _validate_texts(texts: list[str]) -> tuple[list[int], list[int], list[str]]:
    """Validate batch texts and separate valid from invalid indices.

    Returns:
        (valid_indices, invalid_indices, error_messages)
    """
    valid_indices = []
    invalid_indices = []
    error_messages = []
    for i, text in enumerate(texts):
        if not text or not text.strip():
            invalid_indices.append(i)
            error_messages.append("empty or whitespace-only string")
            logger.warning("Item %d failed validation: empty or whitespace-only string", i)
        else:
            valid_indices.append(i)
    return valid_indices, invalid_indices, error_messages


def _lexical_weights_to_qdrant_sparse(
    lexical_weights: list[dict[Any, Any]],
) -> list[dict[str, list]]:
    """Convert ``lexical_weights`` rows to Qdrant sparse format.

    Maps each ``{token_id: weight}`` dict to ``{"indices": [int], "values": [float]}``.
    When ONNX sparse output is already in Qdrant format (via ``_onnx_sparse_to_qdrant``),
    this function is a no-op passthrough.
    """
    converted: list[dict[str, list]] = []
    for row in lexical_weights:
        if "indices" in row and "values" in row:
            # Already in Qdrant sparse format — pass through
            converted.append(row)
            continue
        indices: list[int] = []
        values: list[float] = []
        for idx, val in row.items():
            indices.append(int(idx))
            values.append(float(val))
        converted.append({"indices": indices, "values": values})
    return converted


# ── Shared encode helper ──


async def _run_encode(
    request: EncodeRequest,
    *,
    encode_type: str,
    return_dense: bool,
    return_sparse: bool,
    return_colbert_vecs: bool,
) -> tuple[
    tuple[list[list[float]], list[dict[str, Any]], list[list[list[float]]]],
    float,
    list["PartialFailure"],
]:
    """Shared encode pipeline: validate → encode → reconstruct full-cardinality response.

    Returns (results_tuple, processing_time, partial_failures) where results_tuple
    contains only the vectors/weights lists that were requested, in order:
    dense_vecs, lexical_weights, colbert_vecs (each included only when the
    corresponding return_* flag is True).

    Callers unpack the tuple according to which flags they set.
    """
    encode_requests_total.labels(encode_type=encode_type).inc()
    encode_batch_size.observe(len(request.texts))

    valid_indices, invalid_indices, error_messages = _validate_texts(request.texts)
    partial_failures = [
        PartialFailure(index=idx, error=msg)
        for idx, msg in zip(invalid_indices, error_messages, strict=True)
    ]
    if invalid_indices:
        encode_partial_failures_total.labels(encode_type=encode_type).inc(len(invalid_indices))

    model = get_model()
    start_time = time.time()

    n = len(request.texts)
    dense_sentinel = [0.0] * 1024
    sparse_sentinel: dict[str, list[Any]] = {"indices": [], "values": []}
    colbert_sentinel = [[0.0] * 1024]

    # Prepare output slots
    dense_vecs: list[list[float]] = [[]] * n if return_dense else []
    lexical_weights: list[dict[str, Any]] = [{}] * n if return_sparse else []
    colbert_vecs: list[list[list[float]]] = [[]] * n if return_colbert_vecs else []

    if valid_indices:
        valid_texts = [request.texts[i] for i in valid_indices]
        embeddings = model.encode(
            valid_texts,
            max_length=request.max_length,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=return_colbert_vecs,
        )

        if return_dense:
            valid_dense = embeddings["dense_vecs"].tolist()
            dense_iter = iter(valid_dense)
            for i in valid_indices:
                dense_vecs[i] = next(dense_iter)
            for i in invalid_indices:
                dense_vecs[i] = dense_sentinel.copy()

        if return_sparse:
            valid_sparse = _lexical_weights_to_qdrant_sparse(embeddings["lexical_weights"])
            sparse_iter = iter(valid_sparse)
            for i in valid_indices:
                lexical_weights[i] = next(sparse_iter)
            for i in invalid_indices:
                lexical_weights[i] = sparse_sentinel.copy()

        if return_colbert_vecs:
            valid_colbert = [vec.tolist() for vec in embeddings["colbert_vecs"]]
            colbert_iter = iter(valid_colbert)
            for i in valid_indices:
                colbert_vecs[i] = next(colbert_iter)
            for i in invalid_indices:
                colbert_vecs[i] = [row[:] for row in colbert_sentinel]
    else:
        # All invalid — fill sentinels
        if return_dense:
            for i in invalid_indices:
                dense_vecs[i] = dense_sentinel.copy()
        if return_sparse:
            for i in invalid_indices:
                lexical_weights[i] = sparse_sentinel.copy()
        if return_colbert_vecs:
            for i in invalid_indices:
                colbert_vecs[i] = [row[:] for row in colbert_sentinel]

    processing_time = time.time() - start_time
    encode_duration.labels(encode_type=encode_type).observe(processing_time)

    return (dense_vecs, lexical_weights, colbert_vecs), processing_time, partial_failures


# ── Endpoints ──


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "model_loaded": _onnx_session is not None, "warmed_up": _warmed_up}


@app.post("/encode/dense", response_model=DenseResponse)
async def encode_dense(request: EncodeRequest):
    """
    Encode texts to dense vectors (1024-dim)

    For semantic similarity search
    """
    try:
        (dense_vecs, _, _), processing_time, partial_failures = await _run_encode(
            request,
            encode_type="dense",
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return DenseResponse(
            dense_vecs=dense_vecs,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )
    except Exception as e:
        logger.error("Dense encoding error", exc_info=e)
        raise HTTPException(500, "Encoding failed: internal error")


@app.post("/encode/sparse", response_model=SparseResponse)
async def encode_sparse(request: EncodeRequest):
    """
    Encode texts to sparse vectors (BM25-style)

    For keyword matching
    """
    try:
        (_, lexical_weights, _), processing_time, partial_failures = await _run_encode(
            request,
            encode_type="sparse",
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        return SparseResponse(
            lexical_weights=lexical_weights,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )
    except Exception as e:
        logger.error("Sparse encoding error", exc_info=e)
        raise HTTPException(500, "Encoding failed: internal error")


@app.post("/encode/colbert", response_model=ColbertResponse)
async def encode_colbert(request: EncodeRequest):
    """
    Encode texts to ColBERT multivectors

    For late-interaction reranking (MaxSim)
    """
    try:
        (_, _, colbert_vecs), processing_time, partial_failures = await _run_encode(
            request,
            encode_type="colbert",
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )
        return ColbertResponse(
            colbert_vecs=colbert_vecs,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )
    except Exception as e:
        logger.error("ColBERT encoding error", exc_info=e)
        raise HTTPException(500, "Encoding failed: internal error")


@app.post("/encode/hybrid", response_model=HybridResponse)
async def encode_hybrid(request: EncodeRequest):
    """
    Encode texts to all three representations at once

    Returns: dense + sparse + colbert
    Most efficient for RAG pipeline
    """
    try:
        (
            (dense_vecs, lexical_weights, colbert_vecs),
            processing_time,
            partial_failures,
        ) = await _run_encode(
            request,
            encode_type="hybrid",
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=True,
        )
        return HybridResponse(
            dense_vecs=dense_vecs,
            lexical_weights=lexical_weights,
            colbert_vecs=colbert_vecs,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )
    except Exception as e:
        logger.error("Hybrid encoding error", exc_info=e)
        raise HTTPException(500, "Encoding failed: internal error")


@app.post("/rerank", response_model=RerankResponse)
async def rerank(request: RerankRequest):
    """
    Rerank documents using ColBERT MaxSim.

    Returns documents sorted by relevance score (highest first).

    Note: no live client — kept for completeness. The only consumer
    (card_d884443ae301) was removed; this endpoint is maintained but
    unused by the active pipeline.
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
            max_length=request.max_length,
            return_dense=False,
            return_sparse=False,
            return_colbert_vecs=True,
        )

        colbert_vecs = embeddings["colbert_vecs"]
        query_vecs = colbert_vecs[0]  # First is query
        doc_vecs_list = colbert_vecs[1:]  # Rest are documents

        # Compute MaxSim scores (pure numpy, no FlagEmbedding dependency)
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
        logger.error("Rerank error", exc_info=e)
        raise HTTPException(500, "Rerank failed: internal error")


# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT, log_level=settings.LOG_LEVEL.lower())
