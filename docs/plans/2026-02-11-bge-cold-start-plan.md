# BGE-M3 Cold Start + ONNX Spike Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Сократить embedding latency в RAG pipeline: Phase A — устранить cold start и оптимизировать query path; Phase B — spike ONNX Runtime для CPU inference.

**Architecture:** BGE-M3 FastAPI сервис (`services/bge-m3-api/`) использует `BGEM3FlagModel` (PyTorch). Модель загружается лениво при первом запросе (cold start ~20-30s). Query max_length=512 в LangChain wrappers, но API-side MAX_LENGTH=2048. Phase A добавляет startup warmup + query-specific max_length. Phase B добавляет альтернативный ONNX backend.

**Tech Stack:** Python 3.12, FastAPI, FlagEmbedding, ONNX Runtime, httpx, pytest

**Issue:** [#106](https://github.com/yastman/rag/issues/106) | **Milestone:** Stream-A: Latency-LLM+Embed

---

## Текущее состояние (из трейсов)

| Metric | Value |
|--------|-------|
| Dense embed total | ~8.6s |
| Sparse embed total | ~5.8s |
| Qdrant search total | ~0.3s |
| Cold start (model load) | ~20-30s |
| First inference after load | ~8-10s (JIT compilation) |

## Ключевые файлы

| File | Role |
|------|------|
| `services/bge-m3-api/app.py` | BGE-M3 FastAPI сервис, lazy model loading |
| `services/bge-m3-api/config.py` | Settings: MAX_LENGTH=2048, BATCH_SIZE=12 |
| `services/bge-m3-api/Dockerfile` | Container: OMP_NUM_THREADS=2, python3.12-slim |
| `telegram_bot/integrations/embeddings.py` | BGEM3HybridEmbeddings (max_length=512) |
| `telegram_bot/preflight.py` | Healthcheck — `/health` (не грузит модель) |
| `telegram_bot/bot.py` | PropertyBot.start() — preflight → polling |
| `telegram_bot/graph/config.py` | GraphConfig — bge_m3_timeout=120.0 |
| `docker-compose.dev.yml:82-107` | bge-m3 service definition |
| `tests/unit/integrations/test_embeddings.py` | Existing embedding wrapper tests |

---

## Phase A: Quick Fix (Before Baseline)

### Task 1: Add Startup Warmup to BGE-M3 API

**Цель:** Загрузить модель и прогреть JIT при старте контейнера, а не при первом запросе.

**Files:**
- Modify: `services/bge-m3-api/app.py:24-56`
- Test: `services/bge-m3-api/test_app.py` (create)

**Step 1: Write the failing test**

Создать файл `services/bge-m3-api/test_app.py`:

```python
"""Tests for BGE-M3 API warmup and health."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_health_reports_model_loaded_after_startup():
    """After startup event, /health should report model_loaded=True."""
    with patch("app.BGEM3FlagModel") as mock_model_cls:
        mock_model_cls.return_value = MagicMock()
        mock_model_cls.return_value.encode.return_value = {"dense_vecs": [[0.1] * 10]}

        from app import app
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["model_loaded"] is True


def test_health_reports_warmup_latency():
    """Health endpoint should include warmup_ms after startup."""
    with patch("app.BGEM3FlagModel") as mock_model_cls:
        mock_model_cls.return_value = MagicMock()
        mock_model_cls.return_value.encode.return_value = {"dense_vecs": [[0.1] * 10]}

        from app import app
        with TestClient(app) as client:
            resp = client.get("/health")
            data = resp.json()
            assert "warmup_ms" in data
```

**Step 2: Run test to verify it fails**

Run: `cd services/bge-m3-api && python -m pytest test_app.py -v`
Expected: FAIL — model not loaded at startup, no `warmup_ms` field

**Step 3: Implement startup warmup**

В `services/bge-m3-api/app.py` заменить lazy loading на eager startup:

```python
import time
from contextlib import asynccontextmanager

# Global state
_model = None
_warmup_ms: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model and run warmup inference on startup."""
    global _model, _warmup_ms
    start = time.perf_counter()

    logger.info("Loading BGE-M3 model: %s", settings.MODEL_NAME)
    _model = BGEM3FlagModel(settings.MODEL_NAME, use_fp16=settings.USE_FP16)
    model_loaded.set(1)

    # Warmup inference — primes PyTorch JIT, CUDA kernels, thread pools
    logger.info("Running warmup inference...")
    _model.encode(
        ["warmup query for JIT compilation"],
        batch_size=1,
        max_length=64,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )

    _warmup_ms = (time.perf_counter() - start) * 1000
    logger.info("Model ready (warmup %.0fms)", _warmup_ms)

    yield  # App runs

    logger.info("Shutting down BGE-M3 API")


# Update FastAPI app to use lifespan
app = FastAPI(
    title="BGE-M3 Embeddings API",
    description="Multi-vector embeddings API (dense + sparse + colbert)",
    version="1.1.0",
    lifespan=lifespan,
)


def get_model():
    """Return pre-loaded model (no lazy loading)."""
    if _model is None:
        raise HTTPException(503, "Model not loaded yet — service starting up")
    return _model


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "warmup_ms": _warmup_ms,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd services/bge-m3-api && python -m pytest test_app.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/bge-m3-api/app.py services/bge-m3-api/test_app.py
git commit -m "feat(bge-m3): add startup model warmup via FastAPI lifespan"
```

---

### Task 2: Add QUERY_MAX_LENGTH Config

**Цель:** Использовать более короткий `max_length` для query embedding (256) vs document embedding (2048).

**Files:**
- Modify: `services/bge-m3-api/config.py:10-39`
- Modify: `services/bge-m3-api/app.py` (EncodeRequest default)
- Modify: `telegram_bot/integrations/embeddings.py:120-128` (BGEM3HybridEmbeddings default)
- Modify: `telegram_bot/graph/config.py:28` (добавить query_max_length)
- Test: `tests/unit/integrations/test_embeddings.py` (add test)

**Step 1: Write the failing test**

В `tests/unit/integrations/test_embeddings.py` добавить:

```python
class TestBGEM3HybridEmbeddings:
    # ... existing tests ...

    async def test_query_uses_query_max_length(self):
        """aembed_query should send query_max_length, not doc max_length."""
        hybrid_response = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.1]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

            emb = BGEM3HybridEmbeddings(
                base_url="http://fake:8000",
                max_length=512,
                query_max_length=256,
            )
            await emb.aembed_query("short query")
            call_json = mock_post.call_args[1]["json"]
            assert call_json["max_length"] == 256

    async def test_documents_use_doc_max_length(self):
        """aembed_documents should send doc max_length."""
        hybrid_response = {
            "dense_vecs": [[0.1]],
            "lexical_weights": [{"indices": [1], "values": [0.1]}],
        }
        mock_response = httpx.Response(
            200,
            json=hybrid_response,
            request=httpx.Request("POST", "http://fake:8000/encode/hybrid"),
        )
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings

            emb = BGEM3HybridEmbeddings(
                base_url="http://fake:8000",
                max_length=512,
                query_max_length=256,
            )
            await emb.aembed_documents(["longer document text"])
            call_json = mock_post.call_args[1]["json"]
            assert call_json["max_length"] == 512
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/integrations/test_embeddings.py::TestBGEM3HybridEmbeddings::test_query_uses_query_max_length -v`
Expected: FAIL — `__init__` doesn't accept `query_max_length`

**Step 3: Implement query_max_length**

В `telegram_bot/integrations/embeddings.py` обновить `BGEM3HybridEmbeddings.__init__`:

```python
class BGEM3HybridEmbeddings(Embeddings):
    def __init__(
        self,
        base_url: str = "http://bge-m3:8000",
        timeout: float = 120.0,
        max_length: int = 512,
        query_max_length: int = 256,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_length = max_length
        self.query_max_length = query_max_length
        self._client: httpx.AsyncClient | None = None
```

Обновить `aembed_hybrid` и `aembed_query`:

```python
    async def aembed_hybrid(self, text: str) -> tuple[list[float], dict[str, Any]]:
        client = self._get_client()
        response = await client.post(
            f"{self.base_url}/encode/hybrid",
            json={"texts": [text], "max_length": self.query_max_length},
        )
        # ... rest stays same

    async def aembed_query(self, text: str) -> list[float]:
        dense, _ = await self.aembed_hybrid(text)
        return dense

    async def aembed_hybrid_batch(
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[dict[str, Any]]]:
        # Uses self.max_length (documents)
        ...

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        # Uses self.max_length via aembed_hybrid_batch (documents)
        ...
```

Также обновить `BGEM3Embeddings` и `BGEM3SparseEmbeddings`:

```python
class BGEM3Embeddings(Embeddings):
    def __init__(self, ..., query_max_length: int = 256) -> None:
        ...
        self.query_max_length = query_max_length

    async def aembed_query(self, text: str) -> list[float]:
        result = await self._aembed_with_length([text], self.query_max_length)
        return result[0]

class BGEM3SparseEmbeddings:
    def __init__(self, ..., query_max_length: int = 256) -> None:
        ...
        self.query_max_length = query_max_length

    async def aembed_query(self, text: str) -> dict[str, Any]:
        # Use query_max_length for queries
        ...
```

Обновить `GraphConfig` (`telegram_bot/graph/config.py`):

```python
@dataclass
class GraphConfig:
    # ... existing fields ...
    bge_m3_query_max_length: int = 256

    @classmethod
    def from_env(cls) -> GraphConfig:
        return cls(
            # ... existing ...
            bge_m3_query_max_length=int(os.getenv("BGE_M3_QUERY_MAX_LENGTH", "256")),
        )

    def create_hybrid_embeddings(self) -> Any:
        from telegram_bot.integrations.embeddings import BGEM3HybridEmbeddings
        return BGEM3HybridEmbeddings(
            base_url=self.bge_m3_url,
            timeout=self.bge_m3_timeout,
            query_max_length=self.bge_m3_query_max_length,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/integrations/test_embeddings.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add telegram_bot/integrations/embeddings.py telegram_bot/graph/config.py tests/unit/integrations/test_embeddings.py
git commit -m "feat(bge-m3): add query_max_length=256 for faster query embedding"
```

---

### Task 3: Add Keep-Warm Ping to Preflight

**Цель:** Прогреть BGE-M3 модель через реальный encode при старте бота (до polling), не только /health.

**Files:**
- Modify: `telegram_bot/preflight.py:228-233`
- Test: `tests/unit/test_preflight.py` (add test if exists, or create)

**Step 1: Write the failing test**

```python
async def test_bge_m3_preflight_warmup(self):
    """Preflight should call /encode/hybrid to warm up the model."""
    # Mock /health returns ok, then /encode/hybrid returns embeddings
    ...
```

**Step 2: Implement warmup in preflight**

В `telegram_bot/preflight.py`, расширить `_check_single_dep` для `bge_m3`:

```python
if name == "bge_m3":
    # 1. Health check
    resp = await client.get(f"{config.bge_m3_url}/health")
    if resp.status_code != 200:
        logger.error("Preflight FAIL: BGE-M3 — %s", resp.status_code)
        return False

    # 2. Warmup: send a dummy encode to ensure model is loaded + JIT primed
    try:
        warmup_resp = await client.post(
            f"{config.bge_m3_url}/encode/hybrid",
            json={"texts": ["preflight warmup"], "max_length": 64},
            timeout=120.0,  # First encode can be slow
        )
        if warmup_resp.status_code == 200:
            data = warmup_resp.json()
            logger.info(
                "Preflight BGE-M3 warmup OK (%.1fms)",
                data.get("processing_time", 0) * 1000,
            )
        else:
            logger.warning("Preflight BGE-M3 warmup failed: %s", warmup_resp.status_code)
    except Exception as exc:
        logger.warning("Preflight BGE-M3 warmup error (non-fatal): %s", exc)

    return True
```

**Step 3: Run test**

Run: `uv run pytest tests/unit/test_preflight.py -v` (или создать тест)
Expected: PASS

**Step 4: Commit**

```bash
git add telegram_bot/preflight.py
git commit -m "feat(preflight): add BGE-M3 warmup encode during bot startup"
```

---

### Task 4: Run Baseline & Validate

**Цель:** Зафиксировать baseline latency до Phase B.

**Step 1: Rebuild and restart BGE-M3**

```bash
docker compose -f docker-compose.dev.yml build --no-cache bge-m3
docker compose -f docker-compose.dev.yml up -d --force-recreate bge-m3
```

**Step 2: Run trace validation**

```bash
make validate-traces-fast
```

**Step 3: Record baseline**

Записать p50/p95 для:
- `bge-m3-hybrid-embed` latency
- `node-retrieve` latency
- `latency_total_ms`

**Step 4: Commit baseline**

```bash
git add -A
git commit -m "docs: record Phase A baseline after warmup + query_max_length"
```

---

## Phase B: ONNX Runtime Spike (Post-Baseline)

> **Prerequisite:** Phase A complete, baseline recorded.

### Task 5: Research & Export BGE-M3 to ONNX

**Цель:** Конвертировать BGE-M3 в ONNX формат (dense only для spike).

**Files:**
- Create: `services/bge-m3-api/export_onnx.py`

**References:**
- [aapot/bge-m3-onnx](https://huggingface.co/aapot/bge-m3-onnx) — pre-converted ONNX model with O2 optimizations
- [philipchung/bge-m3-onnx](https://huggingface.co/philipchung/bge-m3-onnx) — ONNX with all 3 embeddings (dense+sparse+ColBERT)
- `onnxruntime` CPU: `InferenceSession(model_path, providers=["CPUExecutionProvider"])`

**Step 1: Add export script**

```python
"""Export BGE-M3 to ONNX format using optimum."""

from optimum.onnxruntime import ORTModelForCustomTask
from transformers import AutoTokenizer

model_name = "BAAI/bge-m3"
output_dir = "/models/bge-m3-onnx"

# Export with O2 optimization
model = ORTModelForCustomTask.from_pretrained(model_name, export=True)
tokenizer = AutoTokenizer.from_pretrained(model_name)

model.save_pretrained(output_dir)
tokenizer.save_pretrained(output_dir)
print(f"ONNX model saved to {output_dir}")
```

**Альтернатива (рекомендуемая):** Использовать pre-converted модель:
```bash
# Download pre-converted ONNX model
huggingface-cli download aapot/bge-m3-onnx --local-dir /models/bge-m3-onnx
```

**Step 2: Commit**

```bash
git add services/bge-m3-api/export_onnx.py
git commit -m "feat(bge-m3): add ONNX export script for BGE-M3"
```

---

### Task 6: Add ONNX Backend to BGE-M3 API

**Цель:** Добавить `BGE_BACKEND=pytorch|onnx` config и ONNX inference path.

**Files:**
- Modify: `services/bge-m3-api/config.py`
- Modify: `services/bge-m3-api/app.py`
- Create: `services/bge-m3-api/backends/__init__.py`
- Create: `services/bge-m3-api/backends/pytorch_backend.py`
- Create: `services/bge-m3-api/backends/onnx_backend.py`
- Test: `services/bge-m3-api/test_backends.py`

**Step 1: Add backend abstraction**

В `services/bge-m3-api/config.py`:

```python
class Settings(BaseSettings):
    # ... existing ...
    BGE_BACKEND: str = "pytorch"  # pytorch | onnx
    ONNX_MODEL_PATH: str = "/models/bge-m3-onnx"
    ONNX_OPTIMIZATION_LEVEL: str = "O2"  # O0, O1, O2
```

**Step 2: Create backend protocol**

```python
# services/bge-m3-api/backends/__init__.py
from typing import Any, Protocol

class EmbeddingBackend(Protocol):
    def encode(
        self,
        texts: list[str],
        batch_size: int,
        max_length: int,
        return_dense: bool,
        return_sparse: bool,
        return_colbert_vecs: bool,
    ) -> dict[str, Any]: ...

    def warmup(self) -> None: ...
```

**Step 3: Wrap PyTorch backend**

```python
# services/bge-m3-api/backends/pytorch_backend.py
from FlagEmbedding import BGEM3FlagModel

class PyTorchBackend:
    def __init__(self, model_name: str, use_fp16: bool = True):
        self.model = BGEM3FlagModel(model_name, use_fp16=use_fp16)

    def encode(self, texts, batch_size, max_length, **kwargs):
        return self.model.encode(
            texts, batch_size=batch_size, max_length=max_length, **kwargs
        )

    def warmup(self):
        self.encode(["warmup"], batch_size=1, max_length=64,
                     return_dense=True, return_sparse=True, return_colbert_vecs=False)
```

**Step 4: Create ONNX backend (dense-only spike)**

```python
# services/bge-m3-api/backends/onnx_backend.py
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

class ONNXBackend:
    def __init__(self, model_path: str, num_threads: int = 4):
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = num_threads
        sess_options.inter_op_num_threads = 1
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            f"{model_path}/model.onnx",
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)

    def encode(self, texts, batch_size, max_length,
               return_dense=True, return_sparse=False, return_colbert_vecs=False):
        inputs = self.tokenizer(
            texts, padding=True, truncation=True,
            max_length=max_length, return_tensors="np",
        )
        outputs = self.session.run(None, dict(inputs))
        # Output: [dense_vecs, sparse_vecs, colbert_vecs] (model-dependent)
        result = {}
        if return_dense:
            # Normalize dense embeddings
            dense = outputs[0]  # shape: (batch, seq_len, dim) or (batch, dim)
            # CLS pooling + L2 normalize
            if dense.ndim == 3:
                dense = dense[:, 0, :]  # CLS token
            norms = np.linalg.norm(dense, axis=1, keepdims=True)
            dense = dense / np.maximum(norms, 1e-12)
            result["dense_vecs"] = dense
        if return_sparse:
            # Sparse extraction from model output (implementation TBD)
            result["lexical_weights"] = [{}] * len(texts)
        if return_colbert_vecs:
            result["colbert_vecs"] = [np.zeros((1, 1024))] * len(texts)
        return result

    def warmup(self):
        self.encode(["warmup"], batch_size=1, max_length=64, return_dense=True)
```

**Step 5: Update app.py to use backend factory**

```python
# In app.py lifespan
from config import settings

if settings.BGE_BACKEND == "onnx":
    from backends.onnx_backend import ONNXBackend
    _model = ONNXBackend(settings.ONNX_MODEL_PATH, settings.NUM_THREADS)
else:
    from backends.pytorch_backend import PyTorchBackend
    _model = PyTorchBackend(settings.MODEL_NAME, settings.USE_FP16)

_model.warmup()
```

**Step 6: Run tests**

Run: `cd services/bge-m3-api && python -m pytest test_backends.py -v`
Expected: PASS for both backends (mock/unit tests)

**Step 7: Commit**

```bash
git add services/bge-m3-api/
git commit -m "feat(bge-m3): add ONNX backend behind BGE_BACKEND flag"
```

---

### Task 7: Benchmark ONNX vs PyTorch

**Цель:** Сравнить latency и quality для ONNX vs PyTorch.

**Files:**
- Create: `services/bge-m3-api/benchmark.py`

**Step 1: Create benchmark script**

```python
"""Benchmark PyTorch vs ONNX backend for BGE-M3."""

import json
import time
import httpx

QUERIES = [
    "квартира 2 комнаты Несебр",
    "студия до 50000 евро",
    "What is the penalty for theft under Ukrainian criminal code?",
    # ... 10+ queries
]

def benchmark_backend(base_url: str, n_runs: int = 5):
    results = []
    client = httpx.Client(timeout=120.0)

    for query in QUERIES:
        latencies = []
        for _ in range(n_runs):
            start = time.perf_counter()
            resp = client.post(
                f"{base_url}/encode/hybrid",
                json={"texts": [query], "max_length": 256},
            )
            resp.raise_for_status()
            latencies.append((time.perf_counter() - start) * 1000)

        results.append({
            "query": query[:50],
            "p50_ms": sorted(latencies)[len(latencies) // 2],
            "p95_ms": sorted(latencies)[int(len(latencies) * 0.95)],
            "mean_ms": sum(latencies) / len(latencies),
        })

    return results

if __name__ == "__main__":
    results = benchmark_backend("http://localhost:8000")
    print(json.dumps(results, indent=2))
```

**Step 2: Run benchmark**

```bash
# PyTorch baseline
BGE_BACKEND=pytorch docker compose up -d bge-m3
python services/bge-m3-api/benchmark.py > logs/bench-pytorch.json

# ONNX backend
BGE_BACKEND=onnx docker compose up -d bge-m3
python services/bge-m3-api/benchmark.py > logs/bench-onnx.json
```

**Step 3: Compare results**

| Metric | PyTorch | ONNX | Delta |
|--------|---------|------|-------|
| p50 (dense+sparse, ms) | TBD | TBD | TBD |
| p95 (dense+sparse, ms) | TBD | TBD | TBD |
| Recall@10 overlap | baseline | TBD | TBD |

**Acceptance criteria:**
- ONNX p50 < PyTorch p50 by ≥25%
- Recall@10 overlap ≥ 95% (top-10 documents match)

**Step 4: Commit benchmark results**

```bash
git add services/bge-m3-api/benchmark.py logs/bench-*.json
git commit -m "perf(bge-m3): benchmark ONNX vs PyTorch — results in logs/"
```

---

### Task 8: Update Docker Config for ONNX (if spike succeeds)

**Цель:** Добавить ONNX dependencies в Dockerfile и docker-compose.

**Files:**
- Modify: `services/bge-m3-api/pyproject.toml` — add `onnxruntime`
- Modify: `services/bge-m3-api/Dockerfile` — model download step
- Modify: `docker-compose.dev.yml:82-107` — add `BGE_BACKEND` env
- Modify: `docker-compose.vps.yml:112-130` — same

**Step 1: Add onnxruntime dependency**

```toml
# services/bge-m3-api/pyproject.toml
[project]
dependencies = [
    # ... existing ...
    "onnxruntime>=1.17.0",
    "optimum>=1.17.0",  # For export
]

[project.optional-dependencies]
onnx = ["onnxruntime>=1.17.0"]
```

**Step 2: Update docker-compose**

```yaml
# docker-compose.dev.yml
bge-m3:
  environment:
    BGE_BACKEND: ${BGE_BACKEND:-pytorch}  # pytorch | onnx
    ONNX_MODEL_PATH: /models/bge-m3-onnx
```

**Step 3: Commit**

```bash
git add services/bge-m3-api/pyproject.toml docker-compose.dev.yml docker-compose.vps.yml
git commit -m "feat(bge-m3): add ONNX runtime dependency and docker config"
```

---

## Summary

| Phase | Task | Impact | Risk |
|-------|------|--------|------|
| A | Startup warmup | Eliminates cold start ~20-30s | Low |
| A | query_max_length=256 | Faster query embed (~2x for short queries) | Low |
| A | Preflight warmup ping | Ensures model ready before polling | Low |
| A | Baseline recording | Reference point for Phase B | None |
| B | ONNX export | Pre-optimized model graph | Medium |
| B | ONNX backend | Potential 25-50% latency reduction | Medium |
| B | Benchmark | Data-driven decision | None |
| B | Docker config | Production-ready ONNX | Low |

**Rollback plan:** `BGE_BACKEND=pytorch` (feature flag, zero-code change to revert).
