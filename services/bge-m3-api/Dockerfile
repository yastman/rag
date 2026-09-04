# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# BGE-M3 Embedding Service — pinned hash-verified ONNX artifact (uv sync)

# ====== BUILD STAGE ======
# Base images pinned — checked 2026-02-09
FROM ghcr.io/astral-sh/uv:0.9-python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 libxml2-dev libxslt1-dev zlib1g-dev

# Deps layer — ONNX runtime (no PyTorch/FlagEmbedding)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project

# Code layer
COPY pyproject.toml uv.lock ./
COPY config.py app.py ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ====== RUNTIME STAGE ======
FROM python:3.14-slim-bookworm@sha256:a9bee15510a364124aa24692899d269835683b883de42f7ebec8c293cf679ccb AS runtime

LABEL org.opencontainers.image.source="https://github.com/yastman/rag"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libxml2 libxslt1.1 zlib1g \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser && \
    mkdir -p /models/hf /models/artifact && \
    chown -R appuser:appgroup /models

# Verify the pinned artifact (manifest presence, byte sizes, SHA-256) BEFORE
# anything is baked: the 41-byte dummy fixtures and corrupted artifacts fail
# the build here instead of silently becoming the runtime model (#3366).
COPY verify_artifact.py /tmp/verify_artifact.py
RUN --mount=type=bind,from=bge_m3_onnx_model,target=/tmp/bge-m3-onnx,readonly \
    python /tmp/verify_artifact.py --dir /tmp/bge-m3-onnx \
      --manifest /tmp/bge-m3-onnx/artifact_manifest.json && \
    mkdir -p /models/artifact/tokenizer && \
    cp /tmp/bge-m3-onnx/model.onnx /tmp/bge-m3-onnx/model.onnx_data /models/artifact/ && \
    cp /tmp/bge-m3-onnx/tokenizer/. /models/artifact/tokenizer/ && \
    cp /tmp/bge-m3-onnx/artifact_manifest.json /models/artifact/ && \
    chown -R appuser:appgroup /models/artifact && \
    rm /tmp/verify_artifact.py

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/config.py /app/app.py ./
COPY --chown=appuser:appgroup verify_artifact.py smoke_offline.py ./

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf \
    ONNX_MODEL_DIR=/models/artifact \
    TOKENIZER_DIR=/models/artifact/tokenizer \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "4"]
