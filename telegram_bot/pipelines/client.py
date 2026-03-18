"""Deterministic client pipeline — fast-path for text queries.

Steps: classify → agent intent gate → RAG → generate → send → post-process.
"""

from __future__ import annotations

import logging
import re
import time
from numbers import Real
from typing import Any

from src.retrieval.topic_classifier import get_query_topic_hint
from telegram_bot.agents.rag_pipeline import rag_pipeline
from telegram_bot.graph.nodes.respond import _MAX_SOURCES, format_sources
from telegram_bot.observability import get_client, observe
from telegram_bot.pipelines.state_contract import coerce_pre_agent_state_contract
from telegram_bot.scoring import score, write_langfuse_scores
from telegram_bot.services.generate_response import generate_response
from telegram_bot.services.grounding_policy import get_grounding_mode
from telegram_bot.services.history_service import HistoryService
from telegram_bot.services.types import PipelineResult


logger = logging.getLogger(__name__)

# Query types that bypass RAG — return canned response immediately.
_NO_RAG_QUERY_TYPES: frozenset[str] = frozenset({"CHITCHAT", "OFF_TOPIC"})

# Cache store allowlist mirrors graph semantic cache policy.
_PIPELINE_STORE_TYPES: frozenset[str] = frozenset({"FAQ", "GENERAL", "ENTITY", "STRUCTURED"})

_TELEGRAM_MESSAGE_LIMIT = 4096

# Contextual follow-up indicators — queries referencing prior turns are not cacheable.
_CONTEXTUAL_RE = re.compile(
    r"\b(подробнее|первый|первую|первое|второй|вторую|второе|третий|третью|третье"
    r"|это|тот|та|те|они|ещё|другие|другой|другую|следующий|следующую|предыдущий|предыдущую"
    r"|оба|обе|тот же|та же|то же)\b",
    re.IGNORECASE,
)

# Fallback confidence threshold for semantic cache store guard.
_CONFIDENCE_THRESHOLD = 0.005


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------


@observe(name="detect-agent-intent", capture_input=False, capture_output=False)
def detect_agent_intent(user_text: str) -> str:
    """Detect if the user intent requires agent routing.

    Args:
        user_text: Raw user message.

    Returns:
        Intent string: "mortgage" | "handoff" | "daily_summary" | "apartment" | "".
    """
    text = user_text.lower()
    lf = get_client()
    lf.update_current_span(input={"query_length": len(user_text)})
    if any(kw in text for kw in ("ипотек", "кредит", "рассрочк")):
        intent = "mortgage"
    elif any(kw in text for kw in ("менеджер", "позвон", "связаться")):
        intent = "handoff"
    elif any(kw in text for kw in ("сводк", "отчёт", "итог дня", "итоги дня")):
        intent = "daily_summary"
    elif any(
        kw in text
        for kw in (
            "апартамент",
            "двушк",
            "трёшк",
            "трешк",
            "трёхкомнат",
            "трехкомнат",
            "студи",
            "подобрать",
            "подбор",
        )
    ):
        intent = "apartment"
    else:
        intent = ""
    lf.update_current_span(output={"intent": intent or "none"})
    return intent


# ---------------------------------------------------------------------------
# Canned responses for non-RAG query types
# ---------------------------------------------------------------------------


def _build_non_rag_response(query_type: str) -> str:
    """Return canned response for CHITCHAT/OFF_TOPIC query types."""
    if query_type == "CHITCHAT":
        return "Привет! Я помогу с вопросами по недвижимости: цены, районы, покупка, документы."
    if query_type == "OFF_TOPIC":
        return (
            "Я отвечаю по теме недвижимости и связанных услуг. "
            "Сформулируйте вопрос по объектам, ценам, районам или процессу покупки."
        )
    return ""


def _safe_collection_name(config: Any) -> str:
    getter = getattr(config, "get_collection_name", None)
    if not callable(getter):
        return ""
    try:
        value = getter()
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _safe_langfuse_env(config: Any) -> str:
    value = getattr(config, "langfuse_env", "")
    return value if isinstance(value, str) else ""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _is_contextual_query(user_text: str) -> bool:
    """Return True if query contains follow-up pronouns / contextual references."""
    return bool(_CONTEXTUAL_RE.search(user_text))


