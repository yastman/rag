"""Voice agent facade backed by the imperative assistant core.

The voice path no longer constructs a LangChain ``create_agent`` graph.  The
factory remains as a compatibility surface for tests/callers that expect an
object with ``ainvoke``/``astream``, but orchestration is delegated to the
procedural core/tool path.
"""

from __future__ import annotations

import logging
from typing import Any, NotRequired, TypedDict

from telegram_bot.agents.agent import AgentMessage, ImperativeBotAgent
from telegram_bot.agents.rag_tool import rag_search


logger = logging.getLogger(__name__)

_VOICE_SYSTEM_PROMPT = (
    "Ты голосовой ассистент по недвижимости. Отвечай кратко (60–100 слов), "
    "ясно и вслух — без эмодзи и Markdown. Если в контексте нет ответа, "
    "скажи об этом прямо одним предложением и предложи переформулировать "
    "вопрос. Цены — в евро. Расстояния — в метрах. Если вопрос за пределами "
    "недвижимости — вежливо откажись и предложи задать вопрос по теме."
)


class VoiceAgentState(TypedDict, total=False):
    """Typed state surface retained for voice-path compatibility."""

    voice_audio: NotRequired[bytes]
    voice_duration_s: NotRequired[float]
    stt_text: NotRequired[str]
    stt_duration_ms: NotRequired[float]
    input_type: NotRequired[str]
    trace_id: NotRequired[str]
    query_type: NotRequired[str]
    cache_hit: NotRequired[bool]
    cached_response: NotRequired[str | None]
    query_embedding: NotRequired[list[float] | None]
    colbert_query: NotRequired[list[list[float]] | None]
    embeddings_cache_hit: NotRequired[bool]
    embedding_error: NotRequired[bool]
    embedding_error_type: NotRequired[str | None]
    response: NotRequired[str]
    response_state: NotRequired[str]
    degraded_reason: NotRequired[str | None]
    cache_eligible: NotRequired[bool]
    store_reason: NotRequired[str]
    sources_count: NotRequired[int]
    show_sources: NotRequired[bool]
    grounding_mode: NotRequired[str]
    grade_confidence: NotRequired[float]
    documents: NotRequired[list[Any]]
    latency_stages: NotRequired[dict[str, float]]
    filters: NotRequired[dict[str, Any]]
    semantic_cache_filter_signature: NotRequired[str | None]
    search_results_count: NotRequired[int]


def _build_default_tools() -> list[Any]:
    """Default tool set for the voice agent — currently the shared ``rag_search``."""
    return [rag_search]


def _voice_payload_to_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if isinstance(payload.get("stt_text"), str):
            return str(payload["stt_text"])
        messages = payload.get("messages") or []
        if messages:
            last = messages[-1]
            if isinstance(last, dict):
                return str(last.get("content", ""))
            return str(getattr(last, "content", last))
    return ""


class ImperativeVoiceAgent(ImperativeBotAgent):
    """Voice-flavoured facade with the same async call shape as the old agent."""

    async def ainvoke(self, payload: Any, config: Any | None = None) -> dict[str, Any]:
        text = _voice_payload_to_text(payload)
        response = await self._run_core_or_tool(text, config if isinstance(config, dict) else {})
        return {"messages": [AgentMessage(response)], "response": response}


def create_voice_agent(
    *,
    cache: Any,
    embeddings: Any,
    model: str,
    tools: list[Any] | None = None,
    extra_middleware: list[Any] | None = None,
    checkpointer: Any | None = None,
    system_prompt: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    cache_scope: str = "rag",
    agent_role: str | None = None,
    guard_mode: str = "hard",
    skip_classify_canned_response: bool = False,
    max_tokens: int | None = None,
) -> Any:
    """Create a voice agent facade without LangChain/LangGraph dependencies."""

    _ = (
        cache,
        embeddings,
        extra_middleware,
        checkpointer,
        base_url,
        api_key,
        cache_scope,
        agent_role,
        guard_mode,
        skip_classify_canned_response,
        max_tokens,
    )
    agent = ImperativeVoiceAgent(
        tools=tools if tools is not None else _build_default_tools(),
        prompt=system_prompt or _VOICE_SYSTEM_PROMPT,
        model=model,
        role=agent_role or "client",
    )
    logger.info("Created imperative voice agent: model=%s tools=%d", model, len(agent.tools))
    return agent


__all__ = ("ImperativeVoiceAgent", "VoiceAgentState", "create_voice_agent")
