FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY telegram_bot/ telegram_bot/
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/telegram_bot /app/telegram_bot
ENV PATH="/app/.venv/bin:$PATH"

# Download VAD/turn-detector models
RUN python -c "from livekit.plugins.silero import VAD; VAD.load()" 2>/dev/null || true

CMD ["python", "-m", "src.voice.agent", "start"]
