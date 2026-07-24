"""Query pipeline handlers extracted from ``telegram_bot/bot.py``.

Split #2816: extracted ``handle_query``, ``_handle_apartment_fast_path``,
``_handle_client_direct_pipeline``, ``_trace_guard_blocked``,
``_handle_pre_agent_cache_hit``, ``_send_core_response``,
``_write_final_pipeline_trace``, ``_handle_query_supervisor``,
``_astream_supervisor_with_recovery``, ``_ainvoke_supervisor_with_recovery``
as module-level functions.
"""

from __future__ import annotations

import contextlib
import inspect
import json
import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aiogram.utils.chat_action import ChatActionSender

from src.retrieval.topic_classifier import get_query_topic_hint
from src.runtime.grounding.policy import get_grounding_mode
from src.runtime.services.cache_policy import (
    SEMANTIC_CACHE_SCHEMA_VERSION,
    build_cacheability_decision,
    is_contextual_query,
    maybe_store_semantic_response,
    resolve_semantic_cache_signature,
)
from src.runtime.services.query_filter_signal import detect_filter_sensitive_query
from telegram_bot.handlers.error_classification import _is_checkpointer_runtime_error
from telegram_bot.observability.state_helpers import (
    _state_control_message_id,  # card_2a71ec058138: homed to observability/
)
from telegram_bot.pipeline.pre_agent import (
    _build_pre_agent_state_contract,
    _get_or_compute_pre_agent_dense,
    _prepare_pre_agent_retrieval_vectors,
)
from telegram_bot.pipeline.streaming import (
    _AGENT_DRAFT_INTERVAL,
    _extract_stream_chunk_text,
    _new_draft_id,
)
from telegram_bot.tracing_context import make_session_id


if TYPE_CHECKING:  # pragma: no cover
    from aiogram.fsm.context import FSMContext
    from aiogram.types import Message

    from telegram_bot.bot import PropertyBot


logger = logging.getLogger(__name__)

_NO_RAG_QUERY_TYPES: frozenset[str] = frozenset({"CHITCHAT", "OFF_TOPIC"})


def _get_classify_query() -> Any:
    from telegram_bot import bot as _m

    return _m.classify_query


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


