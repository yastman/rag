"""Context formatting for runtime generation."""

from __future__ import annotations

from typing import Any


_MAX_CONTEXT_DOCS = 5


def _format_context(documents: list[dict[str, Any]], max_docs: int = _MAX_CONTEXT_DOCS) -> str:
    """Format top-N retrieved documents into LLM context string."""
    return _format_context_for_mode(documents, max_docs=max_docs, sources_enabled=True)


def _format_context_for_mode(
    documents: list[dict[str, Any]],
    max_docs: int = _MAX_CONTEXT_DOCS,
    *,
    sources_enabled: bool,
) -> str:
    """Format top-N retrieved documents into LLM context string for current source mode."""
    if not documents:
        return "Релевантной информации не найдено."

    parts: list[str] = []
    for i, doc in enumerate(documents[:max_docs], 1):
        text = doc.get("text", "")
        metadata = doc.get("metadata", {}) or {}
        score = doc.get("score", 0)

        meta_str = ""
        if "title" in metadata:
            meta_str += f"Название: {metadata['title']}\n"
        if "city" in metadata:
            meta_str += f"Город: {metadata['city']}\n"
        if "price" in metadata:
            try:
                price_val = metadata["price"]
                if isinstance(price_val, (int, float)):
                    meta_str += f"Цена: {price_val:,}€\n"
                else:
                    meta_str += f"Цена: {price_val}€\n"
            except Exception:
                meta_str += f"Цена: {metadata['price']}€\n"

        if sources_enabled:
            header = f"[Объект {i}] (релевантность: {score:.2f})"
        else:
            header = "Фрагмент контекста"
        parts.append(f"{header}\n{meta_str}{text}")

    return "\n\n---\n\n".join(parts)
