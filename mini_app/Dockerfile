# syntax=docker/dockerfile:1@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6
# Mini App FastAPI backend — uv sync pattern (2026 best practices)

# ====== BUILD STAGE ======
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Deps layer (cached separately from code)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-dev --no-install-project --extra mini-app

# Code layer
COPY pyproject.toml uv.lock ./
COPY mini_app/ mini_app/
COPY telegram_bot/ telegram_bot/
COPY src/ src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra mini-app

# ====== RUNTIME STAGE ======
FROM python:3.14-slim-bookworm@sha256:5404df00cf00e6e7273375f415651837b4d192ac6859c44d3b740888ac798c99 AS runtime

WORKDIR /app

RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -m -d /app -s /bin/false appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/mini_app /app/mini_app
COPY --from=builder --chown=appuser:appuser /app/telegram_bot /app/telegram_bot
COPY --from=builder --chown=appuser:appuser /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8090/health', timeout=5)"

CMD ["uvicorn", "mini_app.api:app", "--host", "0.0.0.0", "--port", "8090"]