async def _handle_apartment_fast_path(
    bot: PropertyBot,
    *,
    user_text: str,
    message: Message,
    state: FSMContext | None = None,
    dialog_manager: Any = None,
) -> str | None:
    """C+ fast path: regex filters -> hybrid search -> generate. No agent loop (#629)."""
    from telegram_bot.services.apartment.apartments_service import check_escalation

    result = await bot._apartment_pipeline.extract(user_text)

    if result.meta.confidence == "LOW":
        return None

    semantic_query = result.meta.semantic_remainder or user_text
    dense, sparse, colbert = await bot._embeddings.aembed_hybrid_with_colbert(semantic_query)
    await bot._cache.store_embedding(semantic_query, dense)
    await bot._cache.store_sparse_embedding(semantic_query, sparse)

    if bot._cache.redis is not None and message.from_user is not None:
        try:
            from telegram_bot.implicit_feedback import is_reformulation

            _uid = message.from_user.id
            _ikey = f"implicit_retry:{_uid}"
            _prev_raw = await bot._cache.redis.get(_ikey)
            if _prev_raw:
                _prev = json.loads(_prev_raw)
                _time_delta = time.time() - float(_prev["ts"])
                if is_reformulation(list(dense), _prev["vec"], _time_delta):
                    pass  # implicit retry detected (scoring removed in #2844)
            await bot._cache.redis.set(
                _ikey,
                json.dumps({"vec": list(dense), "ts": time.time()}),
                ex=60,
            )
        except Exception:
            logger.debug("Implicit retry check failed", exc_info=True)

    filters = result.hard.to_filters_dict()
    results, returned_count = await bot._apartments_service.search_with_filters(
        dense_vector=dense,
        colbert_query=colbert or None,
        sparse_vector=sparse,
        filters=filters or None,
        top_k=10,
    )

    score_spread = (results[0]["score"] - results[-1]["score"]) if len(results) > 1 else 0
    escalation = check_escalation(
        returned_count=returned_count,
        top_k=10,
        score_spread=score_spread,
        confidence=result.meta.confidence,
    )
    if escalation:
        return None

    from telegram_bot.services.apartment.apartment_formatter import format_apartment_text
    from telegram_bot.services.generation.generate_response import generate_response

    context = format_apartment_text(results)

    generated = await generate_response(
        query=user_text,
        documents=[],
        retrieved_context=[{"content": context, "source": "apartments_catalog"}],
        raw_messages=[{"role": "user", "content": user_text}],
        config=bot._graph_config,
        message=message,
    )

    response_text = str(generated.get("response", "") or context)
    if not generated.get("response_sent"):
        await bot._send_markdown_chunks(message, response_text)

    if state is not None and results:
        from telegram_bot.dialogs.catalog import activate_catalog_state, show_catalog_controls
        from telegram_bot.dialogs.states import CatalogSG
        from telegram_bot.services.apartment.catalog_rendering import send_catalog_results
        from telegram_bot.services.apartment.catalog_session import (
            build_catalog_runtime,
            clear_legacy_catalog_state,
        )

        runtime = build_catalog_runtime(
            query=user_text,
            source="free_text",
            filters=filters or {},
            view_mode="cards",
            results=results,
            total=len(results),
            next_offset=None,
        )
        state_data = await state.get_data()
        control_message_id = _state_control_message_id(state_data)
        if control_message_id is not None and message.bot is not None:
            with contextlib.suppress(Exception):
                await message.bot.delete_message(message.chat.id, control_message_id)
        cleaned_state = clear_legacy_catalog_state(state_data)
        cleaned_state["catalog_runtime"] = runtime

        maybe_set_data = getattr(state, "set_data", None)
        if inspect.iscoroutinefunction(maybe_set_data):
            await maybe_set_data(cleaned_state)
        await state.update_data(**cleaned_state)

        telegram_id = message.from_user.id if message.from_user else 0
        await send_catalog_results(
            message=message,
            property_bot=bot,
            results=results,
            total_count=len(results),
            view_mode=runtime.get("view_mode", "cards"),
            shown_start=1,
            telegram_id=telegram_id,
        )
        if dialog_manager is not None:
            dialog_manager.middleware_data.setdefault("state", state)
            await show_catalog_controls(
                message=message,
                dialog_manager=dialog_manager,
                runtime=runtime,
            )
            await activate_catalog_state(
                dialog_manager=dialog_manager,
                state=CatalogSG.results,
            )

    return response_text


async def _handle_client_direct_pipeline(
    bot: PropertyBot,
    *,
    message: Message,
    user_text: str,
    user_id: int,
    session_id: str,
    role: str,
    query_type: str,
    rag_result_store: dict[str, Any],
    state: FSMContext | None = None,
    dialog_manager: Any = None,
) -> str | None:
    """Delegate to run_client_pipeline. Returns None if needs_agent."""
    from telegram_bot.pipelines.client import infer_agent_intent, run_client_pipeline

    agent_intent = infer_agent_intent(user_text)
    if agent_intent == "apartment":
        apt_answer = await _handle_apartment_fast_path(
            bot,
            user_text=user_text,
            message=message,
            state=state,
            dialog_manager=dialog_manager,
        )
        if apt_answer is not None:
            return apt_answer
        return None

    result = await run_client_pipeline(
        user_text=user_text,
        user_id=user_id,
        session_id=session_id,
        message=message,
        cache=bot._cache,
        embeddings=bot._embeddings,
        sparse_embeddings=bot._sparse,
        qdrant=bot._qdrant,
        reranker=bot._reranker,
        llm=bot._llm,
        config=bot._graph_config,
        rag_result_store=rag_result_store,
        role=role,
        query_type=query_type,
        agent_intent=agent_intent,
    )
    if result.needs_agent:
        return None
    return result.answer  # type: ignore[no-any-return]


