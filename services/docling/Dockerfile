# syntax=docker/dockerfile:1@sha256:2780b5c3bab67f1f76c781860de469442999ed1a0d7992a5efdf2cffc0e3d769
# Docling Serve — CPU-only optimized build for VPS
# Multi-stage build with uv (Context7 best practices 2026)
#
# Key optimizations:
# 1. CPU-only PyTorch (no CUDA) via uv lockfile + pytorch-cpu index
# 2. uv sync instead of pip install (lockfile-backed, reproducible)
# 3. Multi-stage build (builder + runtime)
# 4. Cache mounts for apt and uv
# 5. Non-root user

# =============================================================================
# BUILD STAGE
# =============================================================================
FROM ghcr.io/astral-sh/uv:0.9-python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install build dependencies with apt cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++

# Deps layer (cached separately from code)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra docling

# =============================================================================
# RUNTIME STAGE
# =============================================================================
FROM python:3.14-slim-bookworm@sha256:2e256d0381371566ed96980584957ed31297f437569b79b0e5f7e17f2720e53a AS runtime

LABEL org.opencontainers.image.source="https://github.com/yastman/rag"

WORKDIR /app

# Install minimal runtime dependencies with apt cache
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    fonts-liberation

# Create non-root user
RUN groupadd -g 1001 docling && \
    useradd -u 1001 -g docling -m -d /app -s /bin/false docling

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=5001 \
    DOCLING_BACKEND=docling \
    DOCLING_PDF_BACKEND=dlparse_v2 \
    DOCLING_TABLE_MODE=accurate \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

# Create cache directory with proper permissions
RUN mkdir -p /app/.cache/huggingface && \
    chown -R docling:docling /app/.cache

# RapidOCR downloads models at runtime
RUN chmod -R a+rw /app/.venv/lib/python*/site-packages/rapidocr/ 2>/dev/null || true

USER docling

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health', timeout=5)" || exit 1

CMD ["docling-serve", "run"]
