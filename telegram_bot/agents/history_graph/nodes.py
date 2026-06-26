"""History sub-graph nodes — guard, retrieve, grade, rewrite, summarize (#408, #432).

Each node follows the LangGraph pattern: async function(state, **deps) → partial state update.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.runtime.graph.nodes.guard import detect_injection


logger = logging.getLogger(__name__)

# --- Blocked response for history guard ---

_HISTORY_BLOCKED_RESPONSE = (
    "Извините, ваш запрос не может быть обработан.\n\n"
    "Я помощник по недвижимости. Пожалуйста, задайте вопрос о вашей истории диалогов."
)


# --- Guard ---


async def history_guard_node(
    state: dict[str, Any],
    *,
    guard_mode: str = "hard",
) -> dict[str, Any]:
    """LangGraph node: detect prompt injection in history search queries (#432)."""
    t0 = time.perf_counter()
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
        if guard_mode == "hard":
            result["guard_blocked"] = True
            result["guard_reason"] = "injection"
            result["summary"] = _HISTORY_BLOCKED_RESPONSE
        elif guard_mode == "soft":
            result["guard_reason"] = "injection"

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


async def history_retrieve_node(
    state: dict[str, Any],
    *,
    history_service: Any,
) -> dict[str, Any]:
    """Retrieve conversation history via semantic search."""
    t0 = time.perf_counter()
    query = state["query"]
    user_id = state["user_id"]
    deal_id = state.get("deal_id")
    scope = state.get("scope", "all")

    try:
        results = await history_service.search_user_history(
            user_id=user_id,
            query=query,
            limit=_HISTORY_RETRIEVE_LIMIT,
            deal_id=deal_id,
            scope=scope,
        )
    except Exception:
        logger.exception("history_retrieve_node: search failed")
        results = []

    elapsed = time.perf_counter() - t0
    logger.info("history_retrieve: %d results for user=%s (%.3fs)", len(results), user_id, elapsed)

    return {
        "results": results,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": elapsed},
    }


# --- Grade ---

_HISTORY_RELEVANCE_THRESHOLD = 0.7


async def history_grade_node(
    state: dict[str, Any],
    *,
    threshold: float = _HISTORY_RELEVANCE_THRESHOLD,
) -> dict[str, Any]:
    """Grade retrieved history results by relevance score."""
    t0 = time.perf_counter()
    results = state.get("results", [])

    if not results:
        elapsed = time.perf_counter() - t0
        return {
            "results_relevant": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    relevant = [r for r in results if r.get("score", 0) >= threshold]
    is_relevant = len(relevant) > 0

    elapsed = time.perf_counter() - t0
    logger.info(
        "history_grade: %d/%d relevant (threshold=%.2f, %.3fs)",
        len(relevant),
        len(results),
        threshold,
        elapsed,
    )

    return {
        "results": relevant,
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


async def history_rewrite_node(
    state: dict[str, Any],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Rewrite the history search query for better retrieval."""
    t0 = time.perf_counter()
    original_query = state["query"]
    rewrite_count = state.get("rewrite_count", 0)

    try:
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()

        prompt = _HISTORY_REWRITE_PROMPT.format(query=original_query)
        response = await llm.chat.completions.create(
            model=config.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=64,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        if not rewritten or rewritten == original_query:
            rewritten = original_query
    except Exception:
        logger.exception("history_rewrite_node: LLM rewrite failed")
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


async def history_summarize_node(
    state: dict[str, Any],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Summarize retrieved history results using LLM."""
    t0 = time.perf_counter()
    query = state["query"]
    results = state.get("results", [])

    if not results:
        elapsed = time.perf_counter() - t0
        summary = _HISTORY_EMPTY_RESPONSE.format(query=query)
        return {
            "summary": summary,
            "latency_stages": {**state.get("latency_stages", {}), "summarize": elapsed},
        }

    used_llm = False
    try:
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()

        context = _format_history_context(results)
        prompt = _HISTORY_SUMMARIZE_PROMPT.format(query=query, context=context)
        response = await llm.chat.completions.create(
            model=config.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=512,
        )
        summary = (response.choices[0].message.content or "").strip()
        if not summary:
            summary = _format_raw_fallback(results)
        else:
            used_llm = True
    except Exception:
        logger.exception("history_summarize_node: LLM failed, using raw fallback")
        summary = _format_raw_fallback(results)

    elapsed = time.perf_counter() - t0
    logger.info("history_summarize: %d chars, used_llm=%s (%.3fs)", len(summary), used_llm, elapsed)

    return {
        "summary": summary,
        "latency_stages": {**state.get("latency_stages", {}), "summarize": elapsed},
    }


# --- Score helpers ---


def write_history_scores(lf: Any, result: dict[str, Any], *, trace_id: str = "") -> None:
    """No-op stub — tracing removed (#2844)."""
