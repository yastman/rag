"""Telegram HTML formatting and delivery helpers for answer text."""

from __future__ import annotations

import html
import logging
from typing import Any


logger = logging.getLogger(__name__)

_TELEGRAM_MESSAGE_LIMIT = 4096
_LONG_ANSWER_THRESHOLD = 900
_QUOTE_THRESHOLD = 120
_QUOTE_MAX_LEN = 220


def _escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def format_answer_html(text: str) -> str:
    """Render plain answer text into Telegram-safe HTML."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    paragraphs = [part.strip() for part in cleaned.split("\n\n") if part.strip()]
    if len(cleaned) >= _LONG_ANSWER_THRESHOLD and len(paragraphs) >= 3:
        lead = "\n\n".join(_escape_html(part) for part in paragraphs[:2])
        details = "\n\n".join(_escape_html(part) for part in paragraphs[2:])
        return f"{lead}\n\n<blockquote expandable>{details}</blockquote>"

    return _escape_html(cleaned)


def format_sources_html(documents: list[dict[str, Any]], max_sources: int = 5) -> str:
    """Format source documents as Telegram HTML attribution."""
    if not documents:
        return ""

    lines: list[str] = []
    for i, doc in enumerate(documents[:max_sources], 1):
        meta = doc.get("metadata", {})
        title = _escape_html(str(meta.get("title", "Документ")))
        city = str(meta.get("city", "") or "").strip()
        score = float(doc.get("score", 0) or 0)
        line = f"[{i}] {title}"
        if city:
            line += f" — {_escape_html(city)}"
        line += f" (рел: {score:.2f})"
        lines.append(line)

    body = "\n".join(lines)
    tag = "blockquote expandable" if len(body) > 180 or len(lines) > 2 else "blockquote"
    return f"\n\n📎 <b>Источники:</b>\n<{tag}>{body}</{tag.split()[0]}>"


def build_reply_parameters(message: Any, user_text: str) -> Any | None:
    """Build Telegram reply quote params for long/complex user questions."""
    if not isinstance(user_text, str):
        return None
    original_text = user_text
    text = user_text.strip()
    message_id = getattr(message, "message_id", None)
    if not isinstance(message_id, int):
        return None
    if len(text) < _QUOTE_THRESHOLD and "\n" not in text and text.count("?") <= 1:
        return None

    try:
        from aiogram.types import ReplyParameters
    except Exception:
        return None

    # Telegram requires `quote` to be an exact substring of the original message.
    # Keep the original whitespace and truncate by prefix only, without adding ellipsis.
    quote_text = original_text
    if len(quote_text) > _QUOTE_MAX_LEN:
        quote_text = quote_text[:_QUOTE_MAX_LEN]

    return ReplyParameters(
        message_id=message_id,
        quote=_escape_html(quote_text),
        quote_parse_mode="HTML",
    )


def _split_plain_text(text: str, limit: int = _TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split long plain text into Telegram-safe chunks before HTML formatting."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if len(cleaned) <= limit:
        return [cleaned]

    paragraphs = cleaned.split("\n\n")
    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(paragraph) <= limit:
            current = paragraph
            continue

        for i in range(0, len(paragraph), limit):
            chunks.append(paragraph[i : i + limit])

    if current:
        chunks.append(current)
    return chunks


def build_html_messages(
    answer_text: str,
    *,
    sources_html: str = "",
    limit: int = _TELEGRAM_MESSAGE_LIMIT,
) -> list[str]:
    """Build one or more HTML messages from raw answer text plus optional sources block."""
    chunks = _split_plain_text(answer_text, limit=limit)
    if not chunks:
        return [sources_html.lstrip()] if sources_html else []

    rendered = [format_answer_html(chunk) for chunk in chunks]
    if not sources_html:
        return rendered

    if len(rendered[-1]) + len(sources_html) <= limit:
        rendered[-1] = rendered[-1] + sources_html
    else:
        rendered.append(sources_html.lstrip())
    return rendered


async def send_html_messages(
    message: Any,
    answer_text: str,
    *,
    sources_html: str = "",
    reply_markup: Any | None = None,
    reply_to_user_text: str | None = None,
) -> bool:
    """Send formatted HTML response in one or more messages."""
    html_messages = build_html_messages(answer_text, sources_html=sources_html)
    if not html_messages:
        return False

    reply_parameters = (
        build_reply_parameters(message, reply_to_user_text or "") if reply_to_user_text else None
    )

    for index, html_text in enumerate(html_messages):
        is_first = index == 0
        is_last = index == len(html_messages) - 1
        kwargs: dict[str, Any] = {"parse_mode": "HTML"}
        if is_last:
            kwargs["reply_markup"] = reply_markup
        if is_first and reply_parameters is not None:
            kwargs["reply_parameters"] = reply_parameters

        try:
            await message.answer(html_text, **kwargs)
        except Exception:
            logger.warning("HTML parse failed, falling back to plain text")
            plain_kwargs = dict(kwargs)
            plain_kwargs.pop("parse_mode", None)
            try:
                await message.answer(html.unescape(html_text), **plain_kwargs)
            except Exception:
                logger.exception("Failed to send formatted response chunk")
                await message.answer(html.unescape(html_text))
    return True
