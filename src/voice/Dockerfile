# syntax=docker/dockerfile:1@sha256:2780b5c3bab67f1f76c781860de469442999ed1a0d7992a5efdf2cffc0e3d769
# Voice Agent — uv sync pattern (2026 best practices)

# ====== BUILD STAGE ======
FROM ghcr.io/astral-sh/uv:0.9-python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Deps layer (cached separately from code)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --extra voice --no-install-project

# Code layer
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY telegram_bot/ telegram_bot/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra voice

# ====== RUNTIME STAGE ======
FROM python:3.14-slim-bookworm@sha256:2e256d0381371566ed96980584957ed31297f437569b79b0e5f7e17f2720e53a AS runtime
WORKDIR /app

RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -m -d /app -s /bin/false appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/telegram_bot /app/telegram_bot
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Download VAD/turn-detector models (before switching to non-root)
RUN python -c "from livekit.plugins.silero import VAD; VAD.load()" 2>/dev/null || true

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "from pathlib import Path; import sys; needle='src.voice.' + 'agent'; sys.exit(0 if any(needle in p.read_text(errors='ignore') for p in Path('/proc').glob('[0-9]*/cmdline')) else 1)"

CMD ["python", "-m", "src.voice.agent", "start"]
