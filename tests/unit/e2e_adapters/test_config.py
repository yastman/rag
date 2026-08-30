from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

from scripts.e2e.config import E2EConfig


@contextmanager
def _cfg_from_env(
    overrides: dict[str, str] | None = None, drop: set[str] | None = None
) -> Iterator[E2EConfig]:
    env = os.environ.copy()
    for key in drop or set():
        env.pop(key, None)
    if overrides:
        env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        yield E2EConfig()


def test_defaults_prefer_litellm_router_and_alias() -> None:
    with _cfg_from_env(
        drop={
            "E2E_JUDGE_PROVIDER",
            "E2E_JUDGE_BASE_URL",
            "E2E_JUDGE_MODEL",
            "LLM_BASE_URL",
            "LLM_MODEL",
        }
    ) as cfg:
        assert cfg.judge_provider == "litellm"
        assert cfg.judge_base_url == ""
        assert cfg.judge_model == "gpt-4o-mini"


@pytest.mark.parametrize("outer_provider_key", (None, "issue-3257-fabricated-key"))
def test_validate_requires_openai_compatible_judge_api_key(
    monkeypatch: pytest.MonkeyPatch, outer_provider_key: str | None
) -> None:
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "CEREBRAS_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    if outer_provider_key is not None:
        monkeypatch.setenv("GROQ_API_KEY", outer_provider_key)

    with _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "hash",
            "E2E_JUDGE_PROVIDER": "litellm",
        },
        drop={
            "E2E_JUDGE_API_KEY",
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "CEREBRAS_API_KEY",
            "GROQ_API_KEY",
        },
    ) as cfg:
        assert (
            "At least one LLM provider key is required for judge provider 'litellm'"
            in cfg.validate()
        )


def test_validate_allows_no_judge_mode_without_judge_credentials() -> None:
    with _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "hash",
        },
        drop={
            "E2E_JUDGE_API_KEY",
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "CEREBRAS_API_KEY",
            "GROQ_API_KEY",
        },
    ) as cfg:
        errors = cfg.validate(judge_required=False)
        assert all("E2E_JUDGE" not in err and "ANTHROPIC_API_KEY" not in err for err in errors)


def test_validate_requires_anthropic_key_in_anthropic_direct_mode() -> None:
    with _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "hash",
            "E2E_JUDGE_PROVIDER": "anthropic-direct",
        },
        drop={"ANTHROPIC_API_KEY"},
    ) as cfg:
        assert "ANTHROPIC_API_KEY not set for judge provider 'anthropic-direct'" in cfg.validate()


def test_repr_redacts_credentials_but_keeps_diagnostics() -> None:
    secrets = (
        "fabricated-telegram-hash",
        "fabricated-judge-key",
        "fabricated-anthropic-key",
    )
    with _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "123",
            "TELEGRAM_API_HASH": secrets[0],
            "E2E_JUDGE_API_KEY": secrets[1],
            "ANTHROPIC_API_KEY": secrets[2],
            "E2E_COLLECTION_NAME": "diagnostic-collection",
        }
    ) as cfg:
        rendered = (repr(cfg), str(AssertionError(cfg)))

    assert all(secret not in output for secret in secrets for output in rendered)
    assert "telegram_api_id=123" in rendered[0]
    assert "test_collection='diagnostic-collection'" in rendered[0]


def test_pytest_bootstrap_disables_downstream_dotenv_discovery() -> None:
    with patch(
        "dotenv.main.find_dotenv",
        side_effect=AssertionError("implicit dotenv discovery attempted"),
    ) as find_dotenv:
        assert load_dotenv() is False

    find_dotenv.assert_not_called()