def _trace_guard_blocked(
    *,
    user_text: str,
    query_type: str,
    pipeline_start: float,
    risk_score: float,
    pattern: str | None,
    root_trace_metadata: dict[str, Any] | None,
) -> None:
    """Write scores for a hard-blocked injection (#1368) — tracing removed (#2844)."""
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


async def _handle_pre_agent_cache_hit(
    bot: PropertyBot,
    *,
    message: Any,
    cached: str,
    user_text: str,
    query_type: str,
    role: str,
    pipeline_start: float,
    pre_agent_start: float,
    rag_result_store: dict[str, Any],
    root_trace_metadata: dict[str, Any] | None,
    dense: list[float],
) -> str:
    """Send cached response and write trace for cache-hit path."""
    logger.info("Pre-agent cache HIT (type=%s): %.60s", query_type, user_text)
    rag_result_store["cache_hit"] = True
    rag_result_store["query_type"] = query_type
    rag_result_store["cache_key_embedding"] = dense
    pre_agent_ms = (time.perf_counter() - pre_agent_start) * 1000
    rag_result_store["pre_agent_ms"] = pre_agent_ms
    tid = uuid4().hex[:16]
    rag_result_store["request_id"] = tid
    reply_markup = None
    if tid and query_type not in _NO_RAG_QUERY_TYPES:
        from telegram_bot.feedback import build_feedback_keyboard

        reply_markup = build_feedback_keyboard(tid)
    await bot._send_markdown_chunks(message, str(cached), reply_markup=reply_markup)
    wall_ms = (time.perf_counter() - pipeline_start) * 1000
    cache_trace_metadata: dict[str, Any] = {
        "pipeline_mode": "pre_agent_cache",
        "pipeline_wall_ms": wall_ms,
        "pre_agent_ms": pre_agent_ms,
        "pre_agent_embed_ms": rag_result_store.get("pre_agent_embed_ms"),
        "pre_agent_cache_check_ms": rag_result_store.get("pre_agent_cache_check_ms"),
        "e2e_latency_ms": wall_ms,
        "topic_hint": rag_result_store.get("topic_hint", ""),
        "grounding_mode": rag_result_store.get("grounding_mode", ""),
        "filter_signature": rag_result_store.get("semantic_cache_filter_signature", ""),
        "grade_confidence": float(rag_result_store.get("grade_confidence", 0.0) or 0.0),
        "sources_count": int(rag_result_store.get("sources_count", 0) or 0),
        "grounded": bool(rag_result_store.get("grounded", True)),
        "legal_answer_safe": bool(rag_result_store.get("legal_answer_safe", True)),
        "semantic_cache_safe_reuse": bool(rag_result_store.get("semantic_cache_safe_reuse", True)),
        "safe_fallback_used": bool(rag_result_store.get("safe_fallback_used", False)),
    }
    if root_trace_metadata is not None:
        root_trace_metadata.update(cache_trace_metadata)
    return cached


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
    user_text: str,
    wall_ms: float,
    pre_agent_ms: float,
    filter_signature: str | None,
    rag_result_store: dict[str, Any],
    root_trace_metadata: dict[str, Any] | None,
) -> None:
    """Write end-of-pipeline span metadata and root trace metadata."""
    if root_trace_metadata is not None:
        root_trace_metadata.update(
            {
                "pipeline_mode": "sdk_agent",
                "query_type": rag_result_store.get("query_type", ""),
                "topic_hint": rag_result_store.get("topic_hint", ""),
                "grounding_mode": rag_result_store.get("grounding_mode", ""),
                "filter_signature": filter_signature or "",
                "grade_confidence": float(rag_result_store.get("grade_confidence", 0.0) or 0.0),
                "sources_count": int(rag_result_store.get("sources_count", 0) or 0),
                "grounded": bool(rag_result_store.get("grounded", True)),
                "legal_answer_safe": bool(rag_result_store.get("legal_answer_safe", True)),
                "semantic_cache_safe_reuse": bool(
                    rag_result_store.get("semantic_cache_safe_reuse", True)
                ),
                "safe_fallback_used": bool(rag_result_store.get("safe_fallback_used", False)),
                "pipeline_wall_ms": wall_ms,
                "pre_agent_ms": pre_agent_ms,
                "pre_agent_embed_ms": rag_result_store.get("pre_agent_embed_ms"),
                "pre_agent_cache_check_ms": rag_result_store.get("pre_agent_cache_check_ms"),
                "e2e_latency_ms": wall_ms,
            }
        )


