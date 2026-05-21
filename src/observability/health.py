"""Health check endpoint registry for all platform services."""

from __future__ import annotations


# HTTP health endpoints keyed by service name
HEALTH_ENDPOINTS: dict[str, str] = {
    "rag-api": "http://localhost:8080/health",
    "mini-app-api": "http://localhost:8090/health",
    "bge-m3": "http://localhost:8000/health",
    "user-base": "http://localhost:8003/health",
    "docling": "http://localhost:5001/health",
    "litellm": "http://localhost:4000/health/liveliness",
    "qdrant": "http://localhost:6333/readyz",
    "langfuse": "http://localhost:3001/api/public/health",
    "loki": "http://localhost:3100/ready",
    "alertmanager": "http://localhost:9093/-/healthy",
}

# Non-HTTP health checks (shell commands)
HEALTH_CHECKS_NON_HTTP: dict[str, str] = {
    "redis": "redis-cli PING",
    "postgres": "pg_isready -U postgres",
    "bot": "pgrep -f telegram_bot.main",
}
