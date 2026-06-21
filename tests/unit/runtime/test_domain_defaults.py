"""Tests that domain-specific defaults are isolated in domain_defaults.py.

Issue: #2949 — domain logic isolation from generic runtime.
"""

from __future__ import annotations


def test_domain_defaults_module_exists() -> None:
    """domain_defaults module must be importable from src.runtime."""
    from src.runtime import domain_defaults  # noqa: F401


def test_domain_defaults_exports_city_pattern() -> None:
    """_CITY_RE must come from domain_defaults, not be redefined in query_filter_signal."""
    import re

    from src.runtime.domain_defaults import _CITY_RE

    assert isinstance(_CITY_RE, re.Pattern)
    assert _CITY_RE.search("квартира в Несебре")


def test_domain_defaults_exports_translit_map() -> None:
    """TRANSLIT_MAP must come from domain_defaults."""
    from src.runtime.domain_defaults import TRANSLIT_MAP

    assert isinstance(TRANSLIT_MAP, dict)
    assert "Nesebar" in TRANSLIT_MAP


def test_domain_defaults_exports_hyde_system_prompt() -> None:
    """HYDE_SYSTEM_PROMPT must come from domain_defaults."""
    from src.runtime.domain_defaults import HYDE_SYSTEM_PROMPT

    assert isinstance(HYDE_SYSTEM_PROMPT, str)
    assert len(HYDE_SYSTEM_PROMPT) > 0


def test_domain_defaults_exports_blocked_response() -> None:
    """BLOCKED_RESPONSE must come from domain_defaults."""
    from src.runtime.domain_defaults import BLOCKED_RESPONSE

    assert isinstance(BLOCKED_RESPONSE, str)
    assert len(BLOCKED_RESPONSE) > 0


def test_domain_defaults_exports_rewrite_prompt() -> None:
    """_REWRITE_PROMPT must come from domain_defaults."""
    from src.runtime.domain_defaults import _REWRITE_PROMPT

    assert isinstance(_REWRITE_PROMPT, str)
    assert "{query}" in _REWRITE_PROMPT


def test_domain_defaults_exports_chitchat_responses() -> None:
    """CHITCHAT_RESPONSES must come from domain_defaults."""
    from src.runtime.domain_defaults import CHITCHAT_RESPONSES

    assert isinstance(CHITCHAT_RESPONSES, dict)
    assert "greeting" in CHITCHAT_RESPONSES


def test_domain_defaults_exports_off_topic_responses() -> None:
    """OFF_TOPIC_RESPONSES must come from domain_defaults."""
    from src.runtime.domain_defaults import OFF_TOPIC_RESPONSES

    assert isinstance(OFF_TOPIC_RESPONSES, list)
    assert len(OFF_TOPIC_RESPONSES) > 0


def test_query_filter_signal_still_works_after_refactor() -> None:
    """detect_filter_sensitive_query must still work (imports from domain_defaults)."""
    from src.runtime.services.query_filter_signal import (
        QueryFilterSignal,
        detect_filter_sensitive_query,
    )

    signal = detect_filter_sensitive_query("студия в Несебре до 80000 евро")
    assert signal == QueryFilterSignal(
        is_filter_sensitive=True,
        reasons=("city", "price", "rooms", "currency"),
    )


def test_classify_node_chitchat_responses_still_importable() -> None:
    """CHITCHAT_RESPONSES must remain importable from classify for compat."""
    from src.runtime.graph.nodes.classify import CHITCHAT_RESPONSES

    assert "greeting" in CHITCHAT_RESPONSES


def test_rag_core_blocked_response_still_importable() -> None:
    """BLOCKED_RESPONSE must remain importable from rag_core for compat."""
    from src.runtime.services.rag_core import BLOCKED_RESPONSE

    assert isinstance(BLOCKED_RESPONSE, str)
