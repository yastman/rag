# syntax=docker/dockerfile:1@sha256:4a43a54dd1fedceb30ba47e76cfcf2b47304f4161c0caeac2db1c61804ea3c91
# USER-base Embedding Service — uv sync (2026 best practices)

# ====== BUILD STAGE ======
# Pin uv version — checked 2026-02-09
FROM ghcr.io/astral-sh/uv:0.9-python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends gcc g++ libgomp1

# Deps layer
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project

# Code layer (single-file app, no package to install)
COPY pyproject.toml uv.lock ./
COPY main.py ./

# ====== RUNTIME STAGE ======
FROM python:3.14-slim-bookworm@sha256:55e465cb7e50cd1d7217fcb5386aa87d0356ca2cd790872142ef68d9ef6812b4 AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m -d /app -s /bin/false appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/main.py ./

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/models/hf \
    TRANSFORMERS_CACHE=/models/hf \
    SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Pre-create model cache paths with appuser ownership.
# This avoids permission errors when a fresh named volume is initialized from image contents.
RUN mkdir -p /models/hf /models/sentence-transformers && \
    chown -R appuser:appgroup /models

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
