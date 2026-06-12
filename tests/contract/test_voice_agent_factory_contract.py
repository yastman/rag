"""Contract for the imperative voice-agent compatibility factory."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_NAME = "telegram_bot.agents.voice_agent"
MODULE_PATH = REPO_ROOT / "telegram_bot" / "agents" / "voice_agent.py"

FORBIDDEN_TOP_IMPORTS = {
    "aiogram",
    "fastapi",
    "qdrant_client",
    "langchain",
    "langchain_core",
    "langchain_openai",
    "langgraph",
    "langmem",
}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_module_exposes_factory_and_state_schema() -> None:
    assert MODULE_PATH.is_file()
    module = importlib.import_module(MODULE_NAME)
    for name in ("create_voice_agent", "VoiceAgentState"):
        assert hasattr(module, name), f"{MODULE_NAME} must export {name}."


def test_voice_agent_state_is_typed_schema() -> None:
    module = importlib.import_module(MODULE_NAME)
    schema = module.VoiceAgentState
    assert inspect.isclass(schema)
    assert hasattr(schema, "__annotations__")


def test_voice_agent_state_has_voice_specific_fields() -> None:
    module = importlib.import_module(MODULE_NAME)
    annotations = getattr(module.VoiceAgentState, "__annotations__", {})
    expected = {
        "voice_audio",
        "voice_duration_s",
        "stt_text",
        "input_type",
        "trace_id",
        "query_type",
        "cache_hit",
        "query_embedding",
    }
    missing = expected - set(annotations)
    assert not missing, f"VoiceAgentState missing fields: {sorted(missing)}"


def test_create_voice_agent_signature_takes_cache_and_embeddings() -> None:
    module = importlib.import_module(MODULE_NAME)
    factory = module.create_voice_agent
    sig = inspect.signature(factory)
    params = sig.parameters
    for name in ("cache", "embeddings", "model"):
        assert name in params, f"create_voice_agent must accept '{name}' (kw-only)"
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_voice_agent_module_has_no_forbidden_top_imports() -> None:
    tree = _parse(MODULE_PATH)
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in FORBIDDEN_TOP_IMPORTS:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".", 1)[0]
            if top in FORBIDDEN_TOP_IMPORTS:
                offenders.append(module)
    assert not offenders, f"Forbidden module-scope imports: {offenders}."
