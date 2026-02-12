# syntax=docker/dockerfile:1@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
# Telegram Bot — uv sync pattern (2026 best practices)

# ====== BUILD STAGE ======
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install build deps
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends gcc g++

# Deps layer (cached separately from code)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=telegram_bot/pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=telegram_bot/uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project

# Code layer
COPY telegram_bot/pyproject.toml telegram_bot/uv.lock ./
COPY telegram_bot/ ./telegram_bot/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ====== RUNTIME STAGE ======
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

RUN groupadd -g 1001 botgroup && \
    useradd -u 1001 -g botgroup -m -s /bin/false botuser

COPY --from=builder --chown=botuser:botgroup /app/.venv /app/.venv
COPY --chown=botuser:botgroup telegram_bot/ ./telegram_bot/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER botuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, signal; os.kill(1, 0)" || exit 1

CMD ["python", "-m", "telegram_bot.main"]
