# syntax=docker/dockerfile:1
# Root Dockerfile — uv SDK pattern (mirrors telegram_bot/Dockerfile)

# ====== BUILD STAGE ======
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
    gcc

# Install Python dependencies (bind mount — no COPY layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install -r requirements.txt

# ====== RUNTIME STAGE ======
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Create non-root user before COPY --chown
RUN groupadd -g 1001 botgroup && \
    useradd -u 1001 -g botgroup -m -s /bin/false botuser

# Copy virtual environment from builder (--chown avoids extra layer)
COPY --from=builder --chown=botuser:botgroup /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code (changes most often — last layer)
COPY --chown=botuser:botgroup . .

USER botuser

CMD ["python", "-m", "telegram_bot.main"]