async def _supervisor_check_guard(
    bot: PropertyBot,
    message: Message,
    *,
    user_text: str,
    query_type: str,
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
            query_type=query_type,
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


async def _supervisor_pre_agent_cache(
    bot: PropertyBot,
    message: Message,
    *,
    user_text: str,
    query_type: str,
    role: str,
    pipeline_start: float,
    pre_agent_start: float,
    rag_result_store: dict[str, Any],
    root_trace_metadata: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any], str | None]:
    """Run pre-agent embedding + cache check + vector prep.

    Returns (cached_response_or_None, extracted_filters, filter_signature).
    If cached_response_or_None is set, caller should return it immediately.
    Mutates rag_result_store in-place.
    """
    from src.runtime.services.rag_core import CACHEABLE_QUERY_TYPES

    extracted_filters: dict[str, Any] = {}
    filter_signature: str | None = None

    if query_type not in CACHEABLE_QUERY_TYPES:
        return None, extracted_filters, filter_signature

    try:
        dense = await _get_or_compute_pre_agent_dense(
            bot._cache, bot._embeddings, user_text, rag_result_store
        )
        if dense is None:
            raise RuntimeError("Pre-agent dense embedding unavailable")

        topic_hint_label = get_query_topic_hint(user_text)
        topic_hint = topic_hint_label.value if topic_hint_label is not None else None
        grounding_mode = get_grounding_mode(query_type=query_type, topic_hint=topic_hint)
        filter_signal = detect_filter_sensitive_query(user_text)
        contextual_query = is_contextual_query(user_text)
        rag_result_store["filter_sensitive"] = filter_signal.is_filter_sensitive
        rag_result_store["filter_signal_reasons"] = list(filter_signal.reasons)
        rag_result_store["contextual_query"] = contextual_query
        rag_result_store["topic_hint"] = topic_hint or ""
        rag_result_store["grounding_mode"] = grounding_mode
        if grounding_mode == "strict":
            rag_result_store.setdefault("grounded", True)
            rag_result_store.setdefault("legal_answer_safe", True)
            rag_result_store.setdefault("semantic_cache_safe_reuse", True)
            rag_result_store.setdefault("safe_fallback_used", False)

        if filter_signal.is_filter_sensitive:
            extracted_filters = await bot._extract_pre_agent_filters(user_text)
            if extracted_filters:
                rag_result_store["filters"] = extracted_filters
                filter_signature = resolve_semantic_cache_signature(filters=extracted_filters)
                rag_result_store["semantic_cache_filter_signature"] = filter_signature

        skip_cache = contextual_query or (
            filter_signal.is_filter_sensitive and filter_signature is None
        )
        cached = None
        if skip_cache:
            rag_result_store["semantic_cache_already_checked"] = True
        else:
            check_start = time.perf_counter()
            cached = await bot._cache.check_semantic(
                query=user_text,
                vector=dense,
                query_type=query_type,
                cache_scope="rag",
                agent_role=role,
                grounding_mode=grounding_mode if grounding_mode == "strict" else None,
                require_safe_reuse=grounding_mode == "strict",
                filter_signature=filter_signature,
            )
            rag_result_store["pre_agent_cache_check_ms"] = (
                time.perf_counter() - check_start
            ) * 1000
            rag_result_store["semantic_cache_already_checked"] = True

        if cached:
            hit_response = await _handle_pre_agent_cache_hit(
                bot,
                message=message,
                cached=cached,
                user_text=user_text,
                query_type=query_type,
                role=role,
                pipeline_start=pipeline_start,
                pre_agent_start=pre_agent_start,
                rag_result_store=rag_result_store,
                root_trace_metadata=root_trace_metadata,
                dense=dense,
            )
            return hit_response, extracted_filters, filter_signature

        logger.debug("Pre-agent cache MISS (type=%s): %.60s", query_type, user_text)
        rag_result_store["query_type"] = query_type
        await _prepare_pre_agent_retrieval_vectors(
            bot._cache, bot._embeddings, user_text, dense, rag_result_store
        )
        grounding_mode_value = rag_result_store.get("grounding_mode", "normal")
        topic_hint_obj = get_query_topic_hint(user_text)
        rag_result_store["state_contract"] = _build_pre_agent_state_contract(
            rag_result_store=rag_result_store,
            query_type=query_type,
            topic_hint=topic_hint_obj.value if topic_hint_obj is not None else None,
            dense_vector=dense,
            sparse_vector=rag_result_store.get("cache_key_sparse")
            if isinstance(rag_result_store.get("cache_key_sparse"), dict)
            else None,
            colbert_query=rag_result_store.get("cache_key_colbert"),
            grounding_mode=grounding_mode_value,
            filters=extracted_filters or None,
        )
    except Exception:
        logger.warning("Pre-agent cache check failed, proceeding to agent", exc_info=True)

    return None, extracted_filters, filter_signature


