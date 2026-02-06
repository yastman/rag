# syntax=docker/dockerfile:1
# Telegram Bot Dockerfile — uv SDK pattern (Context7 best practices 2026)

# ====== BUILD STAGE ======
# Use uv pre-installed image as builder (SDK approach)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install build dependencies with apt cache mount
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++

# Install Python dependencies (bind mount — no COPY layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=telegram_bot/requirements.txt,target=requirements.txt \
    uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install -r requirements.txt

# ====== RUNTIME STAGE ======
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code (changes most often — last layer)
COPY telegram_bot/ ./telegram_bot/

# Create non-root user
RUN groupadd -g 1001 botgroup && \
    useradd -u 1001 -g botgroup -m -s /bin/false botuser && \
    chown -R botuser:botgroup /app
USER botuser

# Health check (lightweight — just verify process is running)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, signal; os.kill(1, 0)" || exit 1

CMD ["python", "-m", "telegram_bot.main"]
