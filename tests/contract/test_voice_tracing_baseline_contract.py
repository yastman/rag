"""Voice tracing baseline contract (#2257).

Locks in the voice-specific OpenTelemetry wiring that the SDK baseline
(``docs/observability/VOICE_TRACING_BASELINE.md``) documents, so it cannot
silently regress:

* ``src/voice/agent.py`` must forward the active OTel ``TracerProvider`` to
  LiveKit via ``livekit.agents.telemetry.set_tracer_provider(provider)`` — this
  is the LiveKit-native hook that makes LiveKit-emitted spans land on the same
  exporter as the rest of the runtime (so voice lifecycle spans share the
  Langfuse trace tree).

The voice -> RAG hop (``src/voice/rag_api_client.py`` using ``httpx`` ->
``HTTPXClientInstrumentor``) is already locked by the cross-service contract in
``test_cross_service_trace_instrumentation_contract.py`` (#2256) and is not
re-asserted here.

SDK evidence (see the baseline doc): the LiveKit Agents telemetry API exposes
``set_tracer_provider`` (LiveKit JS API reference documents the equivalent
``setTracerProvider`` in ``@livekit/agents/telemetry``; the OpenObserve LiveKit
integration documents registering a ``TracerProvider`` via
``telemetry.set_tracer_provider()``). Content was rephrased for compliance with
licensing restrictions.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_AGENT = "src/voice/agent.py"


def _source_of(rel: str) -> str | None:
    path = REPO_ROOT / rel
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _calls_name(tree: ast.AST, name: str) -> bool:
    """True if the module invokes ``name(...)`` (bare or attribute call)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def _imports_name(tree: ast.AST, module_substr: str, name: str) -> bool:
    """True if the module does ``from <...module_substr...> import <name>``."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and module_substr in node.module
            and any(alias.name == name for alias in node.names)
        ):
            return True
    return False


def _forwards_tracer_provider(source: str) -> bool:
    tree = ast.parse(source)
    return _imports_name(tree, "livekit.agents.telemetry", "set_tracer_provider") and _calls_name(
        tree, "set_tracer_provider"
    )


class TestVoiceAgentForwardsTracerProvider:
    """The voice agent must wire LiveKit telemetry to the runtime provider."""

    def test_voice_agent_exists(self) -> None:
        assert _source_of(VOICE_AGENT) is not None, f"missing: {VOICE_AGENT}"

    def test_voice_agent_forwards_tracer_provider_to_livekit(self) -> None:
        source = _source_of(VOICE_AGENT)
        assert source is not None
        assert _forwards_tracer_provider(source), (
            f"{VOICE_AGENT} must import and call "
            f"livekit.agents.telemetry.set_tracer_provider(provider) so LiveKit "
            f"spans share the Langfuse OTel trace tree (#2257). Without it the "
            f"voice lifecycle spans would not participate in the single trace."
        )


class TestDetectorSelfChecks:
    _OK = (
        "from livekit.agents.telemetry import set_tracer_provider\nset_tracer_provider(provider)\n"
    )
    _MISSING_CALL = "from livekit.agents.telemetry import set_tracer_provider\n"
    _MISSING_IMPORT = "set_tracer_provider(provider)\n"
    _UNRELATED = "import os\nos.getenv('X')\n"

    def test_detector_accepts_import_and_call(self) -> None:
        assert _forwards_tracer_provider(self._OK)

    def test_detector_requires_the_call(self) -> None:
        assert not _forwards_tracer_provider(self._MISSING_CALL)

    def test_detector_requires_the_import(self) -> None:
        assert not _forwards_tracer_provider(self._MISSING_IMPORT)

    def test_detector_rejects_unrelated_module(self) -> None:
        assert not _forwards_tracer_provider(self._UNRELATED)
