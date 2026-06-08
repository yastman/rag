"""Telegram adapter helpers for the assistant core rollout.

CORE-008 keeps these helpers isolated so the production text path can switch to
``src.core.run_assistant_request`` in a controlled follow-up without mixing
Telegram rendering with runtime RAG ownership.
"""

from __future__ import annotations

import os
from typing import Any

from src.core import (
    AssistantResult,
    CoreDependencies,
    UserContext,
    run_assistant_request,
)


CORE_ENTRYPOINT_ENV = "ASSISTANT_CORE_ENTRYPOINT_ENABLED"


def core_entrypoint_enabled() -> bool:
    """Return whether Telegram should use the assistant core entrypoint."""

    return os.getenv(CORE_ENTRYPOINT_ENV, "0").strip().lower() in {"1", "true", "yes", "on"}


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

    return await run_assistant_request(
        query,
        collection=collection,
        user_context=user_context,
        request_id=request_id,
        dependencies=dependencies,
    )


def response_text_for_telegram(result: AssistantResult) -> str:
    """Return the user-visible Telegram text for a core result."""

    return result.response_text


__all__ = [
    "CORE_ENTRYPOINT_ENV",
    "build_user_context",
    "core_entrypoint_enabled",
    "response_text_for_telegram",
    "run_core_text_request",
]