async def _supervisor_run_core(
    bot: PropertyBot,
    message: Message,
    *,
    user_text: str,
    user_id: int,
    session_id: str,
    role: str,
    query_type: str,
    language: str,
    extracted_filters: dict[str, Any],
    rag_result_store: dict[str, Any],
    state: FSMContext | None,
    dialog_manager: Any,
    forum_thread_id: int | None,
) -> str:
    """Run client-direct pipeline (if enabled) or assistant core. Returns response_text."""
    assert message.bot is not None
    aiogram_bot = message.bot

    if role == "client" and bot.config.client_direct_pipeline_enabled:
        try:
            async with ChatActionSender.typing(bot=aiogram_bot, chat_id=message.chat.id):
                rag_result_store["pre_agent_ms"] = rag_result_store.get("pre_agent_ms", 0.0)
                pipeline_answer = await _handle_client_direct_pipeline(
                    bot,
                    message=message,
                    user_text=user_text,
                    user_id=user_id,
                    session_id=session_id,
                    role=role,
                    query_type=query_type,
                    rag_result_store=rag_result_store,
                    state=state,
                    dialog_manager=dialog_manager,
                )
                if pipeline_answer is not None:
                    return pipeline_answer
        except Exception:
            logger.exception("Client direct pipeline failed; falling back to sdk_agent")

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
    rag_result_store["query_type"] = core_result.request_type or query_type
    rag_result_store["request_id"] = core_result.request_id
    rag_result_store["cache_hit"] = core_result.cache_hit
    rag_result_store["rerank_applied"] = core_result.rerank_applied
    rag_result_store["sources_count"] = core_result.documents_count
    rag_result_store["grade_confidence"] = 1.0 if core_result.documents_count > 0 else 0.0
    rag_result_store["grounded"] = True
    rag_result_store["legal_answer_safe"] = True
    rag_result_store["semantic_cache_safe_reuse"] = True
    rag_result_store["documents"] = [
        {"metadata": {"title": src.get("title", ""), "url": src.get("url", "")}, "score": 1.0}
        for src in core_result.retrieved_sources
    ]
    return response_text


