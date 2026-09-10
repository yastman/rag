"""Behavior coverage for runtime domain defaults (#2949, #3406).

The #2949 structure ratchets (module-exists import check, per-constant
export/type checks, compatibility import-location asserts) were replaced by
one behavior table that probes each constant the way its consumers use it,
plus the live filter-signal detection test. Consumer-side compat is owned by
test_assistant_pipeline.py (CHITCHAT_RESPONSES) and
tests/contract/test_bot_no_private_runtime_internals_contract.py
(BLOCKED_RESPONSE via rag_core).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.runtime import domain_defaults as dd
from src.runtime.services.query_filter_signal import (
    QueryFilterSignal,
    detect_filter_sensitive_query,
)


@pytest.mark.parametrize(
    ("constant", "probe"),
    [
        ("_CITY_RE", lambda: dd._CITY_RE.search("квартира в Несебре") is not None),
        ("BLOCKED_RESPONSE", lambda: dd.BLOCKED_RESPONSE.strip() != ""),
        (
            "_REWRITE_PROMPT",
            lambda: "студия у моря" in dd._REWRITE_PROMPT.format(query="студия у моря"),
        ),
        (
            "CHITCHAT_RESPONSES",
            lambda: any(text.strip() for text in dd.CHITCHAT_RESPONSES.get("greeting", [])),
        ),
        (
            "OFF_TOPIC_RESPONSES",
            lambda: any(text.strip() for text in dd.OFF_TOPIC_RESPONSES),
        ),
    ],
    ids=[
        "city_pattern_matches_city_query",
        "blocked_response_is_user_facing",
        "rewrite_prompt_renders_query",
        "chitchat_greeting_available",
        "off_topic_responses_available",
    ],
)
def test_domain_default_serves_its_consumer(constant: str, probe: Callable[[], bool]) -> None:
    """Each domain default must satisfy the consumer contract listed in its row."""
    assert probe(), f"domain default {constant} no longer serves its consumers"


def test_detect_filter_sensitive_query_detects_city_price_rooms_currency() -> None:
    """Filter-sensitive detection keeps working through the domain_defaults import."""
    signal = detect_filter_sensitive_query("студия в Несебре до 80000 евро")
    assert signal == QueryFilterSignal(
        is_filter_sensitive=True,
        reasons=("city", "price", "rooms", "currency"),
    )
