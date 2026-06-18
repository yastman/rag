"""Tests for generate_node — verifies graph node uses canonical streaming from services."""

from __future__ import annotations


def test_streaming_partial_delivery_error_is_canonical() -> None:
    """StreamingPartialDeliveryError in graph node is the same class as in services."""
    from telegram_bot.graph.nodes.generate import StreamingPartialDeliveryError as NodeError
    from telegram_bot.services.generate_response import (
        StreamingPartialDeliveryError as ServiceError,
    )

    assert NodeError is ServiceError, (
        "graph/nodes/generate.StreamingPartialDeliveryError must be the canonical class "
        "from services/generate_response, not a local duplicate"
    )


def test_generate_node_does_not_define_local_generate_streaming() -> None:
    """generate_node no longer defines a local _generate_streaming — uses service default."""
    import telegram_bot.graph.nodes.generate as mod

    # The local duplicate should not exist
    assert not hasattr(mod, "_generate_streaming"), (
        "Local _generate_streaming was removed; graph node now uses "
        "the canonical implementation from services/generate_response"
    )


def test_generate_node_uses_canonical_generate_streaming() -> None:
    """generate_node delegates to service without overriding generate_streaming callback."""
    import inspect

    from telegram_bot.graph.nodes.generate import generate_node

    source = inspect.getsource(generate_node)
    # Must NOT pass generate_streaming= to the service (no local override)
    assert "generate_streaming=" not in source, (
        "generate_node must not pass generate_streaming= to the service; "
        "it should use the canonical default from services/generate_response"
    )
    # Must call the service function
    assert "_generate_response_service" in source


async def test_generate_node_non_streaming_returns_response() -> None:
    """generate_node non-streaming path returns a response dict."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from telegram_bot.graph.state import make_initial_state

    mock_choice = MagicMock()
    mock_choice.message.content = "Canonical answer."
    mock_response = MagicMock(choices=[mock_choice], model="gpt-4o-mini", usage=None)
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    mock_config = MagicMock()
    mock_config.domain = "недвижимость"
    mock_config.llm_model = "gpt-4o-mini"
    mock_config.llm_temperature = 0.1
    mock_config.generate_max_tokens = 128
    mock_config.streaming_enabled = False
    mock_config.show_sources = False
    mock_config.response_style_enabled = False
    mock_config.response_style_shadow_mode = False
    mock_config.create_llm.return_value = mock_client

    state = make_initial_state(user_id=1, session_id="s", query="test query")
    state["documents"] = [{"text": "Context doc", "score": 0.9, "metadata": {}}]

    from telegram_bot.graph.nodes.generate import generate_node

    mock_lf = MagicMock()
    with (
        patch("telegram_bot.graph.nodes.generate._get_config", return_value=mock_config),
        patch("telegram_bot.graph.nodes.generate.get_client", return_value=mock_lf),
        patch("src.runtime.services.response_style_detector.get_client", return_value=mock_lf),
        patch("src.runtime.generation.service.get_client", return_value=mock_lf),
    ):
        result = await generate_node(state)

    assert result["response"] == "Canonical answer."
    assert "generate" in result["latency_stages"]
