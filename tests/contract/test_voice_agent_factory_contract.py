"""Contract: ``create_voice_agent`` lives in ``telegram_bot/agents/voice_agent.py``.

Slice 3 of the voice-path migration to ``create_agent`` (ADR-0010,
parent #1535 / #2051). This module assembles the
``GuardMiddleware`` (#2052), ``ClassifyMiddleware`` (Slice 2.5) and
``SemanticCacheMiddleware`` (Slice 2) on top of the existing
``rag_search`` tool, returning a compiled agent ready for
``handle_voice``'s rewire (Slice 5).

The contract pins:

1. ``telegram_bot.agents.voice_agent`` exposes ``VoiceAgentState``
   (custom ``AgentState`` with the voice-specific NotRequired fields
   listed in ADR-0010) and ``create_voice_agent`` (factory).
2. ``create_voice_agent`` is a callable accepting
   ``cache`` / ``embeddings`` / ``model`` keyword arguments — the
   minimum dependency surface needed to wire the middleware stack.
3. The module does not import aiogram / fastapi / qdrant_client at
   module scope, so the factory is unit testable in isolation.
4. ``VoiceAgentState`` declares the voice-specific fields the legacy
   graph state tracks today (input_type, voice_audio, voice_duration_s,
   stt_text, trace_id) plus the cache fields the middleware writes.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "telegram_bot.agents.voice_agent"
MODULE_PATH = REPO_ROOT / "telegram_bot" / "agents" / "voice_agent.py"

FORBIDDEN_TOP_IMPORTS = {"aiogram", "fastapi", "qdrant_client"}
ALLOWED_LANGGRAPH_SUBPACKAGES = {"langgraph.runtime"}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_module_exposes_factory_and_state_schema() -> None:
    assert MODULE_PATH.is_file(), (
        f"{MODULE_PATH.relative_to(REPO_ROOT)} must exist (#2051 Slice 3)."
    )
    module = importlib.import_module(MODULE_NAME)
    for name in ("create_voice_agent", "VoiceAgentState"):
        assert hasattr(module, name), f"{MODULE_NAME} must export {name}."


def test_voice_agent_state_subclasses_AgentState() -> None:

    module = importlib.import_module(MODULE_NAME)
    schema = module.VoiceAgentState
    assert inspect.isclass(schema)
    # ``AgentState`` is a TypedDict; subclass relationship is not via issubclass
    # — instead check the inheritance chain via __orig_bases__.
    bases = getattr(schema, "__orig_bases__", ())
    base_names = {getattr(b, "__name__", "") for b in bases}
    assert "AgentState" in base_names, (
        f"VoiceAgentState must subclass AgentState (got bases: {base_names})"
    )


def test_voice_agent_state_has_voice_specific_fields() -> None:
    """Voice fields the legacy graph state carries today + cache fields
    the middleware stack writes."""
    module = importlib.import_module(MODULE_NAME)
    annotations = getattr(module.VoiceAgentState, "__annotations__", {})
    expected = {
        # voice-only inputs the handler will write before invoking the agent
        "voice_audio",
        "voice_duration_s",
        "stt_text",
        "input_type",
        "trace_id",
        # shared with text path / written by middleware
        "query_type",
        "cache_hit",
        "query_embedding",
    }
    missing = expected - set(annotations)
    assert not missing, (
        f"VoiceAgentState must annotate {sorted(expected)} fields. Missing: {sorted(missing)}"
    )


def test_create_voice_agent_signature_takes_cache_and_embeddings() -> None:
    module = importlib.import_module(MODULE_NAME)
    factory = module.create_voice_agent
    assert callable(factory)
    sig = inspect.signature(factory)
    params = sig.parameters
    for name in ("cache", "embeddings", "model"):
        assert name in params, f"create_voice_agent must accept '{name}' (kw-only)"
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_module_has_no_forbidden_top_imports() -> None:
    tree = _parse(MODULE_PATH)
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in FORBIDDEN_TOP_IMPORTS:
                    offenders.append(alias.name)
                if top == "langgraph" and alias.name not in ALLOWED_LANGGRAPH_SUBPACKAGES:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".", 1)[0]
            if top in FORBIDDEN_TOP_IMPORTS:
                offenders.append(module)
            if top == "langgraph" and module not in ALLOWED_LANGGRAPH_SUBPACKAGES:
                offenders.append(module)
    assert not offenders, (
        f"{MODULE_PATH.relative_to(REPO_ROOT)} forbidden module-scope imports: {offenders}."
    )
