"""Query pipeline handlers extracted from ``telegram_bot/bot.py``.

Split #2816: extracted ``handle_query``, ``_handle_apartment_fast_path``,
``_trace_guard_blocked``,
``_send_core_response``, ``_write_final_pipeline_trace``, ``_handle_query_supervisor``
as module-level functions.

#3208 convergence: the Telegram free-text path is reduced to gating
(handoff + guard), deterministic context assembly (role, filters), ONE
assistant-core call, and presentation. Classify/embed/semantic-cache work
lives in the core (``src.core.assistant`` → ``run_assistant_pipeline``);
this module no longer duplicates it.

#3216: the imperative agent facade and its recovery wrappers were removed;
queries route deterministically to assistant-core or product services.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram.utils.chat_action import ChatActionSender

from src.runtime.services.query_filter_signal import detect_filter_sensitive_query
from telegram_bot.pipeline.streaming import (
    _new_draft_id,
)
from telegram_bot.tracing_context import make_session_id


if TYPE_CHECKING:  # pragma: no cover
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)

# Maps Fluent locale code -> language label used in system prompt {{language}} variable.
# Moved here from the removed ``telegram_bot.agents`` facade (#3216).
LOCALE_TO_LANGUAGE: dict[str, str] = {
    "ru": "русском языке",
    "en": "English",
    "uk": "українською мовою",
}


def _get_detect_injection() -> Any:
    from telegram_bot import bot as _m

    return _m.detect_injection


async def handle_query(
    bot: PropertyBot,
    message: Message,
    locale: str = "ru",
    state: FSMContext | None = None,
    dialog_manager: Any = None,
) -> None:
    """Handle user query via supervisor graph (#310: supervisor-only)."""
    pipeline_start = time.perf_counter()
    assert message.bot is not None
    assert message.from_user is not None
    aiogram_bot = message.bot

    # Handoff mode check (#730): relay to topic or skip bot response.
    if bot._handoff_state is not None:
        handoff = await bot._handoff_state.get_by_client(message.from_user.id)
        if handoff and handoff.mode == "human":
            if bot._forum_bridge is not None:
                await bot._forum_bridge.relay_to_topic(
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                    topic_id=handoff.topic_id,
                )
            return
        if handoff and handoff.mode == "human_waiting" and bot._forum_bridge is not None:
            await bot._forum_bridge.relay_to_topic(
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                topic_id=handoff.topic_id,
            )

    await aiogram_bot.send_chat_action(chat_id=message.chat.id, action="typing")

    _raw_thread_id = message.message_thread_id
    forum_thread_id: int | None = _raw_thread_id if isinstance(_raw_thread_id, int) else None
    expert_id: str | None = None

    root_trace_metadata: dict[str, Any] = {}
    await _handle_query_supervisor(
        bot,
        message,
        pipeline_start,
        locale=locale,
        root_trace_metadata=root_trace_metadata,
        state=state,
        forum_thread_id=forum_thread_id,
        expert_id=expert_id,
        dialog_manager=dialog_manager,
    )


def _trace_guard_blocked(
    *,
    user_text: str,
    pipeline_start: float,
    risk_score: float,
    pattern: str | None,
    root_trace_metadata: dict[str, Any] | None,
) -> None:
    """Write trace metadata for a hard-blocked injection (#1368)."""
    wall_ms = (time.perf_counter() - pipeline_start) * 1000
    if root_trace_metadata is not None:
        root_trace_metadata.update(
            {
                "pipeline_mode": "sdk_agent",
                "pipeline_wall_ms": wall_ms,
                "e2e_latency_ms": wall_ms,
                "guard_blocked": True,
                "injection_pattern": pattern,
                "injection_risk_score": risk_score,
            }
        )


async def _send_core_response(
    bot: PropertyBot,
    *,
    message: Any,
    response_text: str,
    user_text: str,
    query_type: str,
    rag_result_store: dict[str, Any],
    ctx: Any,
    forum_thread_id: int | None,
) -> None:
    """Send response with feedback keyboard and source attribution."""
    trace_id = str(rag_result_store.get("request_id", "") or "")

    reply_markup = None
    if trace_id and query_type and query_type not in {"CHITCHAT", "OFF_TOPIC"}:
        from telegram_bot.feedback import build_feedback_keyboard

        reply_markup = build_feedback_keyboard(trace_id)
    if reply_markup is None and ctx.history_reply_markup is not None:
        reply_markup = ctx.history_reply_markup

    sources_html = ""
    documents = rag_result_store.get("documents", [])
    if bot._graph_config.show_sources and documents and query_type not in {"CHITCHAT", "OFF_TOPIC"}:
        from telegram_bot.services.generation.telegram_formatting import format_sources_html

        _MAX_SOURCES = 5
        sources_html = format_sources_html(documents, max_sources=_MAX_SOURCES)
        rag_result_store["sources_count"] = min(len(documents), _MAX_SOURCES)

    from telegram_bot.services.generation.telegram_formatting import (
        build_html_messages,
        send_html_messages,
    )

    html_messages = build_html_messages(response_text, sources_html=sources_html)

    if message.chat.type == "private":
        draft_state = rag_result_store.get("_draft_state")
        try:
            if draft_state is None and len(html_messages) == 1:
                draft_state = {
                    "chat_id": message.chat.id,
                    "thread_id": forum_thread_id,
                    "draft_id": _new_draft_id(),
                }
            if draft_state is not None and len(html_messages) == 1:
                send_kwargs: dict[str, Any] = {
                    "chat_id": draft_state["chat_id"],
                    "text": html_messages[0],
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup,
                }
                thread_id = draft_state.get("thread_id")
                if thread_id is not None:
                    send_kwargs["message_thread_id"] = thread_id
                await bot.bot.send_message(**send_kwargs)
            else:
                await send_html_messages(
                    message, response_text, sources_html=sources_html, reply_markup=reply_markup
                )
            ctx.response_sent = True
        except Exception:
            logger.warning(
                "Draft finalize via bot.send_message failed, falling back to send_html_messages"
            )
            try:
                await send_html_messages(
                    message, response_text, sources_html=sources_html, reply_markup=reply_markup
                )
                ctx.response_sent = True
            except Exception:
                logger.exception("Failed to send text response")
                if response_text:
                    await message.answer(response_text)
                ctx.response_sent = True
    else:
        await send_html_messages(
            message, response_text, sources_html=sources_html, reply_markup=reply_markup
        )
        if html_messages:
            ctx.response_sent = True


def _write_final_pipeline_trace(
    *,
    wall_ms: float,
    rag_result_store: dict[str, Any],
    root_trace_metadata: dict[str, Any] | None,
) -> None:
    """Write end-of-pipeline trace metadata from the core result (truthful)."""
    if root_trace_metadata is not None:
        root_trace_metadata.update(
            {
                "pipeline_mode": "assistant_core",
                "query_type": rag_result_store.get("query_type", ""),
                "grounding_mode": rag_result_store.get("grounding_mode") or "",
                "cache_hit": bool(rag_result_store.get("cache_hit", False)),
                "rerank_applied": bool(rag_result_store.get("rerank_applied", False)),
                "sources_count": int(rag_result_store.get("sources_count", 0) or 0),
                "grounded": rag_result_store.get("grounded"),
                "legal_answer_safe": rag_result_store.get("legal_answer_safe"),
                "semantic_cache_safe_reuse": rag_result_store.get("semantic_cache_safe_reuse"),
                "safe_fallback_used": bool(rag_result_store.get("safe_fallback_used", False)),
                "core_latency_ms": rag_result_store.get("core_latency_ms"),
                "pipeline_wall_ms": wall_ms,
                "e2e_latency_ms": wall_ms,
            }
        )


async def _supervisor_check_guard(
    bot: PropertyBot,
    message: Message,
    *,
    user_text: str,
    pipeline_start: float,
    root_trace_metadata: dict[str, Any] | None,
) -> str | None:
    """Run content-filter guard. Returns BLOCKED_RESPONSE string if hard-blocked, else None."""
    from src.runtime.services.rag_core import BLOCKED_RESPONSE

    detect_injection = _get_detect_injection()
    detected, risk_score, pattern = detect_injection(user_text)
    if not detected:
        return None
    if bot.config.guard_mode == "hard":
        logger.warning(
            "Pre-agent guard blocked (score=%.2f, pattern=%s): %.80s",
            risk_score,
            pattern,
            user_text,
        )
        await message.answer(BLOCKED_RESPONSE)
        _trace_guard_blocked(
            user_text=user_text,
            pipeline_start=pipeline_start,
            risk_score=risk_score,
            pattern=pattern,
            root_trace_metadata=root_trace_metadata,
        )
        return BLOCKED_RESPONSE
    logger.warning(
        "Pre-agent guard detected (mode=%s, score=%.2f, pattern=%s): %.80s",
        bot.config.guard_mode,
        risk_score,
        pattern,
        user_text,
    )
    return None


async def _extract_request_filters(
    bot: PropertyBot,
    *,
    user_text: str,
    rag_result_store: dict[str, Any],
) -> dict[str, Any]:
    """Deterministically extract retrieval filters for the core request (#3208).

    Filter extraction stays a transport-side context-assembly duty (the
    extractor is a Telegram service); propagation into retrieval, cache
    signature, and store signature is owned by the core.
    """
    filter_signal = detect_filter_sensitive_query(user_text)
    rag_result_store["filter_sensitive"] = filter_signal.is_filter_sensitive
    rag_result_store["filter_signal_reasons"] = list(filter_signal.reasons)
    if not filter_signal.is_filter_sensitive:
        return {}
    extracted_filters = await bot._extract_pre_agent_filters(user_text)
    if extracted_filters:
        rag_result_store["filters"] = extracted_filters
    return extracted_filters


async def _supervisor_run_core(
    bot: PropertyBot,
    message: Message,
    *,
    user_text: str,
    user_id: int,
    session_id: str,
    role: str,
    language: str,
    extracted_filters: dict[str, Any],
    rag_result_store: dict[str, Any],
    forum_thread_id: int | None,
) -> str:
    """Run the assistant core for the text query. Returns response_text."""
    assert message.bot is not None
    aiogram_bot = message.bot

    from src.core import CoreDependencies
    from telegram_bot.assistant_core_adapter import build_user_context, run_core_text_request

    user_context = build_user_context(
        user_id=user_id,
        session_id=session_id,
        role=role,
        filters=extracted_filters or None,
        language=language,
    )
    dependencies = CoreDependencies(
        cache=bot._cache,
        embeddings=bot._embeddings,
        sparse_embeddings=bot._sparse,
        qdrant=bot._qdrant,
        reranker=bot._reranker,
        llm=bot._llm,
        config=bot.config,
    )
    async with ChatActionSender.typing(bot=aiogram_bot, chat_id=message.chat.id):
        core_result = await run_core_text_request(
            query=user_text,
            collection=bot.config.qdrant_collection,
            user_context=user_context,
            dependencies=dependencies,
        )

    response_text = core_result.response_text
    # Truthful core metadata (#3208): no hardcoded grounded/safety flags.
    rag_result_store["query_type"] = core_result.request_type or ""
    rag_result_store["request_id"] = core_result.request_id
    rag_result_store["cache_hit"] = core_result.cache_hit
    rag_result_store["rerank_applied"] = core_result.rerank_applied
    rag_result_store["sources_count"] = core_result.documents_count
    rag_result_store["core_latency_ms"] = core_result.latency_ms
    rag_result_store["grounding_mode"] = core_result.grounding_mode
    rag_result_store["grounded"] = core_result.grounded
    rag_result_store["legal_answer_safe"] = core_result.legal_answer_safe
    rag_result_store["semantic_cache_safe_reuse"] = core_result.semantic_cache_safe_reuse
    rag_result_store["safe_fallback_used"] = core_result.safe_fallback_used
    rag_result_store["documents"] = [
        {"metadata": {"title": src.get("title", ""), "url": src.get("url", "")}, "score": 1.0}
        for src in core_result.retrieved_sources
    ]
    return response_text


def _supervisor_write_final_trace(
    *,
    pipeline_start: float,
    rag_result_store: dict[str, Any],
    root_trace_metadata: dict[str, Any] | None,
) -> None:
    """Write the final trace from the core result metadata (no cache store).

    Semantic-cache storage moved into the core (#3208); this is observability
    only.
    """
    wall_ms = (time.perf_counter() - pipeline_start) * 1000
    _write_final_pipeline_trace(
        wall_ms=wall_ms,
        rag_result_store=rag_result_store,
        root_trace_metadata=root_trace_metadata,
    )


async def _handle_query_supervisor(
    bot: PropertyBot,
    message: Message,
    pipeline_start: float,
    locale: str = "ru",
    root_trace_metadata: dict[str, Any] | None = None,
    state: FSMContext | None = None,
    forum_thread_id: int | None = None,
    expert_id: str | None = None,
    dialog_manager: Any = None,
) -> str:
    """Handle free-text Q&A by converging on the assistant core (#3208).

    Telegram keeps only: handoff gating (``handle_query``), the content-filter
    guard, deterministic context assembly (role, language, filters), ONE core
    call, and presentation. Classify/embed/semantic-cache work happens inside
    ``run_assistant_pipeline`` exactly once.
    """

    assert message.bot is not None
    assert message.from_user is not None
    user_id = message.from_user.id
    session_id = make_session_id("chat", message.chat.id)
    role = await bot._resolve_user_role(user_id)
    language = LOCALE_TO_LANGUAGE.get(locale, bot.config.domain_language)

    rag_result_store: dict[str, Any] = {}
    user_text = message.text or ""

    # Step 1: Content-filter guard (transport-side safety gate).
    if bot.config.content_filter_enabled:
        blocked = await _supervisor_check_guard(
            bot,
            message,
            user_text=user_text,
            pipeline_start=pipeline_start,
            root_trace_metadata=root_trace_metadata,
        )
        if blocked is not None:
            return blocked

    # Step 2: Deterministic context assembly (filter propagation into the core).
    extracted_filters = await _extract_request_filters(
        bot, user_text=user_text, rag_result_store=rag_result_store
    )

    # Step 3: ONE core call (classify → cache check → retrieve → generate → cache store).
    response_text = await _supervisor_run_core(
        bot,
        message,
        user_text=user_text,
        user_id=user_id,
        session_id=session_id,
        role=role,
        language=language,
        extracted_filters=extracted_filters,
        rag_result_store=rag_result_store,
        forum_thread_id=forum_thread_id,
    )

    # Step 4: Send exactly once.
    query_type = str(rag_result_store.get("query_type", "") or "")

    class _DummyCtx:
        response_sent = False
        history_reply_markup = None

    ctx: Any = _DummyCtx()
    if response_text and not ctx.response_sent:
        await _send_core_response(
            bot,
            message=message,
            response_text=response_text,
            user_text=user_text,
            query_type=query_type,
            rag_result_store=rag_result_store,
            ctx=ctx,
            forum_thread_id=forum_thread_id,
        )

    # Step 5: Final trace from truthful core metadata.
    _supervisor_write_final_trace(
        pipeline_start=pipeline_start,
        rag_result_store=rag_result_store,
        root_trace_metadata=root_trace_metadata,
    )

    return response_text
