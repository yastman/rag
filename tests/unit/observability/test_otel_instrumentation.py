"""Unit tests for OTEL auto-instrumentation activation (#2225).

The Langfuse v4 SDK runs on top of OpenTelemetry. By default the SDK only emits
spans for code wrapped in ``@observe``; everything *underneath* the Python
function — outbound HTTP, Postgres queries, Redis SET/GET, gRPC to Qdrant —
is invisible. This is the «black hole between ``@observe(name='kommo-create-
lead')`` and the actual HTTP call» problem from the audit (#2215, Pass 4).

The fix is SDK-native: activate the official ``opentelemetry-instrumentation-*``
packages once at boot. After that:

* Every outbound httpx/aiohttp request gets ``HTTP <method> <url>`` child spans
  with ``http.method``, ``http.status_code``, ``http.url`` semantic attributes
  *and* the ``traceparent`` header injected automatically (closes most of
  Epic P #2226 manual plumbing).
* Every asyncpg query gets a ``db`` span.
* Every Redis command gets a ``redis`` span.
* Every gRPC call (Qdrant) gets a client span.

These tests pin the activation contract:

1. ``activate_otel_instrumentations()`` calls ``.instrument()`` on every
   available instrumentor exactly once per process.
2. Calling it twice is a no-op (idempotent — guard via
   ``_is_instrumented_by_opentelemetry``-style flag at module level).
3. Missing optional deps are tolerated (``ImportError`` -> instrumentor
   silently skipped, others continue).
4. ``initialize_langfuse(...)`` calls ``activate_otel_instrumentations()``
   after the Langfuse client is constructed (single boot point).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_instrumentation_state() -> None:
    """Reset the ``activate_otel_instrumentations`` idempotent flag between tests."""
    import src.observability_otel as mod

    mod._INSTRUMENTATIONS_ACTIVE = False
    yield
    mod._INSTRUMENTATIONS_ACTIVE = False


class TestActivateOtelInstrumentations:
    def test_activates_each_instrumentor_when_all_packages_available(self) -> None:
        """All five OTEL client instrumentors must be activated when present."""
        import src.observability_otel as mod

        httpx_inst = MagicMock(name="HTTPXClientInstrumentor")
        asyncpg_inst = MagicMock(name="AsyncPGInstrumentor")
        redis_inst = MagicMock(name="RedisInstrumentor")
        grpc_inst = MagicMock(name="GrpcAioInstrumentorClient")
        aiohttp_inst = MagicMock(name="AioHttpClientInstrumentor")
        logging_inst = MagicMock(name="LoggingInstrumentor")

        instrumentors = {
            "httpx": httpx_inst,
            "asyncpg": asyncpg_inst,
            "redis": redis_inst,
            "grpc_aio_client": grpc_inst,
            "aiohttp_client": aiohttp_inst,
            "logging": logging_inst,
        }
        with patch.object(mod, "_resolve_instrumentors", return_value=instrumentors):
            mod.activate_otel_instrumentations()

        for inst in instrumentors.values():
            inst.return_value.instrument.assert_called_once()

    def test_is_idempotent_within_a_process(self) -> None:
        """Calling ``activate_otel_instrumentations()`` twice must not double-instrument."""
        import src.observability_otel as mod

        httpx_inst = MagicMock(name="HTTPXClientInstrumentor")
        with patch.object(mod, "_resolve_instrumentors", return_value={"httpx": httpx_inst}):
            mod.activate_otel_instrumentations()
            mod.activate_otel_instrumentations()

        # Each instrumentor class is instantiated once and ``.instrument()`` is
        # called once across both invocations — second call is a guard no-op.
        assert httpx_inst.return_value.instrument.call_count == 1

    def test_tolerates_missing_optional_packages(self) -> None:
        """When an instrumentor package is absent, ``_resolve_instrumentors``
        silently omits it and the rest still activate."""
        import src.observability_otel as mod

        # Only httpx + redis available; asyncpg/grpc/aiohttp/logging missing.
        httpx_inst = MagicMock(name="HTTPXClientInstrumentor")
        redis_inst = MagicMock(name="RedisInstrumentor")
        with patch.object(
            mod,
            "_resolve_instrumentors",
            return_value={"httpx": httpx_inst, "redis": redis_inst},
        ):
            # Must not raise even when other packages would be missing
            mod.activate_otel_instrumentations()

        httpx_inst.return_value.instrument.assert_called_once()
        redis_inst.return_value.instrument.assert_called_once()

    def test_swallows_individual_instrumentor_errors(self) -> None:
        """One instrumentor raising must not block the others (graceful degrade)."""
        import src.observability_otel as mod

        # httpx instrumentor blows up; redis must still activate.
        httpx_inst_class = MagicMock(name="HTTPXClientInstrumentor")
        httpx_inst_class.return_value.instrument.side_effect = RuntimeError("double-init")
        redis_inst_class = MagicMock(name="RedisInstrumentor")
        with patch.object(
            mod,
            "_resolve_instrumentors",
            return_value={"httpx": httpx_inst_class, "redis": redis_inst_class},
        ):
            mod.activate_otel_instrumentations()  # must not raise

        redis_inst_class.return_value.instrument.assert_called_once()


class TestInstrumentFastApiApp:
    def test_calls_fastapi_instrumentor_when_available(self) -> None:
        """``instrument_fastapi_app(app)`` must call ``FastAPIInstrumentor.instrument_app(app)``."""
        import src.observability_otel as mod

        fake_instrumentor_class = MagicMock(name="FastAPIInstrumentor")
        fake_app = MagicMock(name="FastAPI app")
        # Simulate a fresh app: the SDK guard flag is explicitly False (not
        # the truthy MagicMock default that would short-circuit our pre-check).
        fake_app._is_instrumented_by_opentelemetry = False
        with patch.object(
            mod, "_resolve_fastapi_instrumentor", return_value=fake_instrumentor_class
        ):
            mod.instrument_fastapi_app(fake_app)

        fake_instrumentor_class.instrument_app.assert_called_once_with(fake_app)

    def test_is_noop_when_fastapi_instrumentor_missing(self) -> None:
        import src.observability_otel as mod

        fake_app = MagicMock(name="FastAPI app")
        with patch.object(mod, "_resolve_fastapi_instrumentor", return_value=None):
            mod.instrument_fastapi_app(fake_app)  # must not raise

    def test_is_idempotent_per_app(self) -> None:
        """Re-instrumenting the same app must not call instrument_app twice."""
        import src.observability_otel as mod

        fake_instrumentor_class = MagicMock(name="FastAPIInstrumentor")
        fake_app = MagicMock(name="FastAPI app")
        # Simulate FastAPIInstrumentor's own guard: second call is a warn-and-skip
        fake_app._is_instrumented_by_opentelemetry = False

        def _instrument_app_side_effect(app):
            app._is_instrumented_by_opentelemetry = True

        fake_instrumentor_class.instrument_app.side_effect = _instrument_app_side_effect

        with patch.object(
            mod, "_resolve_fastapi_instrumentor", return_value=fake_instrumentor_class
        ):
            mod.instrument_fastapi_app(fake_app)
            mod.instrument_fastapi_app(fake_app)

        # Our wrapper must check the flag and skip a second activation
        assert fake_instrumentor_class.instrument_app.call_count == 1


class TestInitializeLangfuseHook:
    """``initialize_langfuse(...)`` must trigger ``activate_otel_instrumentations``
    once a real Langfuse client is constructed."""

    def test_initialize_langfuse_activates_instrumentations_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.observability as observability

        observability._reset_langfuse_client_for_tests()

        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)

        fake_client = MagicMock(name="Langfuse client")
        activate_mock = MagicMock(name="activate_otel_instrumentations")
        with (
            patch.object(observability, "Langfuse", return_value=fake_client),
            patch(
                "src.observability_otel.activate_otel_instrumentations",
                activate_mock,
            ),
            patch.object(observability, "sync_langfuse_model_definitions", return_value=0),
        ):
            client = observability.initialize_langfuse(force=True)

        assert client is fake_client
        activate_mock.assert_called_once()

    def test_initialize_langfuse_does_not_activate_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing keys must NOT activate instrumentations (no Langfuse client to ride)."""
        import src.observability as observability

        observability._reset_langfuse_client_for_tests()

        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        activate_mock = MagicMock(name="activate_otel_instrumentations")
        with patch("src.observability_otel.activate_otel_instrumentations", activate_mock):
            client = observability.initialize_langfuse(force=True)

        assert client is None
        activate_mock.assert_not_called()
