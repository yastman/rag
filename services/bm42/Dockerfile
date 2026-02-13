# syntax=docker/dockerfile:1.21@sha256:27f9262d43452075f3c410287a2c43f5ef1bf7ec2bb06e8c9eeb1b8d453087bc
# BM42 Sparse Embedding Service - Optimized with uv

# ====== BUILD STAGE ======
# Pin base images — checked 2026-02-09
FROM python:3.14-slim-bookworm@sha256:f0540d0436a220db0a576ccfe75631ab072391e43a24b88972ef9833f699095f AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10@sha256:94a23af2d50e97b87b522d3cea24aaf8a1faedec1344c952767434f69585cbf9 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_SYSTEM_PYTHON=1 \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install \
        fastapi>=0.115.0 \
        uvicorn>=0.32.0 \
        fastembed>=0.7.0 \
        pydantic>=2.0.0

# Pre-download model during build (cached in image)
RUN mkdir -p /app/.cache/fastembed && \
    python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm42-all-minilm-l6-v2-attentions')"

# ====== RUNTIME STAGE ======
FROM python:3.14-slim-bookworm@sha256:f0540d0436a220db0a576ccfe75631ab072391e43a24b88972ef9833f699095f AS runtime

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# Copy fastembed model cache from explicit path
COPY --from=builder /app/.cache/fastembed /app/.cache/fastembed

ENV PATH="/usr/local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed

COPY --chown=appuser:appgroup main.py .

RUN chown -R appuser:appgroup /app/.cache

USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
