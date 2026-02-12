# syntax=docker/dockerfile:1.4@sha256:9ba7531bd80fb0a858632727cf7a112fbfd19b17e94c4e84ced81e24ef1a0dbc
# BM42 Sparse Embedding Service - Optimized with uv

# ====== BUILD STAGE ======
# Pin base images — checked 2026-02-09
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

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
FROM python:3.12-slim-bookworm AS runtime

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
