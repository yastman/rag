# syntax=docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f543c0d03998580f9cb89
# Telegram Bot — single uv authority (#3210)
#
# Dependency resolution uses the repo-root pyproject.toml + uv.lock
# (`--extra telegram`) — the ONLY authority for the Telegram runtime.
# The former telegram_bot/pyproject.toml + telegram_bot/uv.lock nested
# authority drifted from root (LiteLLM 1.88.1 vs 1.98.0, OpenAI 2.37.0
# vs 2.54.0, redisvl 0.18.2 vs 0.23.0) and was retired by #3210.

# ====== BUILD STAGE ======
FROM ghcr.io/astral-sh/uv:0.9-python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder

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
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --extra telegram --no-install-project

# Manifest layer (busts cache when the root manifest/lock changes)
COPY pyproject.toml uv.lock ./

# Reconcile .venv with the exact root lock after a manifest change
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra telegram

# ====== RUNTIME STAGE ======
FROM python:3.13-slim-bookworm@sha256:e4fa1f978c539608a10cdf74700ac32a3f719dfc6e8b6b6001da82deb36302a2 AS runtime

LABEL org.opencontainers.image.source="https://github.com/yastman/rag"

WORKDIR /app

# Install procps for pgrep-based HEALTHCHECK
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && apt-get install -y --no-install-recommends procps

RUN groupadd -g 1001 botgroup && \
    useradd -u 1001 -g botgroup -m -s /bin/false botuser

COPY --from=builder --chown=botuser:botgroup /app/.venv /app/.venv
COPY --chown=botuser:botgroup telegram_bot/ ./telegram_bot/
COPY --chown=botuser:botgroup src/ ./src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER botuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD pgrep -f "telegram_bot.main" || exit 1

CMD ["python", "-m", "telegram_bot.main"]
