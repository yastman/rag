FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra voice --no-install-project
COPY src/ src/
COPY telegram_bot/ telegram_bot/
RUN uv sync --frozen --no-dev --extra voice

FROM python:3.14-slim-bookworm@sha256:f0540d0436a220db0a576ccfe75631ab072391e43a24b88972ef9833f699095f AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/telegram_bot /app/telegram_bot
ENV PATH="/app/.venv/bin:$PATH"

# Download VAD/turn-detector models
RUN python -c "from livekit.plugins.silero import VAD; VAD.load()" 2>/dev/null || true

CMD ["python", "-m", "src.voice.agent", "start"]
