"""History sub-graph nodes — guard, retrieve, grade, rewrite, summarize (#408, #432).

Each node follows the LangGraph pattern: async function(state, **deps) → partial state update.
All nodes decorated with @observe() for Langfuse tracing.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.graph.nodes.guard import detect_injection
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

# --- Blocked response for history guard ---

_HISTORY_BLOCKED_RESPONSE = (
    "Извините, ваш запрос не может быть обработан.\n\n"
    "Я помощник по недвижимости. Пожалуйста, задайте вопрос о вашей истории диалогов."
)


# --- Guard ---


@observe(name="history-guard")
async def history_guard_node(
    state: dict[str, Any],
    *,
    guard_mode: str = "hard",
) -> dict[str, Any]:
    """LangGraph node: detect prompt injection in history search queries (#432).

    Reuses detect_injection() regex heuristics from the main RAG guard.
    Adapts HistoryState (query field) instead of RAGState (messages field).

    Behavior depends on guard_mode:
    - "hard": blocks query, sets guard_blocked=True, fills summary with blocked message
    - "soft": sets guard_blocked=True, logs, continues to retrieve
    - "log": logs only, continues to retrieve
    """
    t0 = time.perf_counter()
    lf = get_client()
    query = state["query"]

    detected, risk_score, pattern = detect_injection(query)

    result: dict[str, Any] = {
        "guard_blocked": False,
        "guard_reason": None,
    }

    if detected:
        logger.warning(
            "History guard: injection detected (mode=%s, score=%.2f, pattern=%s): %.80s",
            guard_mode,
            risk_score,
            pattern,
            query,
        )
        lf.update_current_span(
            output={
                "injection_detected": True,
                "risk_score": risk_score,
                "pattern": pattern,
                "guard_mode": guard_mode,
            }
        )

        if guard_mode == "hard":
            result["guard_blocked"] = True
            result["guard_reason"] = "injection"
            result["summary"] = _HISTORY_BLOCKED_RESPONSE
        elif guard_mode == "soft":
            # Flag but don't block — continue to retrieve (matches main guard behavior)
            result["guard_reason"] = "injection"
    else:
        lf.update_current_span(output={"injection_detected": False, "risk_score": 0.0})

    result["latency_stages"] = {
        **state.get("latency_stages", {}),
        "guard": time.perf_counter() - t0,
    }
    return result


def route_history_guard(state: dict[str, Any]) -> str:
    """Route after guard: END if blocked in hard mode, else retrieve."""
    if state.get("guard_blocked") and state.get("guard_reason") == "injection":
        return "__end__"
    return "retrieve"


# --- Retrieve ---

_HISTORY_RETRIEVE_LIMIT = 10


@observe(name="history-retrieve", capture_input=False, capture_output=False)
async def history_retrieve_node(
    state: dict[str, Any],
    *,
    history_service: Any,
) -> dict[str, Any]:
    """Retrieve conversation history via semantic search.

    Calls HistoryService.search_user_history() with user isolation.
    """
    t0 = time.perf_counter()
    query = state["query"]
    user_id = state["user_id"]

    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120], "user_id": user_id})

    try:
        results = await history_service.search_user_history(
            user_id=user_id,
            query=query,
            limit=_HISTORY_RETRIEVE_LIMIT,
        )
    except Exception as e:
        logger.exception("history_retrieve_node: search failed")
        lf.update_current_span(
            level="ERROR", status_message=f"History search failed: {str(e)[:200]}"
        )
        results = []

    elapsed = time.perf_counter() - t0
    logger.info("history_retrieve: %d results for user=%s (%.3fs)", len(results), user_id, elapsed)

    lf.update_current_span(
        output={"results_count": len(results), "duration_ms": round(elapsed * 1000, 1)}
    )

    return {
        "results": results,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": elapsed},
    }


# --- Grade ---

_HISTORY_RELEVANCE_THRESHOLD = 0.7


@observe(name="history-grade")
async def history_grade_node(state: dict[str, Any]) -> dict[str, Any]:
    """Grade retrieved history results by relevance score.

    Filters out results below threshold and marks overall relevance.
    """
    t0 = time.perf_counter()
    results = state.get("results", [])

    if not results:
        elapsed = time.perf_counter() - t0
        return {
            "results_relevant": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    relevant = [r for r in results if r.get("score", 0) >= _HISTORY_RELEVANCE_THRESHOLD]
    is_relevant = len(relevant) > 0

    elapsed = time.perf_counter() - t0
    logger.info(
        "history_grade: %d/%d relevant (threshold=%.2f, %.3fs)",
        len(relevant),
        len(results),
        _HISTORY_RELEVANCE_THRESHOLD,
        elapsed,
    )

    return {
        "results": relevant or results[:3],  # fallback: top-3 if none pass
        "results_relevant": is_relevant,
        "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
    }


# --- Rewrite ---

_HISTORY_REWRITE_PROMPT = (
    "Пользователь ищет информацию в своей истории диалогов.\n"
    "Его запрос не дал релевантных результатов.\n\n"
    "Переформулируй запрос для лучшего семантического поиска по истории.\n"
    "Верни ТОЛЬКО переформулированный запрос, без пояснений.\n\n"
    "Оригинальный запрос: {query}"
)


@observe(name="history-rewrite")
async def history_rewrite_node(
    state: dict[str, Any],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Rewrite the history search query for better retrieval.

    Calls LLM to reformulate. Increments rewrite_count.
    Falls back to original query on LLM failure.
    """
    t0 = time.perf_counter()
    original_query = state["query"]
    rewrite_count = state.get("rewrite_count", 0)

    try:
        if llm is None:
            from telegram_bot.graph.config import GraphConfig

            config = GraphConfig.from_env()
            llm = config.create_llm()

        prompt = _HISTORY_REWRITE_PROMPT.format(query=original_query)
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=64,
            name="history-rewrite-query",  # type: ignore[call-overload]
        )
        rewritten = (response.choices[0].message.content or "").strip()
        if not rewritten or rewritten == original_query:
            rewritten = original_query
    except Exception as e:
        logger.exception("history_rewrite_node: LLM rewrite failed")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"History rewrite failed: {str(e)[:200]}",
        )
        rewritten = original_query

    elapsed = time.perf_counter() - t0
    logger.info(
        "history_rewrite: attempt %d, '%.50s' → '%.50s' (%.3fs)",
        rewrite_count + 1,
        original_query,
        rewritten,
        elapsed,
    )

    return {
        "query": rewritten,
        "rewrite_count": rewrite_count + 1,
        "latency_stages": {**state.get("latency_stages", {}), "rewrite": elapsed},
    }


