"""
BGE-M3 Embeddings API
Multi-vector embeddings: dense + sparse + colbert
ONNX INT8 runtime (philipchung/bge-m3-onnx)
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

import numpy as np
import onnxruntime
from fastapi import FastAPI, Header, HTTPException, Request
from langfuse import get_client, observe
from opentelemetry import propagate
from opentelemetry.context import attach, detach
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel, Field
from transformers import AutoTokenizer

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

LangfuseTraceIdHeader = Annotated[str | None, Header(alias="x-langfuse-trace-id")]
LangfuseParentObservationIdHeader = Annotated[
    str | None, Header(alias="x-langfuse-parent-observation-id")
]


def _update_current_bge_span(
    *,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    encode_type: str,
) -> None:
    """Attach curated BGE service metadata to the active Langfuse observation."""
    payload: dict[str, Any] = {
        "metadata": {
            "model": settings.MODEL_NAME,
            "runtime": "onnx-int8",
            "encode_type": encode_type,
        }
    }
    if input is not None:
        payload["input"] = input
    if output is not None:
        payload["output"] = output
    try:
        get_client().update_current_span(**payload)
    except Exception:
        logger.debug("Langfuse BGE span update skipped", exc_info=True)


class ONNXEmbeddingModel:
    """ONNX INT8 BGE-M3 embedding model wrapper.

    Replaces ``FlagEmbedding.BGEM3FlagModel`` with the same interface:
    ``encode()`` returns a dict with ``dense_vecs``, ``lexical_weights``,
    and ``colbert_vecs`` keys, preserving the existing endpoint contracts.
    """

    def __init__(self, session: onnxruntime.InferenceSession, tokenizer):
        self.session = session
        self.tokenizer = tokenizer
        self._input_names = [inp.name for inp in session.get_inputs()]
        self._output_names = [out.name for out in session.get_outputs()]
        logger.info("ONNX inputs: %s, outputs: %s", self._input_names, self._output_names)

    def encode(
        self,
        texts: list[str],
        *,
        batch_size: int = 12,
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
    # Activate OTEL auto-instrumentation (#2225). The SDK-native
    # FastAPIInstrumentor.instrument_app(app) replaces the bespoke
    # @app.middleware('http') extract_trace_context defined below with a
    # standard ASGI middleware that:
    #   * extracts traceparent / baggage from incoming headers automatically;
    #   * adds http.method / http.route / http.status_code semantic attrs;
    #   * sets the OTEL context for every @observe span downstream.
    # Activation is best-effort so a missing optional dep does not block boot.
    try:  # pragma: no cover — exercised via service smoke tests
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        if not getattr(app, "_is_instrumented_by_opentelemetry", False):
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPIInstrumentor activated (#2225)")
    except Exception:
        logger.warning("FastAPIInstrumentor activation skipped", exc_info=True)

    try:  # pragma: no cover
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception:
        logger.debug("LoggingInstrumentor activation skipped", exc_info=True)

    logger.info("Starting model warmup...")
    start = time.time()
    model = get_model()
    model.encode(
        ["warmup query"],
        batch_size=1,
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
    description="Multi-vector embeddings API (dense + sparse + colbert) — ONNX INT8",
    version="2.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def extract_trace_context(request: Request, call_next):
    """Attach incoming W3C trace context so service spans join caller traces."""
    context = propagate.extract(request.headers)
    token = attach(context)
    try:
        return await call_next(request)
    finally:
        detach(token)


def get_model():
    """Load ONNX session and tokenizer (lazy, cached)."""
    global _onnx_session, _tokenizer
    if _onnx_session is None:
        logger.info("Loading BGE-M3 ONNX model from %s", settings.ONNX_MODEL_DIR)

        onnx_path = os.path.join(settings.ONNX_MODEL_DIR, "model.int8.onnx")
        if not os.path.isfile(onnx_path):
            raise FileNotFoundError(f"ONNX model not found at {onnx_path}")

        start_time = time.time()

        sess_options = onnxruntime.SessionOptions()
        sess_options.intra_op_num_threads = settings.NUM_THREADS
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

        _onnx_session = onnxruntime.InferenceSession(onnx_path, sess_options)
        load_time = time.time() - start_time
        logger.info("ONNX session loaded in %.2fs", load_time)

        # Load tokenizer from HuggingFace (model config only, no weights)
        logger.info("Loading tokenizer for %s", settings.MODEL_NAME)
        _tokenizer = AutoTokenizer.from_pretrained(
            settings.MODEL_NAME,
            cache_dir=settings.MODEL_CACHE_DIR,
            revision=settings.MODEL_REVISION,
        )
        logger.info("Tokenizer loaded")
        model_loaded.set(1)

    return ONNXEmbeddingModel(_onnx_session, _tokenizer)


# Pydantic models
class EncodeRequest(BaseModel):
    texts: list[str] = Field(..., description="List of texts to encode")
    max_length: int = Field(settings.MAX_LENGTH, description="Max token length")
    batch_size: int = Field(settings.BATCH_SIZE, description="Batch size for processing")


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


# ── Endpoints ──


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok", "model_loaded": _onnx_session is not None, "warmed_up": _warmed_up}


@app.post("/encode/dense", response_model=DenseResponse)
@observe(
    name="bge-m3-service-encode-dense",
    as_type="embedding",
    capture_input=False,
    capture_output=False,
)
async def encode_dense(
    request: EncodeRequest,
    langfuse_trace_id: LangfuseTraceIdHeader = None,
    langfuse_parent_observation_id: LangfuseParentObservationIdHeader = None,
):
    """
    Encode texts to dense vectors (1024-dim)

    For semantic similarity search
    """
    encode_requests_total.labels(encode_type="dense").inc()
    encode_batch_size.observe(len(request.texts))
    _update_current_bge_span(
        input={
            "texts_count": len(request.texts),
            "batch_size": request.batch_size,
            "max_length": request.max_length,
        },
        encode_type="dense",
    )

    try:
        valid_indices, invalid_indices, error_messages = _validate_texts(request.texts)
        partial_failures = [
            PartialFailure(index=idx, error=msg)
            for idx, msg in zip(invalid_indices, error_messages, strict=True)
        ]
        if invalid_indices:
            encode_partial_failures_total.labels(encode_type="dense").inc(len(invalid_indices))

        model = get_model()
        start_time = time.time()

        if valid_indices:
            valid_texts = [request.texts[i] for i in valid_indices]
            embeddings = model.encode(
                valid_texts,
                batch_size=request.batch_size,
                max_length=request.max_length,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            valid_vecs = embeddings["dense_vecs"].tolist()
        else:
            valid_vecs = []

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="dense").observe(processing_time)

        # Reconstruct full-cardinality response
        dense_sentinel = [0.0] * 1024
        dense_vecs: list[list[float]] = [[]] * len(request.texts)
        valid_iter = iter(valid_vecs)
        for i in valid_indices:
            dense_vecs[i] = next(valid_iter)
        for i in invalid_indices:
            dense_vecs[i] = dense_sentinel.copy()

        _update_current_bge_span(
            output={
                "vectors_count": len(dense_vecs),
                "vector_dim": len(dense_vecs[0]) if dense_vecs else 0,
                "processing_time": processing_time,
                "partial_failures": len(partial_failures),
            },
            encode_type="dense",
        )
        return DenseResponse(
            dense_vecs=dense_vecs,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )

    except Exception as e:
        logger.error(f"Dense encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/encode/sparse", response_model=SparseResponse)
@observe(
    name="bge-m3-service-encode-sparse",
    as_type="embedding",
    capture_input=False,
    capture_output=False,
)
async def encode_sparse(
    request: EncodeRequest,
    langfuse_trace_id: LangfuseTraceIdHeader = None,
    langfuse_parent_observation_id: LangfuseParentObservationIdHeader = None,
):
    """
    Encode texts to sparse vectors (BM25-style)

    For keyword matching
    """
    encode_requests_total.labels(encode_type="sparse").inc()
    encode_batch_size.observe(len(request.texts))
    _update_current_bge_span(
        input={
            "texts_count": len(request.texts),
            "batch_size": request.batch_size,
            "max_length": request.max_length,
        },
        encode_type="sparse",
    )

    try:
        valid_indices, invalid_indices, error_messages = _validate_texts(request.texts)
        partial_failures = [
            PartialFailure(index=idx, error=msg)
            for idx, msg in zip(invalid_indices, error_messages, strict=True)
        ]
        if invalid_indices:
            encode_partial_failures_total.labels(encode_type="sparse").inc(len(invalid_indices))

        model = get_model()
        start_time = time.time()

        if valid_indices:
            valid_texts = [request.texts[i] for i in valid_indices]
            embeddings = model.encode(
                valid_texts,
                batch_size=request.batch_size,
                max_length=request.max_length,
                return_dense=False,
                return_sparse=True,
                return_colbert_vecs=False,
            )
            # ONNX already returns Qdrant sparse format
            valid_weights = _lexical_weights_to_qdrant_sparse(embeddings["lexical_weights"])
        else:
            valid_weights = []

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="sparse").observe(processing_time)

        # Reconstruct full-cardinality response
        sparse_sentinel: dict[str, list[Any]] = {"indices": [], "values": []}
        lexical_weights: list[dict[str, Any]] = [{}] * len(request.texts)
        valid_iter = iter(valid_weights)
        for i in valid_indices:
            lexical_weights[i] = next(valid_iter)
        for i in invalid_indices:
            lexical_weights[i] = sparse_sentinel.copy()

        _update_current_bge_span(
            output={
                "weights_count": len(lexical_weights),
                "processing_time": processing_time,
                "partial_failures": len(partial_failures),
            },
            encode_type="sparse",
        )
        return SparseResponse(
            lexical_weights=lexical_weights,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )

    except Exception as e:
        logger.error(f"Sparse encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/encode/colbert", response_model=ColbertResponse)
@observe(
    name="bge-m3-service-encode-colbert",
    as_type="embedding",
    capture_input=False,
    capture_output=False,
)
async def encode_colbert(
    request: EncodeRequest,
    langfuse_trace_id: LangfuseTraceIdHeader = None,
    langfuse_parent_observation_id: LangfuseParentObservationIdHeader = None,
):
    """
    Encode texts to ColBERT multivectors

    For late-interaction reranking (MaxSim)
    """
    encode_requests_total.labels(encode_type="colbert").inc()
    encode_batch_size.observe(len(request.texts))
    _update_current_bge_span(
        input={
            "texts_count": len(request.texts),
            "batch_size": request.batch_size,
            "max_length": request.max_length,
        },
        encode_type="colbert",
    )

    try:
        valid_indices, invalid_indices, error_messages = _validate_texts(request.texts)
        partial_failures = [
            PartialFailure(index=idx, error=msg)
            for idx, msg in zip(invalid_indices, error_messages, strict=True)
        ]
        if invalid_indices:
            encode_partial_failures_total.labels(encode_type="colbert").inc(len(invalid_indices))

        model = get_model()
        start_time = time.time()

        if valid_indices:
            valid_texts = [request.texts[i] for i in valid_indices]
            embeddings = model.encode(
                valid_texts,
                batch_size=request.batch_size,
                max_length=request.max_length,
                return_dense=False,
                return_sparse=False,
                return_colbert_vecs=True,
            )
            valid_vecs = [vec.tolist() for vec in embeddings["colbert_vecs"]]
        else:
            valid_vecs = []

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="colbert").observe(processing_time)

        # Reconstruct full-cardinality response
        colbert_sentinel = [[0.0] * 1024]
        colbert_vecs: list[list[list[float]]] = [[]] * len(request.texts)
        valid_iter = iter(valid_vecs)
        for i in valid_indices:
            colbert_vecs[i] = next(valid_iter)
        for i in invalid_indices:
            colbert_vecs[i] = [row[:] for row in colbert_sentinel]

        _update_current_bge_span(
            output={
                "colbert_count": len(colbert_vecs),
                "colbert_vector_count": len(colbert_vecs[0]) if colbert_vecs else 0,
                "processing_time": processing_time,
                "partial_failures": len(partial_failures),
            },
            encode_type="colbert",
        )
        return ColbertResponse(
            colbert_vecs=colbert_vecs,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )

    except Exception as e:
        logger.error(f"ColBERT encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/encode/hybrid", response_model=HybridResponse)
@observe(
    name="bge-m3-service-encode-hybrid",
    as_type="embedding",
    capture_input=False,
    capture_output=False,
)
async def encode_hybrid(
    request: EncodeRequest,
    langfuse_trace_id: LangfuseTraceIdHeader = None,
    langfuse_parent_observation_id: LangfuseParentObservationIdHeader = None,
):
    """
    Encode texts to all three representations at once

    Returns: dense + sparse + colbert
    Most efficient for RAG pipeline
    """
    encode_requests_total.labels(encode_type="hybrid").inc()
    encode_batch_size.observe(len(request.texts))
    _update_current_bge_span(
        input={
            "texts_count": len(request.texts),
            "batch_size": request.batch_size,
            "max_length": request.max_length,
        },
        encode_type="hybrid",
    )

    try:
        valid_indices, invalid_indices, error_messages = _validate_texts(request.texts)
        partial_failures = [
            PartialFailure(index=idx, error=msg)
            for idx, msg in zip(invalid_indices, error_messages, strict=True)
        ]
        if invalid_indices:
            encode_partial_failures_total.labels(encode_type="hybrid").inc(len(invalid_indices))

        model = get_model()
        start_time = time.time()

        if valid_indices:
            valid_texts = [request.texts[i] for i in valid_indices]
            embeddings = model.encode(
                valid_texts,
                batch_size=request.batch_size,
                max_length=request.max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=True,
            )
            valid_dense = embeddings["dense_vecs"].tolist()
            valid_sparse = _lexical_weights_to_qdrant_sparse(embeddings["lexical_weights"])
            valid_colbert = [vec.tolist() for vec in embeddings["colbert_vecs"]]
        else:
            valid_dense = []
            valid_sparse = []
            valid_colbert = []

        processing_time = time.time() - start_time
        encode_duration.labels(encode_type="hybrid").observe(processing_time)

        # Reconstruct full-cardinality responses
        dense_sentinel = [0.0] * 1024
        sparse_sentinel: dict[str, list[Any]] = {"indices": [], "values": []}
        colbert_sentinel = [[0.0] * 1024]

        dense_vecs: list[list[float]] = [[]] * len(request.texts)
        lexical_weights: list[dict[str, Any]] = [{}] * len(request.texts)
        colbert_vecs: list[list[list[float]]] = [[]] * len(request.texts)

        dense_iter = iter(valid_dense)
        sparse_iter = iter(valid_sparse)
        colbert_iter = iter(valid_colbert)
        for i in valid_indices:
            dense_vecs[i] = next(dense_iter)
            lexical_weights[i] = next(sparse_iter)
            colbert_vecs[i] = next(colbert_iter)
        for i in invalid_indices:
            dense_vecs[i] = dense_sentinel.copy()
            lexical_weights[i] = sparse_sentinel.copy()
            colbert_vecs[i] = [row[:] for row in colbert_sentinel]

        _update_current_bge_span(
            output={
                "dense_count": len(dense_vecs),
                "sparse_count": len(lexical_weights),
                "colbert_count": len(colbert_vecs),
                "processing_time": processing_time,
                "partial_failures": len(partial_failures),
            },
            encode_type="hybrid",
        )
        return HybridResponse(
            dense_vecs=dense_vecs,
            lexical_weights=lexical_weights,
            colbert_vecs=colbert_vecs,
            processing_time=processing_time,
            partial_failures=partial_failures,
        )

    except Exception as e:
        logger.error(f"Hybrid encoding error: {e!s}")
        raise HTTPException(500, f"Encoding failed: {e!s}")


@app.post("/rerank", response_model=RerankResponse)
@observe(
    name="bge-m3-service-rerank",
    as_type="embedding",
    capture_input=False,
    capture_output=False,
)
async def rerank(
    request: RerankRequest,
    langfuse_trace_id: LangfuseTraceIdHeader = None,
    langfuse_parent_observation_id: LangfuseParentObservationIdHeader = None,
):
    """
    Rerank documents using ColBERT MaxSim.

    Returns documents sorted by relevance score (highest first).
    """
    encode_requests_total.labels(encode_type="rerank").inc()
    _update_current_bge_span(
        input={
            "query_length": len(request.query),
            "documents_count": len(request.documents),
            "top_k": request.top_k,
            "max_length": request.max_length,
        },
        encode_type="rerank",
    )

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
        _update_current_bge_span(
            output={"results_count": 0, "processing_time": 0.0},
            encode_type="rerank",
        )
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

        _update_current_bge_span(
            output={
                "results_count": len(results),
                "top_score": results[0].score if results else None,
                "processing_time": processing_time,
            },
            encode_type="rerank",
        )
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
