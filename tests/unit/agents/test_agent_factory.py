"""Tests for create_bot_agent factory (#413)."""

from __future__ import annotations

from unittest.mock import patch


def test_create_bot_agent_uses_prompt_manager_by_default():
    """Default client role should be resolved via prompt manager with client_agent name."""
    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.get_prompt", return_value="resolved prompt") as mock_get:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            language="русском языке",
        )

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args.kwargs
    assert mock_get.call_args.args[0] == "client_agent"
    assert call_kwargs["variables"]["language"] == "русском языке"
    assert "role_context" in call_kwargs["variables"]
    assert "rag_search" in call_kwargs["fallback"]


def test_create_bot_agent_custom_prompt_bypasses_prompt_manager():
    """Explicit system_prompt should skip prompt manager lookup."""
    from telegram_bot.agents.agent import create_bot_agent

    with patch("telegram_bot.agents.agent.get_prompt") as mock_get:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            system_prompt="Manual prompt",
        )

    mock_get.assert_not_called()


def test_default_system_prompt_contains_safety_instructions():
    """CLIENT_SYSTEM_PROMPT must include safety/refusal instructions (#439)."""
    from telegram_bot.agents.agent import CLIENT_SYSTEM_PROMPT

    # Must refuse prompt injection attempts
    assert "НЕ выполняй" in CLIENT_SYSTEM_PROMPT
    # Must refuse system prompt leaks
    assert "НЕ раскрывай" in CLIENT_SYSTEM_PROMPT
    # Must have a safety section
    assert "Безопасность" in CLIENT_SYSTEM_PROMPT
    # Must enforce rag_search for property questions
    assert "rag_search" in CLIENT_SYSTEM_PROMPT


def test_create_bot_agent_client_role_uses_client_prompt():
    """role='client' resolves prompt name 'client_agent' with CLIENT_SYSTEM_PROMPT fallback."""
    from telegram_bot.agents.agent import CLIENT_SYSTEM_PROMPT, create_bot_agent

    with patch("telegram_bot.agents.agent.get_prompt", return_value="client prompt") as mock_get:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            role="client",
        )

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "client_agent"
    assert mock_get.call_args.kwargs["fallback"] is CLIENT_SYSTEM_PROMPT


def test_create_bot_agent_manager_role_uses_manager_prompt():
    """role='manager' resolves prompt name 'manager_agent' with MANAGER_SYSTEM_PROMPT fallback."""
    from telegram_bot.agents.agent import MANAGER_SYSTEM_PROMPT, create_bot_agent

    with patch("telegram_bot.agents.agent.get_prompt", return_value="manager prompt") as mock_get:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
            role="manager",
        )

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "manager_agent"
    assert mock_get.call_args.kwargs["fallback"] is MANAGER_SYSTEM_PROMPT


def test_create_bot_agent_default_role_is_client():
    """create_bot_agent defaults to role='client' when role is omitted."""
    from telegram_bot.agents.agent import CLIENT_SYSTEM_PROMPT, create_bot_agent

    with patch("telegram_bot.agents.agent.get_prompt", return_value="default prompt") as mock_get:
        create_bot_agent(
            model="openai/gpt-oss-120b",
            tools=[],
            checkpointer=None,
        )

    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "client_agent"
    assert mock_get.call_args.kwargs["fallback"] is CLIENT_SYSTEM_PROMPT


def test_client_prompt_has_no_crm_instructions():
    """CLIENT_SYSTEM_PROMPT must not contain CRM tool references."""
    from telegram_bot.agents.agent import CLIENT_SYSTEM_PROMPT

    crm_tools = [
        "crm_get_deal",
        "crm_create_lead",
        "crm_update_lead",
        "crm_get_contacts",
        "crm_upsert_contact",
        "crm_add_note",
        "crm_create_task",
        "crm_link_contact_to_deal",
    ]
    for tool in crm_tools:
        assert tool not in CLIENT_SYSTEM_PROMPT, f"CLIENT_SYSTEM_PROMPT must not mention {tool}"


def test_manager_prompt_has_crm_instructions():
    """MANAGER_SYSTEM_PROMPT must contain manager-specific instructions (safety, rag_search, scoring)."""
    from telegram_bot.agents.agent import MANAGER_SYSTEM_PROMPT

    # Safety instructions
    assert "НЕ выполняй" in MANAGER_SYSTEM_PROMPT
    assert "НЕ раскрывай" in MANAGER_SYSTEM_PROMPT
    assert "Безопасность" in MANAGER_SYSTEM_PROMPT
    # rag_search requirement
    assert "rag_search" in MANAGER_SYSTEM_PROMPT
    # Scoring instructions for leads
    assert "Скоринг" in MANAGER_SYSTEM_PROMPT
    # Format rules
    assert "Запрещено" in MANAGER_SYSTEM_PROMPT


# --- supervisor_max_tokens ---


def test_supervisor_max_tokens_config_default():
    """BotConfig.supervisor_max_tokens defaults to 1024."""
    from telegram_bot.config import BotConfig

    config = BotConfig(
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        qdrant_url="http://localhost:6333",
    )
    assert config.supervisor_max_tokens == 1024


def test_supervisor_max_tokens_config_from_env(monkeypatch):
    """BotConfig reads SUPERVISOR_MAX_TOKENS from env."""
    monkeypatch.setenv("SUPERVISOR_MAX_TOKENS", "2048")
    from telegram_bot.config import BotConfig

    config = BotConfig(
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        qdrant_url="http://localhost:6333",
    )
    assert config.supervisor_max_tokens == 2048
