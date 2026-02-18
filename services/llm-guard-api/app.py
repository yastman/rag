"""LLM Guard Prompt Injection Scanner — FastAPI service.

Loads ProtectAI/deberta-v3-base-prompt-injection-v2 at startup.
Exposes POST /scan/injection for prompt injection detection.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from config import settings


logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

_scanner = None


def _load_scanner():
    """Load the PromptInjection scanner (called once at startup)."""
    global _scanner
    from llm_guard.input_scanners import PromptInjection
    from llm_guard.input_scanners.prompt_injection import MatchType

    logger.info(
        "Loading PromptInjection scanner (model=%s, onnx=%s)...",
        settings.MODEL_NAME,
        settings.USE_ONNX,
    )
    t0 = time.time()
    _scanner = PromptInjection(
        threshold=settings.THRESHOLD,
        match_type=MatchType.FULL,
        use_onnx=settings.USE_ONNX,
    )
    logger.info("Scanner loaded in %.2fs", time.time() - t0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eager model loading at startup."""
    _load_scanner()
    # Warmup scan
    if _scanner:
        _scanner.scan("warmup test query")
        logger.info("Warmup scan complete")
    yield


app = FastAPI(
    title="LLM Guard API",
    description="Prompt injection detection via DeBERTa v3",
    version="1.0.0",
    lifespan=lifespan,
)


class ScanRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class ScanResponse(BaseModel):
    detected: bool
    risk_score: float
    processing_time_ms: float


@app.post("/scan/injection", response_model=ScanResponse)
async def scan_injection(request: ScanRequest):
    """Scan text for prompt injection."""
    t0 = time.perf_counter()
    _sanitized, is_valid, risk_score = _scanner.scan(request.text)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    detected = not is_valid
    return ScanResponse(
        detected=detected,
        risk_score=float(risk_score),
        processing_time_ms=round(elapsed_ms, 1),
    )


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "model_loaded": _scanner is not None}
