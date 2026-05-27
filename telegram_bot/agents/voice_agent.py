"""Voice-flavoured ``create_agent`` factory.

Slice 3 of the voice-path migration to ``create_agent`` (ADR-0010,
parent #1535 / #2051). Builds a compiled agent that mirrors the legacy
voice graph topology (``transcribe`` → ``guard`` → ``classify`` →
``cache_check`` → ``rag_search`` → ``cache_store``) while staying
inside the SDK's ``before_agent`` / ``before_model`` / ``after_agent``
hook system.

Wiring
------

The factory layers three middleware in deterministic order:

1. :class:`~telegram_bot.graph.middleware.GuardMiddleware` —
   ``before_model`` injection guard. Already on ``dev`` (#2052).
2. :class:`~telegram_bot.graph.middleware.ClassifyMiddleware` —
   ``before_agent`` query classifier; short-circuits CHITCHAT /
   OFF_TOPIC with the legacy canned response.
3. :class:`~telegram_bot.graph.middleware.SemanticCacheMiddleware` —
   ``before_agent`` cache lookup + ``after_agent`` cache store. Skips
   the model loop entirely on a cache HIT.

Tools default to the existing ``rag_search`` (the same one the text
``create_bot_agent`` already wires); the factory accepts an explicit
``tools`` argument for tests / future extensions.

Pre-agent ``transcribe`` and post-agent ``respond`` stay outside the
factory — they live in ``handle_voice`` because they need aiogram /
Telegram-side concerns the agent itself does not know about. This
matches ADR-0010's split between the SDK middleware lifecycle and the
Telegram-side I/O.

Module imports stay narrow (no aiogram / fastapi / qdrant_client at
module scope) so the factory is unit testable in isolation.
"""

from __future__ import annotations

import logging
from typing import Any, NotRequired

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_openai import ChatOpenAI

from telegram_bot.agents.context import BotContext
from telegram_bot.agents.rag_tool import rag_search
from telegram_bot.graph.middleware.cache import SemanticCacheMiddleware
from telegram_bot.graph.middleware.classify import ClassifyMiddleware
from telegram_bot.graph.middleware.guard import GuardMiddleware


logger = logging.getLogger(__name__)


# Default voice-tuned system prompt. Kept inline (not via prompt registry) so
# the factory has no extra Redis dependency at construction time. Matches the
# tone of the legacy voice respond_node — short, conversational, source-aware.
_VOICE_SYSTEM_PROMPT = (
    "Ты голосовой ассистент по недвижимости. Отвечай кратко (60–100 слов), "
    "ясно и вслух — без эмодзи и Markdown. Если в контексте нет ответа, "
    "скажи об этом прямо одним предложением и предложи переформулировать "
    "вопрос. Цены — в евро. Расстояния — в метрах. Если вопрос за пределами "
    "недвижимости — вежливо откажись и предложи задать вопрос по теме."
)


class VoiceAgentState(AgentState):
    """Custom ``AgentState`` for the voice-path agent.

    All fields are :class:`typing_extensions.NotRequired` so old
    checkpoints still validate (per ADR-0010 §"Custom State Schema").
    The schema is the union of:

    * voice-only inputs the handler writes before invoking the agent
      (``voice_audio``, ``voice_duration_s``, ``stt_text``,
      ``input_type``, ``trace_id``);
    * cache fields the middleware stack writes
      (``query_type``, ``cache_hit``, ``cached_response``,
      ``query_embedding``, ``colbert_query``, ``embeddings_cache_hit``,
      ``embedding_error``, ``embedding_error_type``);
    * shared observability slots (``response``, ``sources_count``,
      ``show_sources``, ``latency_stages``).
    """

    # Voice-only inputs
    voice_audio: NotRequired[bytes]
    voice_duration_s: NotRequired[float]
    stt_text: NotRequired[str]
    stt_duration_ms: NotRequired[float]
    input_type: NotRequired[str]
    trace_id: NotRequired[str]

    # Classification + cache (aligned with _ClassifyAwareState / _CacheAwareState)
    query_type: NotRequired[str]
    cache_hit: NotRequired[bool]
    cached_response: NotRequired[str | None]
    query_embedding: NotRequired[list[float] | None]
    colbert_query: NotRequired[list[list[float]] | None]
    embeddings_cache_hit: NotRequired[bool]
    embedding_error: NotRequired[bool]
    embedding_error_type: NotRequired[str | None]

    # Shared observability + response surface
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


