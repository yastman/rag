"""OpenTelemetry auto-instrumentation activation (#2225).

Langfuse v4 SDK is built on top of OpenTelemetry: ``@observe`` produces OTEL
spans that flow through the global ``TracerProvider`` to the Langfuse OTLP
exporter. By default that means we trace only the Python functions wrapped in
``@observe`` — everything *underneath* (outbound httpx, asyncpg queries,
Redis commands, gRPC to Qdrant, the FastAPI request itself) is invisible.

This module activates the official ``opentelemetry-instrumentation-*``
packages once at boot. After activation:

* Every outbound httpx/aiohttp request gets an HTTP client span with
  ``http.method`` / ``http.status_code`` / ``http.url`` semantic attributes
  *and* the ``traceparent`` header injected automatically. This is the
  SDK-native equivalent of the manual ``inject(headers)`` plumbing #2229
  added in 10 places of ``src/services/bge_m3_client.py`` — that code can
  be removed once Epic P (#2226) lands.
* Every asyncpg query produces a ``db`` span with ``db.system='postgresql'``,
  ``db.statement`` (sanitized), ``net.peer.name``.
* Every Redis command produces a ``redis`` span.
* Every gRPC call (Qdrant) produces a client span.
* ``LoggingInstrumentor`` injects ``otelTraceID`` / ``otelSpanID`` into every
  ``LogRecord`` so JSON logs can be correlated with Langfuse traces (closes
  the operational gap from Epic G #2217).

For FastAPI servers, call :func:`instrument_fastapi_app(app)` from each
service's ``lifespan`` (mini-app-api, rag-api, bge-m3-api, user-base). This
is the SDK-native replacement for the manual ``propagate.extract``/``attach``
middleware added in #2229.

Design notes (see Langfuse SDK ``code_review.md``):

* Idempotent: re-calling :func:`activate_otel_instrumentations` is a no-op.
* Graceful degradation: missing optional packages are silently skipped — a
  missing ``opentelemetry-instrumentation-asyncpg`` does not break startup.
* Per-instrumentor try/except: one failing instrumentor does not block the
  others.
* Test-friendly: every instrumentor lookup goes through
  :func:`_resolve_instrumentors` / :func:`_resolve_fastapi_instrumentor` so
  unit tests can patch the import surface without touching real packages.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


# Module-level idempotency guard. Mirrors the
# ``app._is_instrumented_by_opentelemetry`` flag that ``FastAPIInstrumentor``
# itself uses for per-app idempotency — but at process scope, since client
# instrumentors (httpx, asyncpg, redis, ...) wrap the underlying library
# globally and re-instrumenting is a logged warning at best, double-wrap at
# worst.
_INSTRUMENTATIONS_ACTIVE: bool = False


# ---------------------------------------------------------------------------
# Instrumentor resolution (test-friendly indirection layer)
# ---------------------------------------------------------------------------


def _resolve_instrumentors() -> dict[str, type]:
    """Return a mapping ``{slug: InstrumentorClass}`` for every available
    OTEL client instrumentor.

    Each ``opentelemetry-instrumentation-*`` package is optional. We return
    only the ones that imported successfully — missing packages are silently
    omitted. The slug is a stable key for logging and tests.

    Slugs and their packages:

    * ``httpx``           -> ``opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor``
    * ``asyncpg``         -> ``opentelemetry.instrumentation.asyncpg.AsyncPGInstrumentor``
    * ``redis``           -> ``opentelemetry.instrumentation.redis.RedisInstrumentor``
    * ``grpc_aio_client`` -> ``opentelemetry.instrumentation.grpc.GrpcAioInstrumentorClient``
    * ``aiohttp_client``  -> ``opentelemetry.instrumentation.aiohttp_client.AioHttpClientInstrumentor``
    * ``requests``        -> ``opentelemetry.instrumentation.requests.RequestsInstrumentor``
    * ``logging``         -> ``opentelemetry.instrumentation.logging.LoggingInstrumentor``
    """
    resolved: dict[str, type] = {}

    def _try(slug: str, module_path: str, class_name: str) -> None:
        try:
            module = __import__(module_path, fromlist=[class_name])
            resolved[slug] = getattr(module, class_name)
        except Exception as exc:  # ImportError or any other init issue
            logger.debug("OTEL instrumentor %s unavailable: %s", slug, exc)

    _try("httpx", "opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor")
    _try("asyncpg", "opentelemetry.instrumentation.asyncpg", "AsyncPGInstrumentor")
    _try("redis", "opentelemetry.instrumentation.redis", "RedisInstrumentor")
    _try("grpc_aio_client", "opentelemetry.instrumentation.grpc", "GrpcAioInstrumentorClient")
    _try(
        "aiohttp_client",
        "opentelemetry.instrumentation.aiohttp_client",
        "AioHttpClientInstrumentor",
    )
    _try("requests", "opentelemetry.instrumentation.requests", "RequestsInstrumentor")
    _try("logging", "opentelemetry.instrumentation.logging", "LoggingInstrumentor")

    return resolved


def _resolve_fastapi_instrumentor() -> Any | None:
    """Return ``FastAPIInstrumentor`` class if the package is installed, else None."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        return FastAPIInstrumentor
    except Exception as exc:
        logger.debug("OTEL FastAPI instrumentor unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def activate_otel_instrumentations() -> None:
    """Activate every available OTEL client instrumentor exactly once.

    Called from :func:`src.observability.initialize_langfuse` after the
    Langfuse client is constructed, so the OTLP exporter is already wired
    when the first auto-traced span lands.

    This function is **idempotent** — calling it twice is a no-op. Each
    instrumentor activates inside its own try/except so a failure in one
    (e.g. ``opentelemetry-instrumentation-redis`` raising on a Redis client
    library version mismatch) does not block the others.
    """
    global _INSTRUMENTATIONS_ACTIVE

    if _INSTRUMENTATIONS_ACTIVE:
        logger.debug("OTEL instrumentations already active; skipping re-activation")
        return

    instrumentors = _resolve_instrumentors()
    if not instrumentors:
        logger.info(
            "No OTEL instrumentor packages found; @observe spans will not be "
            "augmented with HTTP/DB/cache child spans (#2225). Install "
            "opentelemetry-instrumentation-{httpx,asyncpg,redis,grpc,...} to "
            "close the gap."
        )
        _INSTRUMENTATIONS_ACTIVE = True
        return

    for slug, instrumentor_class in instrumentors.items():
        try:
            instrumentor_class().instrument()
            logger.debug("OTEL instrumentation activated: %s", slug)
        except Exception:
            # Most common failure mode: package version mismatch with the
            # underlying client (e.g. redis-py 7 vs an older instrumentor
            # release). Log and keep going — partial coverage is better than
            # none.
            logger.warning(
                "OTEL instrumentor %s failed to activate; auto-spans for this "
                "library will be missing",
                slug,
                exc_info=True,
            )

    _INSTRUMENTATIONS_ACTIVE = True
    logger.info(
        "OTEL auto-instrumentations activated: %s (#2225)",
        ", ".join(sorted(instrumentors.keys())),
    )


def instrument_fastapi_app(app: Any) -> None:
    """Instrument a FastAPI app with the OTEL ASGI middleware.

    SDK-native replacement for the manual ``propagate.extract``/``attach``
    middleware added in #2229. After this call:

    * Every incoming request extracts ``traceparent`` and ``baggage`` headers
      automatically and seeds the OTEL context, so any subsequent ``@observe``
      span nests under the originating cross-service trace.
    * Every request gets a server span with ``http.method``, ``http.route``,
      ``http.status_code``, ``net.peer.ip`` semantic attributes.

    Idempotent per app via the ``_is_instrumented_by_opentelemetry`` flag
    that ``FastAPIInstrumentor.instrument_app`` itself sets — but we read it
    *before* calling so we don't trip the SDK's «Attempting to instrument
    FastAPI app while already instrumented» warning on accidental
    re-invocation.

    Args:
        app: A ``fastapi.FastAPI`` instance.
    """
    instrumentor_class = _resolve_fastapi_instrumentor()
    if instrumentor_class is None:
        logger.debug(
            "FastAPI app not instrumented: opentelemetry-instrumentation-fastapi "
            "is not available (#2225)"
        )
        return

    if getattr(app, "_is_instrumented_by_opentelemetry", False):
        logger.debug("FastAPI app already instrumented; skipping re-activation")
        return

    try:
        instrumentor_class.instrument_app(app)
        logger.debug("FastAPI app instrumented (#2225)")
    except Exception:
        logger.warning(
            "FastAPIInstrumentor.instrument_app failed; the manual #2229 "
            "FastAPI middleware in services/bge-m3-api/app.py remains the "
            "fallback for trace context extraction",
            exc_info=True,
        )
