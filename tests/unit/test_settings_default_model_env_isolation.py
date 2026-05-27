"""Regression test for #2197: provider default-model selection must be
isolated from local ``MODEL_NAME`` env / ``.env`` leakage in tests.

``Settings.model_name`` resolves to (in order): explicit argument, the
``MODEL_NAME`` env var, then the provider default. The env override is
intentional in production — operators set ``MODEL_NAME=...`` to swap
models without code changes. The bug surfaced in #2197 was test-side:
the existing ``TestDefaultModelSelection`` cases used
``patch.dict(..., clear=False)`` and inherited a developer's local
``MODEL_NAME`` from ``.env``, which made ``make test`` fail.

This module pins isolation: when ``MODEL_NAME`` is removed from the
environment, the provider default applies regardless of what the host
``.env`` originally contained.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.constants import ModelName
from src.config.settings import Settings


_PROVIDER_DEFAULT_CASES = [
    ("claude", "ANTHROPIC_API_KEY", ModelName.CLAUDE_SONNET.value),
    ("openai", "OPENAI_API_KEY", ModelName.GPT_4_TURBO.value),
    ("groq", "GROQ_API_KEY", ModelName.GROQ_LLAMA3_70B.value),
]


@pytest.mark.parametrize("provider,key_name,expected_model", _PROVIDER_DEFAULT_CASES)
def test_provider_default_applies_when_model_name_env_isolated(
    provider: str,
    key_name: str,
    expected_model: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When MODEL_NAME is removed from env, the provider default applies.

    Reproduces the failure mode in #2197: simulate a polluted env first
    (MODEL_NAME=zai-glm-4.7), then explicitly delenv it, then construct
    Settings. The provider default must win.
    """
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    monkeypatch.setenv("MODEL_NAME", "zai-glm-4.7")  # simulate .env pollution
    monkeypatch.delenv("MODEL_NAME", raising=False)  # the isolation contract
    monkeypatch.setenv(key_name, "test-key")

    settings = Settings(env_file=str(empty_env), api_provider=provider)

    assert settings.model_name == expected_model, (
        f"provider default for {provider} regressed under env isolation "
        f"(got {settings.model_name!r}, expected {expected_model!r})"
    )


def test_explicit_model_name_argument_overrides_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit model_name= still beats both env and provider default."""
    monkeypatch.setenv("MODEL_NAME", "zai-glm-4.7")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(api_provider="openai", model_name="gpt-4")

    assert settings.model_name == "gpt-4"


def test_model_name_env_override_still_works_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production behaviour pin: with no explicit argument and MODEL_NAME
    in env, the env value wins over the provider default. This guards
    against accidental regressions when adjusting test isolation."""
    monkeypatch.setenv("MODEL_NAME", "custom-model-from-env")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = Settings(api_provider="openai")

    assert settings.model_name == "custom-model-from-env"
