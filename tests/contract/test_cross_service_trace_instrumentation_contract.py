"""Cross-service W3C TraceContext instrumentation contract (#2256).

Locks in the SDK-native cross-service propagation layer so it cannot silently
regress, and so the legacy manual BGE-M3 propagation (#2253) can be removed
safely once a runtime run proves continuity.

Contract:

* **Inbound** FastAPI services must extract W3C TraceContext on every request
  via ``FastAPIInstrumentor`` — directly (``FastAPIInstrumentor.instrument_app``)
  or through the shared ``instrument_fastapi_app(app)`` helper.
* **Outbound** HTTP clients must ride on ``httpx`` so the process-wide
  ``HTTPXClientInstrumentor`` injects ``traceparent``/``baggage`` automatically.
* The httpx instrumentation must be activated at startup
  (``activate_otel_instrumentations`` -> ``HTTPXClientInstrumentor``).

Verified against OpenTelemetry Python Contrib docs via Context7
(``/open-telemetry/opentelemetry-python-contrib``): ``instrument_app(app)`` for
inbound extraction (with a built-in double-instrumentation guard) and
``HTTPXClientInstrumentor().instrument()`` for outbound injection. Content was
rephrased for compliance with licensing restrictions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

# Inbound FastAPI entrypoints that must instrument for W3C TraceContext extraction.
INBOUND_FASTAPI_ENTRYPOINTS = [
    "services/bge-m3-api/app.py",
    "services/user-base/main.py",
    "src/api/main.py",
    "mini_app/api.py",
]

# Outbound HTTP clients that must ride on httpx so HTTPXClientInstrumentor
# injects traceparent/baggage automatically.
OUTBOUND_HTTPX_CLIENTS = [
    "src/services/bge_m3_client.py",
    "src/services/kommo_client.py",
    "src/voice/rag_api_client.py",
    "src/ingestion/docling_client.py",
    # Additional clients discovered during #2256 fan-out audit:
    "src/services/kommo_tokens.py",
    "src/services/vectorizers.py",
    "src/runtime/integrations/embeddings.py",
]

# Startup site that activates the auto-instrumentations (incl. httpx).
HTTPX_ACTIVATION_INVOCATION = "src/observability.py"
HTTPX_ACTIVATION_IMPL = "src/observability_otel.py"

# Either the shared helper (Name call) or the raw instrumentor method (attr call).
_FASTAPI_INSTRUMENT_NAMES = {"instrument_fastapi_app", "instrument_app"}

# Non-httpx HTTP client libraries whose presence in any OUTBOUND_HTTPX_CLIENTS
# file would silently bypass the process-wide HTTPXClientInstrumentor.
# Even a single ``import requests`` (or ``from aiohttp import ...``) alongside
# existing ``import httpx`` can create a trace-context leak: the process-wide
# instrumentor only injects ``traceparent``/``baggage`` into httpx, not these.
_NON_HTTPX_HTTP_CLIENT_MODULES: frozenset[str] = frozenset(
    {
        "requests",
        "aiohttp",
        "urllib3",
        "http.client",
    }
)
_NON_HTTPX_HTTP_CLIENT_FROM_IMPORTS: dict[str, frozenset[str]] = {
    "urllib": frozenset({"request"}),
    "http": frozenset({"client"}),
}


def _source_of(rel: str) -> str | None:
    path = REPO_ROOT / rel
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _called_names(tree: ast.AST) -> set[str]:
    """Collect both ``name(...)`` and ``obj.attr(...)`` call targets."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            found.add(func.id)
        elif isinstance(func, ast.Attribute):
            found.add(func.attr)
    return found


def _is_fastapi_instrumented(source: str) -> bool:
    """True if the module invokes the FastAPI instrumentation (helper or raw)."""
    tree = ast.parse(source)
    return bool(_called_names(tree) & _FASTAPI_INSTRUMENT_NAMES)


def _imports_httpx(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "httpx" or alias.name.startswith("httpx.") for alias in node.names
        ):
            return True
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module == "httpx" or node.module.startswith("httpx."))
        ):
            return True
    return False


def _invokes(source: str, name: str) -> bool:
    return name in _called_names(ast.parse(source))


