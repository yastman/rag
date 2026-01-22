***REMOVED*** Telegram Bot Dockerfile
***REMOVED*** Multi-stage build for smaller image size

***REMOVED*** Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

***REMOVED*** Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

***REMOVED*** Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

***REMOVED*** Install Python dependencies
COPY telegram_bot/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

***REMOVED*** Runtime stage
FROM python:3.12-slim AS runtime

WORKDIR /app

***REMOVED*** Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

***REMOVED*** Copy application code
COPY telegram_bot/ ./telegram_bot/

***REMOVED*** Create non-root user
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

***REMOVED*** Environment variables (defaults, override in docker-compose)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

***REMOVED*** Health check - verify bot module can be imported
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from telegram_bot.bot import PropertyBot" || exit 1

***REMOVED*** Run bot
CMD ["python", "-m", "telegram_bot.main"]