async def _supervisor_store_cache_and_trace(
    bot: PropertyBot,
    message: Message,
    *,
    user_text: str,
    response_text: str,
    query_type: str,
    role: str,
    pipeline_start: float,
    pre_agent_ms: float,
    rag_result_store: dict[str, Any],
    root_trace_metadata: dict[str, Any] | None,
    user_id: int,
    session_id: str,
    messages: list[Any],
) -> None:
    """Cache store, final trace write, scores, and background history save."""
    from src.runtime.services.rag_core import CACHEABLE_QUERY_TYPES

    # Resolve filter_signature from stored state
    result_filters = rag_result_store.get("filters")
    if not isinstance(result_filters, dict) or not result_filters:
        state_contract = rag_result_store.get("state_contract")
        if isinstance(state_contract, dict):
            contract_filters = state_contract.get("filters")
            if isinstance(contract_filters, dict) and contract_filters:
                result_filters = contract_filters
    filter_signature = resolve_semantic_cache_signature(filters=result_filters)

    if bot._cache and response_text:
        _q = str(rag_result_store.get("query_type", "") or "")
        _gm = str(rag_result_store.get("grounding_mode", "normal") or "normal")
        raw_threshold = getattr(bot.config, "relevance_threshold_rrf", 0.005)
        confidence_threshold = (
            float(raw_threshold) if isinstance(raw_threshold, int | float) else 0.005
        )
        decision = build_cacheability_decision(
            result={**rag_result_store, "response": response_text},
            query_type=_q,
            grounding_mode=_gm,
            documents=rag_result_store.get("documents", []),
            cache_hit=bool(rag_result_store.get("cache_hit", False)),
            contextual=is_contextual_query(user_text),
            grade_confidence=float(rag_result_store.get("grade_confidence", 0.0) or 0.0),
            confidence_threshold=confidence_threshold,
            schema_version=SEMANTIC_CACHE_SCHEMA_VERSION,
        )
        rag_result_store["response_state"] = decision.response_state
        rag_result_store["degraded_reason"] = decision.degraded_reason
        rag_result_store["cache_eligible"] = decision.cache_eligible
        rag_result_store["store_reason"] = decision.store_reason
        store_vector = rag_result_store.get("cache_key_embedding") or rag_result_store.get(
            "query_embedding"
        )
        if _q in CACHEABLE_QUERY_TYPES and isinstance(store_vector, list) and bool(store_vector):
            try:
                await maybe_store_semantic_response(
                    cache=bot._cache,
                    query=message.text or "",
                    response=response_text,
                    vector=store_vector,
                    query_type=_q,
                    cache_scope="rag",
                    decision=decision,
                    agent_role=role,
                    filter_signature=filter_signature,
                )
            except Exception:
                logger.warning("Failed to store semantic cache in text path", exc_info=True)

    wall_ms = (time.perf_counter() - pipeline_start) * 1000
    _write_final_pipeline_trace(
        user_text=user_text,
        wall_ms=wall_ms,
        pre_agent_ms=pre_agent_ms,
        filter_signature=filter_signature,
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
    """Handle query via imperative adapter SDK (#413 — replaces build_supervisor_graph).

    Decomposed into helpers (#2927): _supervisor_check_guard,
    _supervisor_pre_agent_cache, _supervisor_run_core,
    _supervisor_store_cache_and_trace.
    """
    from telegram_bot.agents.agent import LOCALE_TO_LANGUAGE

    classify_query = _get_classify_query()

    assert message.bot is not None
    assert message.from_user is not None
    user_id = message.from_user.id
    session_id = make_session_id("chat", message.chat.id)
    role = await bot._resolve_user_role(user_id)
    language = LOCALE_TO_LANGUAGE.get(locale, bot.config.domain_language)

    rag_result_store: dict[str, Any] = {}
    pre_agent_start = time.perf_counter()

    user_text = message.text or ""
    query_type = classify_query(user_text)

    # Step 1: Content-filter guard
    if bot.config.content_filter_enabled:
        blocked = await _supervisor_check_guard(
            bot,
            message,
            user_text=user_text,
            query_type=query_type,
            pipeline_start=pipeline_start,
            root_trace_metadata=root_trace_metadata,
        )
        if blocked is not None:
            return blocked

    # Step 2: Pre-agent cache check + vector prep
    cached_response, extracted_filters, _filter_sig = await _supervisor_pre_agent_cache(
        bot,
        message,
        user_text=user_text,
        query_type=query_type,
        role=role,
        pipeline_start=pipeline_start,
        pre_agent_start=pre_agent_start,
        rag_result_store=rag_result_store,
        root_trace_metadata=root_trace_metadata,
    )
    if cached_response is not None:
        return cached_response

    rag_result_store.setdefault("pre_agent_ms", (time.perf_counter() - pre_agent_start) * 1000)

    # Step 3: Execute core request (client-direct or assistant core)
    response_text = await _supervisor_run_core(
        bot,
        message,
        user_text=user_text,
        user_id=user_id,
        session_id=session_id,
        role=role,
        query_type=query_type,
        language=language,
        extracted_filters=extracted_filters,
        rag_result_store=rag_result_store,
        state=state,
        dialog_manager=dialog_manager,
        forum_thread_id=forum_thread_id,
    )

    # Step 4: Token usage from last AI message (legacy messages list is empty in core path)
    messages: list[Any] = []

    # Step 5: Send response
    query_type = rag_result_store.get("query_type", query_type)  # type: ignore[assignment]

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

    # Step 6: Cache store + trace + scores + history
    pre_agent_ms = float(rag_result_store.get("pre_agent_ms", 0.0) or 0.0)
    await _supervisor_store_cache_and_trace(
        bot,
        message,
        user_text=user_text,
        response_text=response_text,
        query_type=query_type,
        role=role,
        pipeline_start=pipeline_start,
        pre_agent_ms=pre_agent_ms,
        rag_result_store=rag_result_store,
        root_trace_metadata=root_trace_metadata,
        user_id=user_id,
        session_id=session_id,
        messages=messages,
    )

    return response_text


async def _astream_supervisor_with_recovery(
    bot: PropertyBot,
    *,
    agent: Any,
    tools: list[Any],
    role: str,
    user_text: str,
    chat_id: int,
    callbacks: list[Any],
    bot_context: Any,
    rag_result_store: dict[str, Any],
    forum_thread_id: int | None = None,
    use_streaming: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Stream supervisor agent output and retry once on checkpointer runtime errors."""
    from telegram_bot.services.util.checkpointer_utils import _supervisor_thread_id

    payload = {"messages": [{"role": "user", "content": user_text}]}
    config = {
        "callbacks": callbacks,
        "configurable": {
            "thread_id": _supervisor_thread_id(chat_id, forum_thread_id),
            "bot_context": bot_context,
            "rag_result_store": rag_result_store,
            "role": role,
            "user_id": bot_context.telegram_user_id,
            "session_id": bot_context.session_id,
        },
    }

    async def _run_once(current_agent: Any) -> tuple[str, dict[str, Any]]:
        can_stream = use_streaming and callable(getattr(current_agent, "astream", None))
        if not can_stream:
            result: dict[str, Any] = await current_agent.ainvoke(payload, config=config)
            messages = result.get("messages", [])
            response_text = ""
            if messages:
                last_msg = messages[-1]
                response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
            return response_text, result

        draft_state: dict[str, Any] = {
            "chat_id": chat_id,
            "thread_id": forum_thread_id,
            "draft_id": _new_draft_id(),
        }

        accumulated = ""
        stream_messages: list[Any] = []
        latest_state: dict[str, Any] | None = None
        last_draft_at = 0.0
        stream = current_agent.astream(
            payload,
            config=config,
            stream_mode=["messages", "values"],
            version="v2",
        )
        async for part in stream:
            if isinstance(part, dict) and "type" in part:
                part_type = part.get("type")
                part_data = part.get("data")
                if part_type == "values":
                    if isinstance(part_data, dict):
                        latest_state = part_data
                    continue
                if part_type != "messages" or not isinstance(part_data, tuple):
                    continue
                message_chunk, metadata = part_data
            else:
                message_chunk, metadata = part
            if isinstance(metadata, dict):
                langgraph_node = metadata.get("langgraph_node")
                if isinstance(langgraph_node, str) and langgraph_node != "model":
                    continue

            text = _extract_stream_chunk_text(message_chunk)
            if not text:
                continue
            accumulated += text
            stream_messages.append(message_chunk)
            now = time.monotonic()
            if now - last_draft_at < _AGENT_DRAFT_INTERVAL:
                continue
            with contextlib.suppress(Exception):
                draft_kwargs: dict[str, Any] = {
                    "chat_id": draft_state["chat_id"],
                    "draft_id": draft_state["draft_id"],
                    "text": accumulated,
                }
                if draft_state["thread_id"] is not None:
                    draft_kwargs["message_thread_id"] = draft_state["thread_id"]
                await bot.bot.send_message_draft(**draft_kwargs)
            last_draft_at = now

        if accumulated:
            rag_result_store["_draft_state"] = draft_state

        return accumulated, latest_state or {"messages": stream_messages}

    from telegram_bot.bot import create_bot_agent

    try:
        return await _run_once(agent)
    except Exception as exc:
        if not _is_checkpointer_runtime_error(exc):
            raise
        if role in {"manager", "admin"}:
            logger.exception(
                "Supervisor stream failed with checkpointer runtime error; "
                "skip retry for role=%s to avoid duplicate side effects",
                role,
            )
            raise
        logger.exception(
            "Supervisor stream failed due to checkpointer runtime error; "
            "retrying once with MemorySaver"
        )

    from telegram_bot.integrations.memory import create_fallback_checkpointer

    bot._agent_checkpointer = create_fallback_checkpointer()
    fallback_agent = create_bot_agent(
        model=bot.config.supervisor_model,
        tools=tools,
        checkpointer=bot._agent_checkpointer,
        language=bot.config.domain_language,
        base_url=bot.config.llm_base_url,
        api_key=bot.config.llm_api_key,
        max_tokens=bot.config.supervisor_max_tokens,
    )
    return await _run_once(fallback_agent)


async def _ainvoke_supervisor_with_recovery(
    bot: PropertyBot,
    *,
    agent: Any,
    tools: list[Any],
    role: str,
    user_text: str,
    chat_id: int,
    callbacks: list[Any],
    bot_context: Any,
    rag_result_store: dict[str, Any],
    forum_thread_id: int | None = None,
    message: Any | None = None,
) -> dict[str, Any]:
    """Invoke supervisor agent and retry once with MemorySaver on checkpointer failures."""
    from telegram_bot.bot import create_bot_agent
    from telegram_bot.pipeline.streaming import _stream_agent_to_draft
    from telegram_bot.services.util.checkpointer_utils import _supervisor_thread_id

    payload = {"messages": [{"role": "user", "content": user_text}]}
    config = {
        "callbacks": callbacks,
        "configurable": {
            "thread_id": _supervisor_thread_id(chat_id, forum_thread_id),
            "bot_context": bot_context,
            "rag_result_store": rag_result_store,
            "role": role,
            "user_id": bot_context.telegram_user_id,
            "session_id": bot_context.session_id,
        },
    }

    streaming_enabled = bool(getattr(bot._graph_config, "streaming_enabled", False))
    if message is not None and streaming_enabled:
        aiogram_bot = getattr(message, "bot", None)
        if aiogram_bot is not None:
            try:
                return await _stream_agent_to_draft(
                    agent=agent,
                    payload=payload,
                    config=config,
                    bot=aiogram_bot,
                    chat_id=chat_id,
                    thread_id=forum_thread_id,
                )
            except Exception:
                logger.warning("Agent streaming failed; falling back to ainvoke", exc_info=True)

    try:
        result: dict[str, Any] = await agent.ainvoke(payload, config=config)
        return result
    except Exception as exc:
        if not _is_checkpointer_runtime_error(exc):
            raise
        if role in {"manager", "admin"}:
            logger.exception(
                "Supervisor ainvoke failed with checkpointer runtime error; "
                "skip retry for role=%s to avoid duplicate side effects",
                role,
            )
            raise
        logger.exception(
            "Supervisor ainvoke failed due to checkpointer runtime error; "
            "retrying once with MemorySaver"
        )

    from telegram_bot.integrations.memory import create_fallback_checkpointer

    bot._agent_checkpointer = create_fallback_checkpointer()
    fallback_agent = create_bot_agent(
        model=bot.config.supervisor_model,
        tools=tools,
        checkpointer=bot._agent_checkpointer,
        language=bot.config.domain_language,
        base_url=bot.config.llm_base_url,
        api_key=bot.config.llm_api_key,
        max_tokens=bot.config.supervisor_max_tokens,
    )
    fallback_result: dict[str, Any] = await fallback_agent.ainvoke(payload, config=config)
    return fallback_result