# --- Routing ---


def route_history_grade(state: dict[str, Any]) -> str:
    """Route after grade: summarize if relevant or rewrites exhausted, else rewrite."""
    if state.get("results_relevant"):
        return "summarize"
    if state.get("rewrite_count", 0) >= state.get("max_rewrite_attempts", 1):
        return "summarize"
    return "rewrite"


# --- Summarize ---

_HISTORY_SUMMARIZE_PROMPT = (
    "Ты — помощник, который анализирует историю предыдущих диалогов пользователя.\n\n"
    "Пользователь спросил: «{query}»\n\n"
    "Вот релевантные фрагменты из его прошлых разговоров:\n\n"
    "{context}\n\n"
    "Составь краткий ответ на основе истории. Укажи:\n"
    "- Какие вопросы пользователь задавал ранее по этой теме\n"
    "- Ключевые факты из предыдущих ответов\n"
    "- Даты диалогов (если есть)\n\n"
    "Отвечай на русском. Будь лаконичным."
)

_HISTORY_EMPTY_RESPONSE = "По запросу «{query}» ничего не найдено в истории ваших диалогов."


def _format_history_context(results: list[dict[str, Any]]) -> str:
    """Format history results as context for LLM prompt."""
    lines = []
    for i, r in enumerate(results, 1):
        ts = str(r.get("timestamp", ""))[:16].replace("T", " ")
        q = r.get("query", "")
        resp = r.get("response", "")
        # Truncate long responses for prompt budget
        if len(resp) > 500:
            resp = resp[:500] + "..."
        lines.append(f"[{i}] ({ts}) Q: {q}\n    A: {resp}")
    return "\n\n".join(lines)


