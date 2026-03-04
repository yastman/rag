# syntax=docker/dockerfile:1@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
# Docling Serve — CPU-only optimized build for VPS
# Multi-stage build with uv (Context7 best practices 2026)
#
# Key optimizations:
# 1. CPU-only PyTorch (no CUDA) via --index-url
# 2. uv instead of pip (10x faster installs)
# 3. Multi-stage build (builder + runtime)
# 4. Cache mounts for apt and uv
# 5. Non-root user

# =============================================================================
# BUILD STAGE
# =============================================================================
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

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

# Create venv and install CPU-only PyTorch FIRST (critical for size)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install \
    torch \
    torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# Install docling-serve with UI support
RUN --mount=type=cache,target=/root/.cache/uv \
    VIRTUAL_ENV=/opt/venv uv pip install \
    "docling-serve[ui]>=1.0.0" \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple/

# =============================================================================
# RUNTIME STAGE
# =============================================================================
FROM python:3.12-slim-bookworm AS runtime

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
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
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
RUN chmod -R a+rw /opt/venv/lib/python*/site-packages/rapidocr/ 2>/dev/null || true

USER docling

EXPOSE 5001

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5001/health', timeout=5)" || exit 1

CMD ["docling-serve", "run"]
