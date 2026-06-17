"""Telegram adapter helpers for the assistant core.

These helpers isolate Telegram-specific transport from the assistant core
so the core path stays independent of the Telegram rendering surface.
"""

from __future__ import annotations

from typing import Any

from src.core import (
    AssistantResult,
    CoreDependencies,
    UserContext,
)
from src.core.app import AssistantApp


def build_user_context(
    *,
    user_id: int | str | None,
    session_id: str | None,
    role: str = "client",
    filters: dict[str, Any] | None = None,
    language: str = "ru",
) -> UserContext:
    """Build the transport-neutral context passed from Telegram into the core."""

    return UserContext(
        user_id=str(user_id or ""),
        session_id=session_id or "",
        role=role,
        filters=filters,
        language=language,
    )


async def run_core_text_request(
    *,
    query: str,
    collection: str,
    user_context: UserContext,
    dependencies: CoreDependencies,
    request_id: str | None = None,
) -> AssistantResult:
    """Call the assistant core from Telegram adapter code."""

    app = AssistantApp.from_dependencies(dependencies)
    return await app.run_text(
        query,
        collection=collection,
        user_context=user_context,
        request_id=request_id,
    )


def response_text_for_telegram(result: AssistantResult) -> str:
    """Return the user-visible Telegram text for a core result."""

    return result.response_text


__all__ = [
    "build_user_context",
    "response_text_for_telegram",
    "run_core_text_request",
]