# ---------------------------------------------------------------------------
# Telegram send helpers
# ---------------------------------------------------------------------------


def _split_telegram_response(text: str, limit: int = _TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into Telegram-safe chunks."""
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


async def _send_markdown_chunks(
    message: Any,
    text: str,
    *,
    reply_markup: Any | None = None,
) -> None:
    """Send response in chunks with Markdown parse_mode fallback."""
    chunks = _split_telegram_response(text)
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        markup = reply_markup if is_last else None
        try:
            await message.answer(chunk, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            logger.warning("Markdown parse failed in client pipeline, falling back")
            try:
                await message.answer(chunk, reply_markup=markup)
            except Exception:
                logger.exception("Failed to send response chunk in client pipeline")
                await message.answer(chunk)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


@observe(name="client-direct-pipeline", capture_input=False, capture_output=False)
async def run_client_pipeline(
    *,
    user_text: str,
    user_id: int,
    session_id: str,
    message: Any,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None,
    llm: Any | None,
    config: Any,
    history_service: HistoryService | None = None,
    rag_result_store: dict[str, Any] | None = None,
    role: str = "client",
    query_type: str = "GENERAL",
) -> PipelineResult:
    """Execute deterministic client pipeline.

    Steps:
        a) Classify gate — CHITCHAT/OFF_TOPIC returns canned response.
        b) Agent intent gate — mortgage/handoff/daily_summary signals needs_agent.
        c) RAG pipeline — retrieve + grade + rerank + optional rewrite.
        d) Generate — LLM answer if RAG cache missed.
        e) Send — response + sources to Telegram.
        f) Post-process — cache store (with guards), history save, Langfuse scores.

    Args:
        user_text: Raw user message.
        user_id: Telegram user ID.
        session_id: Session identifier.
        message: aiogram Message for sending responses.
        cache: CacheLayerManager instance.
        embeddings: BGEM3HybridEmbeddings (or compatible).
        sparse_embeddings: Sparse embedding service.
        qdrant: QdrantService instance.
        reranker: Reranker service or None.
        llm: LLM client or None (generate_response uses its own via config).
        config: GraphConfig instance.
        history_service: Optional HistoryService for saving turns.
        rag_result_store: Dict with pre-computed embeddings from pre-agent cache check.
        role: User role ("client" or "manager").
        query_type: Pre-classified query type from classify_query().

    Returns:
        PipelineResult with answer, metadata, and routing signals.
    """
    pipeline_start = time.perf_counter()
    lf = get_client()

    # --- Step a) Classify gate ---
    if query_type in _NO_RAG_QUERY_TYPES:
        response_text = _build_non_rag_response(query_type)
        await _send_markdown_chunks(message, response_text)
        latency_ms = (time.perf_counter() - pipeline_start) * 1000
        return PipelineResult(
            answer=response_text,
            query_type=query_type,
            response_sent=True,
            latency_ms=latency_ms,
        )

    # --- Step b) Agent intent gate ---
    agent_intent = detect_agent_intent(user_text)
    if agent_intent:
        latency_ms = (time.perf_counter() - pipeline_start) * 1000
        return PipelineResult(
            needs_agent=True,
            agent_intent=agent_intent,
            query_type=query_type,
            latency_ms=latency_ms,
        )

    # --- Step c) RAG pipeline ---
    result: dict[str, Any] = {
        "query_type": query_type,
        "cache_hit": False,
        "llm_call_count": 0,
        "messages": [{"role": "user", "content": user_text}],
    }

    _store = rag_result_store or {}
    semantic_cache_already_checked = bool(_store.get("semantic_cache_already_checked"))
    contract_topic_hint = _store.get("state_contract", {}).get("topic_hint")
    if not isinstance(contract_topic_hint, str):
        topic_hint_label = get_query_topic_hint(user_text)
        contract_topic_hint = topic_hint_label.value if topic_hint_label is not None else None
    grounding_mode = get_grounding_mode(query_type=query_type, topic_hint=contract_topic_hint)
    state_contract = coerce_pre_agent_state_contract(
        _store,
        query_type=query_type,
        topic_hint=contract_topic_hint,
        grounding_mode=grounding_mode,
    )
    if state_contract is not None:
        state_contract["grounding_mode"] = grounding_mode
        state_contract["topic_hint"] = contract_topic_hint
        _store["state_contract"] = state_contract
    result["topic_hint"] = contract_topic_hint
    result["grounding_mode"] = grounding_mode
    pre_computed = (
        state_contract.get("dense_vector")
        if state_contract is not None
        else _store.get("cache_key_embedding")
    )
    pre_computed_sparse = (
        state_contract.get("sparse_vector")
        if state_contract is not None
        else _store.get("cache_key_sparse")
    )
    pre_computed_colbert = (
        state_contract.get("colbert_query")
        if state_contract is not None
        else _store.get("cache_key_colbert")
    )
    pre_agent_ms = float(_store.get("pre_agent_ms", 0.0) or 0.0)
    pre_agent_embed_ms = _store.get("pre_agent_embed_ms")
    pre_agent_cache_check_ms = _store.get("pre_agent_cache_check_ms")
    if pre_agent_ms > 0:
        result["pre_agent_ms"] = pre_agent_ms
    if isinstance(pre_agent_embed_ms, Real):
        result["pre_agent_embed_ms"] = float(pre_agent_embed_ms)
    if isinstance(pre_agent_cache_check_ms, Real):
        result["pre_agent_cache_check_ms"] = float(pre_agent_cache_check_ms)

    pipeline_result = await rag_pipeline(
        user_text,
        user_id=user_id,
        session_id=session_id,
        query_type=query_type,
        original_query=user_text,
        cache=cache,
        embeddings=embeddings,
        sparse_embeddings=sparse_embeddings,
        qdrant=qdrant,
        reranker=reranker,
        llm=llm,
        agent_role=role,
        state_contract=state_contract,
        pre_computed_embedding=pre_computed,
        pre_computed_sparse=pre_computed_sparse,
        pre_computed_colbert=pre_computed_colbert,
        semantic_cache_already_checked=semantic_cache_already_checked,
    )
    result.update(pipeline_result)
    response_text = str(pipeline_result.get("response", "") or "")

    # --- Step d) Generate if RAG did not return cached response ---
    if not response_text:
        generated = await generate_response(
            query=user_text,
            documents=result.get("documents", []),
            retrieved_context=result.get("retrieved_context", []),
            raw_messages=[{"role": "user", "content": user_text}],
            latency_stages=result.get("latency_stages", {}),
            llm_call_count=int(result.get("llm_call_count", 0) or 0),
            grounding_mode=grounding_mode,
            config=config,
            message=message,
        )
        result.update(generated)
        response_text = str(generated.get("response", "") or "")

    result["response"] = response_text

    # --- Step e) Send ---
    trace_id = lf.get_current_trace_id() or ""
    reply_markup = None
    if trace_id:
        from telegram_bot.feedback import build_feedback_keyboard

        reply_markup = build_feedback_keyboard(trace_id)

    sources_text = ""
    documents_list: list[Any] = result.get("documents", [])
    sources_required = bool(getattr(config, "show_sources", False) or grounding_mode == "strict")
    if sources_required and documents_list:
        sources_text = format_sources(documents_list)
        result["sources_count"] = min(len(documents_list), _MAX_SOURCES)

    response_already_sent = result.get("response_sent", False)
    if response_already_sent:
        # Streaming already delivered the main response; only send sources if applicable.
        if sources_text:
            await _send_markdown_chunks(message, sources_text, reply_markup=reply_markup)
        elif reply_markup:
            # Attach feedback keyboard to the streamed message (#745).
            ref = result.get("sent_message")
            if ref and isinstance(ref, dict):
                try:
                    await message.bot.edit_message_reply_markup(
                        chat_id=ref["chat_id"],
                        message_id=ref["message_id"],
                        reply_markup=reply_markup,
                    )
                except Exception:
                    logger.debug(
                        "Failed to attach feedback keyboard to streamed message",
                        exc_info=True,
                    )
    else:
        full_response = response_text + sources_text if sources_text else response_text
        await _send_markdown_chunks(message, full_response, reply_markup=reply_markup)

    # --- Step f) Post-process ---
    wall_ms = (time.perf_counter() - pipeline_start) * 1000
    e2e_wall_ms = wall_ms + pre_agent_ms
    topic_hint = result.get("topic_hint")
    topic_hint_value = topic_hint if isinstance(topic_hint, str) else ""
    grounding_mode = result.get("grounding_mode")
    grounding_mode_value = grounding_mode if isinstance(grounding_mode, str) else ""
    trace_metadata = {
        "route": "client_direct",
        "pipeline_mode": "client_direct",
        "query_type": query_type,
        "topic_hint": topic_hint_value,
        "grounding_mode": grounding_mode_value,
        "collection": _safe_collection_name(config),
        "environment": _safe_langfuse_env(config),
        "pipeline_wall_ms": wall_ms,
        "pre_agent_ms": pre_agent_ms,
        "e2e_latency_ms": e2e_wall_ms,
    }
    _store.update(trace_metadata)

    # Cache store — apply guards: type, contextual, confidence, source presence.
    store_vector = result.get("cache_key_embedding") or result.get("query_embedding")
    grade_confidence = float(result.get("grade_confidence", 0.0))
    raw_threshold = getattr(config, "relevance_threshold_rrf", _CONFIDENCE_THRESHOLD)
    confidence_threshold = (
        float(raw_threshold) if isinstance(raw_threshold, Real) else _CONFIDENCE_THRESHOLD
    )

    should_store = (
        cache
        and response_text
        and query_type in _PIPELINE_STORE_TYPES
        and not result.get("cache_hit", False)
        and isinstance(store_vector, list)
        and bool(store_vector)
        and not _is_contextual_query(user_text)
        and grade_confidence >= confidence_threshold
        and bool(documents_list)
    )

    if should_store:
        try:
            await cache.store_semantic(
                query=user_text,
                response=response_text,
                vector=store_vector,
                query_type=query_type,
                cache_scope="rag",
                agent_role=role,
            )
        except Exception:
            logger.warning("Failed to store semantic cache in client pipeline", exc_info=True)

    # Langfuse update + scores.
    lf.update_current_trace(
        input={"query": user_text},
        output={"response": response_text},
        tags=["telegram", "rag", "client_direct"],
        metadata=trace_metadata,
    )
    tid = trace_id or (lf.get_current_trace_id() or "")
    if tid:
        score(lf, tid, name="user_role", value=role, data_type="CATEGORICAL")
        result.update(
            {
                "pipeline_wall_ms": wall_ms,
                "user_perceived_wall_ms": e2e_wall_ms,
                "e2e_latency_ms": e2e_wall_ms,
                "query_type": query_type,
                "input_type": "text",
                "messages": [
                    *result.get("messages", []),
                    {"role": "assistant", "content": response_text},
                ],
            }
        )
        try:
            write_langfuse_scores(lf, result, trace_id=tid)
        except Exception:
            logger.warning("Failed to write Langfuse scores in client pipeline", exc_info=True)

    # History save.
    if history_service and response_text:
        try:
            saved = await history_service.save_turn(
                user_id=user_id,
                session_id=session_id,
                query=user_text,
                response=response_text,
                input_type="text",
                query_embedding=result.get("query_embedding"),
            )
            if tid:
                lf.create_score(
                    trace_id=tid,
                    name="history_save_success",
                    value=1 if saved else 0,
                    data_type="BOOLEAN",
                    score_id=f"{tid}-history_save_success",
                )
        except Exception:
            logger.warning("Failed to save history turn in client pipeline", exc_info=True)

    # Build sources list for PipelineResult.
    sources: list[dict[str, str]] = []
    for doc in documents_list[:_MAX_SOURCES]:
        if isinstance(doc, dict):
            meta = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            sources.append(
                {
                    "url": str(meta.get("url", "")),
                    "title": str(meta.get("title", meta.get("source", ""))),
                }
            )

    return PipelineResult(
        answer=response_text,
        sources=sources,
        query_type=query_type,
        cache_hit=bool(result.get("cache_hit", False)),
        needs_agent=False,
        latency_ms=wall_ms,
        llm_call_count=int(result.get("llm_call_count", 0) or 0),
        scores={
            k: float(v) for k, v in result.get("scores", {}).items() if isinstance(v, (int, float))
        },
        pipeline_mode="client_direct",
        sent_message=result.get("sent_message"),
        response_sent=True,
    )