def _imports_non_httpx_http_client(source: str) -> list[str]:
    """Return names of non-httpx HTTP client modules imported in *source*.

    Only modules in ``_NON_HTTPX_HTTP_CLIENT_MODULES`` are considered.
    An empty list means the source is clean.
    """
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in _NON_HTTPX_HTTP_CLIENT_MODULES or alias.name == "urllib.request":
                    found.append(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module in _NON_HTTPX_HTTP_CLIENT_MODULES or node.module == "urllib.request":
                found.append(node.module)
                continue
            denied_names = _NON_HTTPX_HTTP_CLIENT_FROM_IMPORTS.get(node.module)
            if denied_names:
                for alias in node.names:
                    if alias.name in denied_names:
                        found.append(f"{node.module}.{alias.name}")
    return found


# --- inbound -----------------------------------------------------------------


class TestInboundFastAPIInstrumented:
    """Every internal FastAPI service must extract W3C TraceContext."""

    @pytest.mark.parametrize("rel", INBOUND_FASTAPI_ENTRYPOINTS)
    def test_entrypoint_exists(self, rel: str) -> None:
        assert _source_of(rel) is not None, f"FastAPI entrypoint missing: {rel}"

    @pytest.mark.parametrize("rel", INBOUND_FASTAPI_ENTRYPOINTS)
    def test_entrypoint_instruments_fastapi(self, rel: str) -> None:
        source = _source_of(rel)
        assert source is not None, f"missing: {rel}"
        assert _is_fastapi_instrumented(source), (
            f"{rel} must call FastAPIInstrumentor.instrument_app(app) or "
            f"instrument_fastapi_app(app) so inbound requests continue the "
            f"caller's W3C trace (#2256). Without it the service starts a new "
            f"root trace and the workflow fragments."
        )


# --- outbound ----------------------------------------------------------------


class TestOutboundHttpxCoverage:
    """Every outbound HTTP client must ride on httpx (-> HTTPXClientInstrumentor)."""

    @pytest.mark.parametrize("rel", OUTBOUND_HTTPX_CLIENTS)
    def test_client_exists(self, rel: str) -> None:
        assert _source_of(rel) is not None, f"outbound client missing: {rel}"

    @pytest.mark.parametrize("rel", OUTBOUND_HTTPX_CLIENTS)
    def test_client_uses_httpx(self, rel: str) -> None:
        source = _source_of(rel)
        assert source is not None, f"missing: {rel}"
        assert _imports_httpx(source), (
            f"{rel} must use httpx so the process-wide HTTPXClientInstrumentor "
            f"injects traceparent/baggage automatically (#2256). A different "
            f"HTTP library would silently drop cross-service trace context."
        )

    @pytest.mark.parametrize("rel", OUTBOUND_HTTPX_CLIENTS)
    def test_client_rejects_non_httpx_http_library(self, rel: str) -> None:
        """No outbound client may import a non-httpx HTTP library alongside httpx.

        ``import httpx`` alongside ``import requests`` (or ``aiohttp``,
        ``urllib``, ``urllib3``, ``http.client``) would silently bypass the
        process-wide ``HTTPXClientInstrumentor``: only httpx calls get
        ``traceparent``/``baggage`` injected. A single stray
        ``requests.get()`` is enough to drop cross-service trace context.
        """
        source = _source_of(rel)
        assert source is not None, f"missing: {rel}"
        offenders = _imports_non_httpx_http_client(source)
        assert not offenders, (
            f"{rel} imports non-httpx HTTP client(s) that would bypass "
            f"HTTPXClientInstrumentor and silently drop W3C TraceContext "
            f"(#2256): {sorted(offenders)}. All outbound HTTP must go through "
            f"httpx so traceparent/baggage injection is automatic."
        )


# --- activation --------------------------------------------------------------


class TestHttpxInstrumentationActivated:
    """The httpx auto-instrumentation must be wired at startup."""

    def test_activation_invoked(self) -> None:
        source = _source_of(HTTPX_ACTIVATION_INVOCATION)
        assert source is not None, f"missing: {HTTPX_ACTIVATION_INVOCATION}"
        assert _invokes(source, "activate_otel_instrumentations"), (
            f"{HTTPX_ACTIVATION_INVOCATION} must invoke "
            f"activate_otel_instrumentations() at startup (#2256/#2225)."
        )

    def test_activation_covers_httpx(self) -> None:
        source = _source_of(HTTPX_ACTIVATION_IMPL)
        assert source is not None, f"missing: {HTTPX_ACTIVATION_IMPL}"
        assert "HTTPXClientInstrumentor" in source, (
            f"{HTTPX_ACTIVATION_IMPL} must activate HTTPXClientInstrumentor so "
            f"outbound httpx requests carry W3C TraceContext (#2256/#2225)."
        )


# --- non-vacuity -------------------------------------------------------------


class TestScannerIsNotVacuous:
    def test_lists_are_populated(self) -> None:
        assert INBOUND_FASTAPI_ENTRYPOINTS
        assert OUTBOUND_HTTPX_CLIENTS


# --- detector self-checks (regression proof) ---------------------------------


class TestDetectorsCatchRegressions:
    _FASTAPI_OK_HELPER = "from x import instrument_fastapi_app\ninstrument_fastapi_app(app)\n"
    _FASTAPI_OK_RAW = (
        "from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor\n"
        "FastAPIInstrumentor.instrument_app(app)\n"
    )
    _FASTAPI_MISSING = "app = FastAPI()\n@app.get('/')\ndef root():\n    return {}\n"

    _HTTPX_IMPORT = "import httpx\nclient = httpx.AsyncClient()\n"
    _HTTPX_FROM = "from httpx import AsyncClient\nclient = AsyncClient()\n"
    _NO_HTTPX = "import requests\nrequests.get('http://x')\n"

    # Denylist probes: mixed httpx + non-httpx imports, or pure non-httpx.
    _MIXED_HTTPX_REQUESTS = "import httpx\nimport requests\nclient = httpx.AsyncClient()\n"
    _MIXED_HTTPX_AIOHTTP = "from httpx import AsyncClient\nfrom aiohttp import ClientSession\n"
    _MIXED_HTTPX_URLLIB_SUBMOD = "import httpx\nimport urllib.request\n"
    _MIXED_HTTPX_URLLIB_FROM = "import httpx\nfrom urllib import request\n"
    _MIXED_HTTPX_HTTP_FROM = "import httpx\nfrom http import client\n"
    _PURE_URLLIB_PARSE = "import urllib.parse\nurllib.parse.urlencode({'a': 'b'})\n"
    _PURE_AIOHTTP = "from aiohttp import ClientSession\n"
    _PURE_URLLIB3 = "import urllib3\nhttp = urllib3.PoolManager()\n"

    def test_fastapi_detector_accepts_helper(self) -> None:
        assert _is_fastapi_instrumented(self._FASTAPI_OK_HELPER)

    def test_fastapi_detector_accepts_raw_instrumentor(self) -> None:
        assert _is_fastapi_instrumented(self._FASTAPI_OK_RAW)

    def test_fastapi_detector_flags_missing(self) -> None:
        assert not _is_fastapi_instrumented(self._FASTAPI_MISSING)

    def test_httpx_detector_accepts_import(self) -> None:
        assert _imports_httpx(self._HTTPX_IMPORT)

    def test_httpx_detector_accepts_from_import(self) -> None:
        assert _imports_httpx(self._HTTPX_FROM)

    def test_httpx_detector_flags_other_lib(self) -> None:
        assert not _imports_httpx(self._NO_HTTPX)

    # --- denylist self-checks -------------------------------------------------

    def test_denylist_accepts_pure_httpx(self) -> None:
        """A file that only imports httpx must NOT trigger the denylist."""
        assert _imports_non_httpx_http_client(self._HTTPX_IMPORT) == []

    def test_denylist_flags_mixed_httpx_requests(self) -> None:
        """import httpx + import requests: the denylist MUST catch requests."""
        offenders = _imports_non_httpx_http_client(self._MIXED_HTTPX_REQUESTS)
        assert offenders, "mixed httpx + requests went undetected — the denylist is broken"
        assert "requests" in offenders

    def test_denylist_flags_mixed_httpx_aiohttp(self) -> None:
        """from httpx + from aiohttp: the denylist MUST catch aiohttp."""
        offenders = _imports_non_httpx_http_client(self._MIXED_HTTPX_AIOHTTP)
        assert offenders, "mixed httpx + aiohttp went undetected — the denylist is broken"
        assert "aiohttp" in offenders

    def test_denylist_flags_urllib_submodule(self) -> None:
        """import urllib.request: the denylist MUST catch the submodule path."""
        offenders = _imports_non_httpx_http_client(self._MIXED_HTTPX_URLLIB_SUBMOD)
        assert offenders, "urllib.request went undetected — the denylist is broken"
        assert "urllib.request" in offenders

    def test_denylist_flags_urllib_request_from_import(self) -> None:
        """from urllib import request: the denylist MUST catch the HTTP client."""
        offenders = _imports_non_httpx_http_client(self._MIXED_HTTPX_URLLIB_FROM)
        assert offenders
        assert "urllib.request" in offenders

    def test_denylist_flags_http_client_from_import(self) -> None:
        """from http import client: the denylist MUST catch the HTTP client."""
        offenders = _imports_non_httpx_http_client(self._MIXED_HTTPX_HTTP_FROM)
        assert offenders
        assert "http.client" in offenders

    def test_denylist_accepts_urllib_parse(self) -> None:
        """urllib.parse is URL manipulation, not an HTTP client."""
        assert _imports_non_httpx_http_client(self._PURE_URLLIB_PARSE) == []

    def test_denylist_flags_pure_aiohttp(self) -> None:
        """A file with only aiohttp (no httpx) is also caught — belt + suspenders."""
        offenders = _imports_non_httpx_http_client(self._PURE_AIOHTTP)
        assert offenders
        assert "aiohttp" in offenders

    def test_denylist_flags_pure_urllib3(self) -> None:
        """A file with only urllib3 (no httpx) is also caught."""
        offenders = _imports_non_httpx_http_client(self._PURE_URLLIB3)
        assert offenders
        assert "urllib3" in offenders
