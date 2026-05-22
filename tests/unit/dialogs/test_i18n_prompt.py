"""Tests for system prompt i18n and role_context variable (#444)."""

from __future__ import annotations

from unittest.mock import patch

from ._property_bot_ast import get_default_map, get_parameter_names, get_property_bot_method


def test_locale_to_language_mapping_covers_all_locales():
    """LOCALE_TO_LANGUAGE maps all supported locale codes."""
    from telegram_bot.agents.agent import LOCALE_TO_LANGUAGE

    assert "ru" in LOCALE_TO_LANGUAGE
    assert "en" in LOCALE_TO_LANGUAGE
    assert "uk" in LOCALE_TO_LANGUAGE
    assert LOCALE_TO_LANGUAGE["ru"] == "русском языке"
    assert LOCALE_TO_LANGUAGE["en"] == "English"
    assert LOCALE_TO_LANGUAGE["uk"] == "українською мовою"


def test_create_bot_agent_passes_role_context_to_prompt_manager():
    """create_bot_agent includes role_context in variables passed to get_prompt."""
    from telegram_bot.agents.agent import create_bot_agent

    with (
        patch("telegram_bot.agents.agent.create_agent"),
        patch("telegram_bot.agents.agent.get_prompt", return_value="prompt") as mock_get,
    ):
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            role="client",
            language="русском языке",
        )

    mock_get.assert_called_once()
    variables = mock_get.call_args.kwargs["variables"]
    assert "role_context" in variables
    assert "language" in variables
    assert variables["language"] == "русском языке"


def test_client_role_context_mentions_client():
    """role='client' passes role_context about helping clients."""
    from telegram_bot.agents.agent import create_bot_agent

    with (
        patch("telegram_bot.agents.agent.create_agent"),
        patch("telegram_bot.agents.agent.get_prompt", return_value="prompt") as mock_get,
    ):
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            role="client",
        )

    variables = mock_get.call_args.kwargs["variables"]
    assert "клиент" in variables["role_context"].lower()


def test_manager_role_context_mentions_crm():
    """role='manager' passes role_context about CRM."""
    from telegram_bot.agents.agent import create_bot_agent

    with (
        patch("telegram_bot.agents.agent.create_agent"),
        patch("telegram_bot.agents.agent.get_prompt", return_value="prompt") as mock_get,
    ):
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            role="manager",
        )

    variables = mock_get.call_args.kwargs["variables"]
    assert (
        "crm" in variables["role_context"].lower()
        or "менеджер" in variables["role_context"].lower()
    )


def test_handle_query_accepts_locale_parameter():
    """handle_query signature accepts locale kwarg injected by i18n middleware."""
    method = get_property_bot_method("handle_query")
    assert "locale" in get_parameter_names(method)
    assert get_default_map(method)["locale"] == "ru"


def test_handle_query_supervisor_accepts_locale_parameter():
    """_handle_query_supervisor accepts locale kwarg."""
    method = get_property_bot_method("_handle_query_supervisor")
    assert "locale" in get_parameter_names(method)
    assert get_default_map(method)["locale"] == "ru"