def create_voice_agent(
    *,
    cache: Any,
    embeddings: Any,
    model: str,
    tools: list[Any] | None = None,
    extra_middleware: list[AgentMiddleware] | None = None,
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
    """Compile a voice-flavoured ``create_agent`` instance.

    The factory wires the three voice middleware (guard, classify,
    cache) on top of a configurable tool set and returns the compiled
    agent ready for ``await agent.ainvoke({"messages": [...]}, config)``.

    Args:
        cache: Cache layer manager passed to ``SemanticCacheMiddleware``.
        embeddings: Embedder passed to ``SemanticCacheMiddleware``.
        model: LLM model name (e.g. ``"openai/gpt-oss-120b"``). Routed
            through LiteLLM proxy when ``base_url`` is supplied.
        tools: Override the default tool set. Defaults to
            ``[rag_search]``.
        extra_middleware: Additional middleware appended after the
            three voice ones. Useful for tests that want to attach a
            spy or for production callers that want a custom logger.
        checkpointer: Optional ``langgraph`` checkpointer (Redis or
            ``MemorySaver``). When ``None`` the agent runs stateless.
        system_prompt: Override the built-in voice prompt.
        base_url: OpenAI-compatible API base URL (e.g. LiteLLM proxy).
        api_key: API key for the LLM provider. Defaults to a sentinel
            so LiteLLM proxy works without a real OpenAI key.
        cache_scope: Cache namespace for the cache middleware.
        agent_role: Optional role tag for cache key isolation.
        guard_mode: ``"hard"`` / ``"soft"`` / ``"log"`` — forwarded to
            :class:`~telegram_bot.graph.middleware.GuardMiddleware`.
        skip_classify_canned_response: Pass-through to
            :class:`~telegram_bot.graph.middleware.ClassifyMiddleware`.
        max_tokens: Optional cap on completion tokens.

    Returns:
        Compiled agent graph ready for ``ainvoke`` / ``astream``.
    """
    model_kwargs: dict[str, Any] = {"model": model}
    if base_url:
        model_kwargs["base_url"] = base_url
    model_kwargs["api_key"] = api_key or "sk-not-needed"
    if max_tokens:
        model_kwargs["max_tokens"] = max_tokens
    llm = ChatOpenAI(**model_kwargs)

    middleware: list[AgentMiddleware] = [
        GuardMiddleware(guard_mode=guard_mode),
        ClassifyMiddleware(skip_canned_response=skip_classify_canned_response),
        SemanticCacheMiddleware(
            cache=cache,
            embeddings=embeddings,
            cache_scope=cache_scope,
            agent_role=agent_role,
        ),
    ]
    if extra_middleware:
        middleware.extend(extra_middleware)

    agent = create_agent(
        model=llm,
        tools=tools if tools is not None else _build_default_tools(),
        system_prompt=system_prompt or _VOICE_SYSTEM_PROMPT,
        state_schema=VoiceAgentState,
        context_schema=BotContext,
        checkpointer=checkpointer,
        middleware=middleware,
    )

    logger.info(
        "Created voice agent: model=%s base_url=%s tools=%d middleware=%d checkpointer=%s",
        model,
        base_url or "default",
        len(tools) if tools is not None else len(_build_default_tools()),
        len(middleware),
        type(checkpointer).__name__ if checkpointer is not None else "None",
    )
    return agent


__all__ = ("VoiceAgentState", "create_voice_agent")
