from __future__ import annotations

import os
from unittest.mock import patch

from scripts.e2e.config import E2EConfig


def _cfg_from_env(
    overrides: dict[str, str] | None = None, drop: set[str] | None = None
) -> E2EConfig:
    env = os.environ.copy()
    for key in drop or set():
        env.pop(key, None)
    if overrides:
        env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        return E2EConfig()


def test_defaults_prefer_litellm_proxy_and_alias() -> None:
    cfg = _cfg_from_env(
        drop={
            "E2E_JUDGE_PROVIDER",
            "E2E_JUDGE_BASE_URL",
            "E2E_JUDGE_MODEL",
            "LLM_BASE_URL",
            "LLM_MODEL",
        }
    )

    assert cfg.judge_provider == "litellm"
    assert cfg.judge_base_url == "http://localhost:4000/v1"
    assert cfg.judge_model == "gpt-4o-mini"


def test_validate_requires_openai_compatible_judge_api_key() -> None:
    cfg = _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "hash",
            "E2E_JUDGE_PROVIDER": "litellm",
        },
        drop={"E2E_JUDGE_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "LITELLM_MASTER_KEY"},
    )

    assert "E2E_JUDGE_API_KEY not set for judge provider 'litellm'" in cfg.validate()


def test_validate_allows_no_judge_mode_without_judge_credentials() -> None:
    cfg = _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "hash",
        },
        drop={"E2E_JUDGE_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "LITELLM_MASTER_KEY"},
    )

    errors = cfg.validate(judge_required=False)
    assert all("E2E_JUDGE" not in err and "ANTHROPIC_API_KEY" not in err for err in errors)


def test_validate_requires_anthropic_key_in_anthropic_direct_mode() -> None:
    cfg = _cfg_from_env(
        overrides={
            "TELEGRAM_API_ID": "1",
            "TELEGRAM_API_HASH": "hash",
            "E2E_JUDGE_PROVIDER": "anthropic-direct",
        },
        drop={"ANTHROPIC_API_KEY"},
    )

    assert "ANTHROPIC_API_KEY not set for judge provider 'anthropic-direct'" in cfg.validate()
