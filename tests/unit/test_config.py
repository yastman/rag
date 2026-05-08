from __future__ import annotations

import os
from unittest.mock import patch

from telegram_bot.config import BotConfig


def _bot_config(
    *, overrides: dict[str, str] | None = None, drop: set[str] | None = None
) -> BotConfig:
    env = os.environ.copy()
    for key in drop or set():
        env.pop(key, None)
    if overrides:
        env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        return BotConfig(_env_file=None)


def test_bot_config_defaults_prefer_local_litellm_proxy() -> None:
    cfg = _bot_config(drop={"LLM_BASE_URL", "LLM_MODEL"})

    assert cfg.llm_base_url == "http://localhost:4000/v1"
    assert cfg.llm_model == "gpt-4o-mini"


def test_bot_config_env_overrides_still_apply() -> None:
    cfg = _bot_config(
        overrides={
            "LLM_BASE_URL": "http://litellm:4000/v1",
            "LLM_MODEL": "custom-model",
        }
    )

    assert cfg.llm_base_url == "http://litellm:4000/v1"
    assert cfg.llm_model == "custom-model"
