"""Response formatting, context assembly, and fallback helpers."""

from __future__ import annotations

import re
from typing import Any


_MAX_CONTEXT_DOCS = 5


def format_context(
    documents: list[dict[str, Any]],
    max_docs: int = _MAX_CONTEXT_DOCS,
    *,
    sources_enabled: bool = True,
) -> str:
    """Format top-N retrieved documents into LLM context string."""
    if not documents:
        return "Релевантной информации не найдено."

    parts: list[str] = []
    for i, doc in enumerate(documents[:max_docs], 1):
        text = doc.get("text", "")
        metadata = doc.get("metadata", {})
        score = doc.get("score", 0)

        meta_str = ""
        if "title" in metadata:
            meta_str += f"Название: {metadata['title']}\n"
        if "city" in metadata:
            meta_str += f"Город: {metadata['city']}\n"
        if "price" in metadata:
            meta_str += f"Цена: {metadata['price']:,}€\n"

        if sources_enabled:
            header = f"[Объект {i}] (релевантность: {score:.2f})"
        else:
            header = "Фрагмент контекста"
        parts.append(f"{header}\n{meta_str}{text}")

    return "\n\n---\n\n".join(parts)


_INLINE_CITATION_RE = re.compile(r"\s*\[(?:\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
_OBJECT_LABEL_RE = re.compile(r"\s*\[Объект\s+\d+\]")
_TRAILING_CITATION_SUFFIX_RE = re.compile(r"\s+(?:\d{1,2})(?:\.)?\s*$")


def sanitize_response_text(answer: str, *, sources_enabled: bool) -> str:
    """Strip citation-like artifacts from user-visible text when sources are disabled."""
    if sources_enabled or not answer:
        return answer

    sanitized_lines: list[str] = []
    for raw_line in answer.splitlines():
        line = _OBJECT_LABEL_RE.sub("", raw_line)
        line = _INLINE_CITATION_RE.sub("", line)
        if not re.match(r"^\s*\d+\.\s", line):
            line = _TRAILING_CITATION_SUFFIX_RE.sub("", line)
        sanitized_lines.append(line.rstrip())

    sanitized = "\n".join(sanitized_lines).strip()
    return sanitized or answer.strip()


def build_fallback_response(documents: list[dict[str, Any]]) -> str:
    """Build fallback response from retrieved documents when LLM fails."""
    if not documents:
        return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

    items: list[str] = []
    for doc in documents[:3]:
        meta = doc.get("metadata", {})
        parts: list[str] = []
        if "title" in meta:
            parts.append(f"**{meta['title']}**")
        if "price" in meta:
            price = meta["price"]
            if isinstance(price, int | float):
                parts.append(f"Цена: {price:,}€")
            else:
                parts.append(f"Цена: {price}€")
        if "city" in meta:
            parts.append(f"Город: {meta['city']}")
        if parts:
            items.append("\n   ".join(parts))

    if not items:
        return "⚠️ Извините, сервис временно недоступен.\n\nПопробуйте повторить запрос позже."

    fallback = "⚠️ Сервис генерации ответов временно недоступен.\n\n"
    fallback += "Найденные результаты:\n\n"
    for i, item in enumerate(items, 1):
        fallback += f"{i}. {item}\n\n"
    fallback += "Напишите менеджеру для получения детальной информации."
    return fallback
