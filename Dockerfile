FROM python:3.12-slim

WORKDIR /app

***REMOVED*** Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

***REMOVED*** Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

***REMOVED*** Copy application code
COPY . .

***REMOVED*** Create non-root user
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

***REMOVED*** Run bot
CMD ["python", "-m", "telegram_bot.main"]
