"""Session summary generation for CRM integration.

Generates structured summaries from Q&A dialog turns using LLM.
"""

import logging
from typing import Literal

from pydantic import BaseModel


logger = logging.getLogger(__name__)


class SessionSummary(BaseModel):
    """Structured summary of a bot-client dialog session.

    Used for CRM note generation (Kommo) and manager context.
    """

    brief: str
    """1-2 sentences summarizing the main topic and outcome."""

    client_needs: list[str]
    """What the client is looking for (extracted needs)."""

    budget: str | None = None
    """Budget if mentioned by client, None otherwise."""

    preferences: list[str]
    """Client preferences: location, floor, area, amenities, etc."""

    next_steps: list[str]
    """Agreed next actions or follow-ups."""

    sentiment: Literal["positive", "neutral", "negative"]
    """Overall conversation tone."""
