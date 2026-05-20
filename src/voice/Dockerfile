***REMOVED*** syntax=docker/dockerfile:1@sha256:2780b5c3bab67f1f76c781860de469442999ed1a0d7992a5efdf2cffc0e3d769
***REMOVED*** Voice Agent — uv sync pattern (2026 best practices)
***REMOVED*** NOTE: Using Python 3.13 to match all other services. See issue ***REMOVED***1548.

***REMOVED*** ====== BUILD STAGE ======
FROM ghcr.io/astral-sh/uv:0.9-python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

***REMOVED*** Deps layer (cached separately from code)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --extra voice --no-install-project

***REMOVED*** Code layer
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY telegram_bot/ telegram_bot/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra voice

***REMOVED*** ====== RUNTIME STAGE ======
FROM python:3.14-slim-bookworm@sha256:a9bee15510a364124aa24692899d269835683b883de42f7ebec8c293cf679ccb AS runtime
WORKDIR /app

RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -m -d /app -s /bin/false appuser

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/telegram_bot /app/telegram_bot
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

***REMOVED*** Download VAD/turn-detector models (before switching to non-root)
RUN python -c "from livekit.plugins.silero import VAD; VAD.load()" 2>/dev/null || true

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -m src.voice.healthcheck || exit 1

CMD ["python", "-m", "src.voice.agent", "start"]
