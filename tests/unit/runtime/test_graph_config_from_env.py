"""Executable field/default and loading contract for the runtime configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.runtime.config import GraphConfig
from src.runtime.integrations.redis_mode import RedisMode


# Public runtime settings: canonical constructor name, environment name,
# default, textual environment override, and its typed result.
CASES = [
    ("llm_model", "LLM_MODEL", "gpt-4o-mini", "custom-model", "custom-model"),
    ("llm_temperature", "LLM_TEMPERATURE", 0.7, "0.3", 0.3),
    ("generate_max_tokens", "GENERATE_MAX_TOKENS", 1024, "512", 512),
    ("reasoning_effort", "REASONING_EFFORT", None, "low", "low"),
    ("reasoning_format", "REASONING_FORMAT", None, "hidden", "hidden"),
    ("disable_reasoning", "DISABLE_REASONING", None, "false", False),
    ("rewrite_model", "REWRITE_MODEL", "gpt-4o-mini", "rewrite-model", "rewrite-model"),
    ("rewrite_max_tokens", "REWRITE_MAX_TOKENS", 64, "128", 128),
    ("bge_m3_timeout", "BGE_M3_TIMEOUT", 120.0, "60.5", 60.5),
    ("rerank_top_k", "RERANK_TOP_K", 7, "5", 5),
    (
        "redis_url",
        "REDIS_URL",
        "redis://redis:6379",
        "redis://localhost:6380",
        "redis://localhost:6380",
    ),
    ("redis_mode", "REDIS_MODE", RedisMode.DISABLED, "single_instance", RedisMode.SINGLE_INSTANCE),
    ("max_rewrite_attempts", "MAX_REWRITE_ATTEMPTS", 1, "2", 2),
    ("skip_rerank_threshold", "SKIP_RERANK_THRESHOLD", 0.018, "0.02", 0.02),
    ("relevance_threshold_rrf", "RELEVANCE_THRESHOLD_RRF", 0.005, "0.006", 0.006),
    ("score_improvement_delta", "SCORE_IMPROVEMENT_DELTA", 0.001, "0.002", 0.002),
    ("small_to_big_mode", "SMALL_TO_BIG_MODE", "on", "off", "off"),
    ("small_to_big_window_before", "SMALL_TO_BIG_WINDOW_BEFORE", 0, "1", 1),
    ("small_to_big_window_after", "SMALL_TO_BIG_WINDOW_AFTER", 2, "3", 3),
    ("max_expanded_chunks", "MAX_EXPANDED_CHUNKS", 10, "6", 6),
    ("max_context_tokens", "MAX_CONTEXT_TOKENS", 8000, "4000", 4000),
    ("domain", "BOT_DOMAIN", "недвижимость", "healthcare", "healthcare"),
    ("response_style_enabled", "RESPONSE_STYLE_ENABLED", False, "true", True),
    ("response_style_shadow_mode", "RESPONSE_STYLE_SHADOW_MODE", False, "true", True),
    ("show_sources", "SHOW_SOURCES", False, "true", True),
    ("guard_mode", "GUARD_MODE", "hard", "soft", "soft"),
    ("content_filter_enabled", "CONTENT_FILTER_ENABLED", True, "false", False),
]


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_path):
    for field, env, *_ in CASES:
        monkeypatch.delenv(field, raising=False)
        monkeypatch.delenv(env, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.mark.parametrize("field,env,default,text,value", CASES)
def test_field_defaults_and_environment_override(monkeypatch, field, env, default, text, value):
    assert getattr(GraphConfig(), field) == default
    assert getattr(GraphConfig.from_env(), field) == default
    monkeypatch.setenv(env, text)
    assert getattr(GraphConfig.from_env(), field) == value
    assert getattr(GraphConfig(**{field: value}), field) == value


@pytest.mark.parametrize("field,env,default,text,value", CASES)
def test_field_name_alias_loads_from_environment(monkeypatch, field, env, default, text, value):
    monkeypatch.setenv(field, text)
    assert getattr(GraphConfig.from_env(), field) == value


@pytest.mark.parametrize("rewrite", [None, "", "explicit-rewrite"])
def test_rewrite_model_environment_fallback(monkeypatch, rewrite):
    monkeypatch.setenv("LLM_MODEL", "environment-model")
    if rewrite is not None:
        monkeypatch.setenv("REWRITE_MODEL", rewrite)
    assert GraphConfig.from_env().rewrite_model == (rewrite or "environment-model")
    assert GraphConfig(llm_model="direct-model").rewrite_model == "gpt-4o-mini"


def test_constructor_and_env_loader_ignore_dotenv(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("LLM_MODEL=dotenv-model\n", encoding="utf-8")
    assert GraphConfig().llm_model == "gpt-4o-mini"
    assert GraphConfig.from_env().llm_model == "gpt-4o-mini"
    monkeypatch.setenv("LLM_MODEL", "environment-model")
    assert GraphConfig().llm_model == "gpt-4o-mini"
    assert GraphConfig(llm_model="explicit-model").llm_model == "explicit-model"
    assert GraphConfig.from_env().llm_model == "environment-model"


@pytest.mark.parametrize("from_env", [False, True])
def test_graph_config_keeps_redis_credentials_out_of_repr(monkeypatch, from_env):
    secret_url = "redis://:graph-secret-repr-canary@redis:6379"
    monkeypatch.setenv("REDIS_URL", secret_url)
    config = GraphConfig.from_env() if from_env else GraphConfig(redis_url=secret_url)
    assert config.redis_url == secret_url
    assert secret_url not in repr(config)
    assert "graph-secret-repr-canary" not in repr(config)


def test_empty_environment_normalization(monkeypatch):
    for key in ("REASONING_EFFORT", "REASONING_FORMAT", "REDIS_MODE"):
        monkeypatch.setenv(key, "")
    config = GraphConfig.from_env()
    assert config.reasoning_effort is None
    assert config.reasoning_format is None
    assert config.redis_mode is RedisMode.DISABLED
    assert GraphConfig(reasoning_effort="", reasoning_format="").reasoning_effort == ""


@pytest.mark.parametrize(
    "values,expected",
    [
        ({}, {}),
        ({"reasoning_effort": "low"}, {"reasoning_effort": "low"}),
        ({"reasoning_format": "hidden"}, {"extra_body": {"reasoning_format": "hidden"}}),
        (
            {"reasoning_effort": "low", "reasoning_format": "hidden"},
            {"reasoning_effort": "low", "extra_body": {"reasoning_format": "hidden"}},
        ),
        (
            {"disable_reasoning": False, "reasoning_effort": "low", "reasoning_format": "hidden"},
            {"extra_body": {"disable_reasoning": False}},
        ),
        ({"disable_reasoning": True}, {"extra_body": {"disable_reasoning": True}}),
    ],
)
def test_reasoning_request_parameters(values, expected):
    assert GraphConfig(**values).get_reasoning_kwargs() == expected


def test_unknown_constructor_argument_fails_clearly():
    with pytest.raises((TypeError, ValidationError), match="misspelled_setting"):
        GraphConfig(misspelled_setting=1)


@pytest.mark.parametrize("env,value", [("RERANK_TOP_K", "invalid"), ("SHOW_SOURCES", "invalid")])
def test_invalid_typed_environment_fails(monkeypatch, env, value):
    monkeypatch.setenv(env, value)
    with pytest.raises(ValidationError):
        GraphConfig.from_env()