def _format_raw_fallback(results: list[dict[str, Any]]) -> str:
    """Format results without LLM (fallback on error)."""
    lines = []
    for i, r in enumerate(results, 1):
        ts = str(r.get("timestamp", ""))[:16].replace("T", " ")
        lines.append(f"{i}. [{ts}] Q: {r.get('query', '')}")
        resp = r.get("response", "")
        if len(resp) > 200:
            resp = resp[:200] + "..."
        lines.append(f"   A: {resp}")
    return "\n".join(lines)


@observe(name="history-summarize", capture_input=False, capture_output=False)
async def history_summarize_node(
    state: dict[str, Any],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Summarize retrieved history results using LLM.

    Falls back to raw formatting on LLM failure or empty results.
    """
    t0 = time.perf_counter()
    query = state["query"]
    results = state.get("results", [])

    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120], "results_count": len(results)})

    if not results:
        elapsed = time.perf_counter() - t0
        summary = _HISTORY_EMPTY_RESPONSE.format(query=query)
        lf.update_current_span(output={"summary_length": len(summary), "used_llm": False})
        return {
            "summary": summary,
            "latency_stages": {**state.get("latency_stages", {}), "summarize": elapsed},
        }

    used_llm = False
    try:
        if llm is None:
            from telegram_bot.graph.config import GraphConfig

            config = GraphConfig.from_env()
            llm = config.create_llm()

        context = _format_history_context(results)
        prompt = _HISTORY_SUMMARIZE_PROMPT.format(query=query, context=context)
        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=512,
            name="history-summarize",  # type: ignore[call-overload]
        )
        summary = (response.choices[0].message.content or "").strip()
        if not summary:
            summary = _format_raw_fallback(results)
        else:
            used_llm = True
    except Exception as e:
        logger.exception("history_summarize_node: LLM failed, using raw fallback")
        lf.update_current_span(
            level="ERROR", status_message=f"History summarize failed: {str(e)[:200]}"
        )
        summary = _format_raw_fallback(results)

    elapsed = time.perf_counter() - t0
    logger.info("history_summarize: %d chars, used_llm=%s (%.3fs)", len(summary), used_llm, elapsed)
    lf.update_current_span(
        output={
            "summary_length": len(summary),
            "used_llm": used_llm,
            "duration_ms": round(elapsed * 1000, 1),
        }
    )

    return {
        "summary": summary,
        "latency_stages": {**state.get("latency_stages", {}), "summarize": elapsed},
    }


# --- Langfuse Scores ---


def write_history_scores(lf: Any, result: dict[str, Any], *, trace_id: str = "") -> None:
    """Write history sub-graph scores with explicit trace_id (#435).

    Scores:
        history_results_count (NUMERIC): Number of retrieved results.
        history_relevance (NUMERIC): 1.0 if relevant, 0.0 if not.
        history_rewrite_count (NUMERIC): Number of query rewrites.
        history_latency_ms (NUMERIC): Total sub-graph wall time (ms).
    """
    if not trace_id:
        trace_id = lf.get_current_trace_id()
    if not trace_id:
        return

    results = result.get("results", [])
    latency_stages = result.get("latency_stages", {})
    total_ms = sum(latency_stages.values()) * 1000

    lf.create_score(
        trace_id=trace_id,
        name="history_results_count",
        value=len(results),
        id=f"{trace_id}-history_results_count",
    )
    lf.create_score(
        trace_id=trace_id,
        name="history_relevance",
        value=1.0 if result.get("results_relevant") else 0.0,
        id=f"{trace_id}-history_relevance",
    )
    lf.create_score(
        trace_id=trace_id,
        name="history_rewrite_count",
        value=result.get("rewrite_count", 0),
        id=f"{trace_id}-history_rewrite_count",
    )
    lf.create_score(
        trace_id=trace_id,
        name="history_latency_ms",
        value=round(total_ms, 1),
        id=f"{trace_id}-history_latency_ms",
    )
