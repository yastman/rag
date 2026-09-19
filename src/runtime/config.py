"""Typed runtime settings with explicit environment loading.

Direct construction uses only arguments and defaults. ``from_env()`` reads the
process environment through Pydantic's native source; neither path loads dotenv.
Transport settings and client endpoints remain owned by their respective adapters.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource

from src.runtime.integrations.redis_mode import DEFAULT_REDIS_MODE, RedisMode, parse_redis_mode


class GraphConfig(BaseSettings):
    """One flat runtime API; call ``from_env()`` explicitly to load environment values."""

    model_config = SettingsConfigDict(extra="forbid", populate_by_name=True, env_file=None)

    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("llm_model", "LLM_MODEL"),
    )
    llm_temperature: float = Field(
        default=0.7,
        validation_alias=AliasChoices("llm_temperature", "LLM_TEMPERATURE"),
    )
    generate_max_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices("generate_max_tokens", "GENERATE_MAX_TOKENS"),
    )
    reasoning_effort: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reasoning_effort", "REASONING_EFFORT"),
    )
    reasoning_format: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reasoning_format", "REASONING_FORMAT"),
    )
    disable_reasoning: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("disable_reasoning", "DISABLE_REASONING"),
    )
    rewrite_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("rewrite_model", "REWRITE_MODEL"),
    )
    rewrite_max_tokens: int = Field(
        default=64,
        validation_alias=AliasChoices("rewrite_max_tokens", "REWRITE_MAX_TOKENS"),
    )
    bge_m3_timeout: float = Field(
        default=120.0,
        validation_alias=AliasChoices("bge_m3_timeout", "BGE_M3_TIMEOUT"),
    )
    rerank_top_k: int = Field(
        default=7,
        validation_alias=AliasChoices("rerank_top_k", "RERANK_TOP_K"),
    )
    redis_url: str = Field(
        default="redis://redis:6379",
        validation_alias=AliasChoices("redis_url", "REDIS_URL"),
        repr=False,
    )
    redis_mode: RedisMode = Field(
        default=DEFAULT_REDIS_MODE,
        validation_alias=AliasChoices("redis_mode", "REDIS_MODE"),
    )
    max_rewrite_attempts: int = Field(
        default=1,
        validation_alias=AliasChoices("max_rewrite_attempts", "MAX_REWRITE_ATTEMPTS"),
    )
    # RRF k=60 scores: top-1 is ~0.016; 0.018 preserves reranking for borderline hits.
    skip_rerank_threshold: float = Field(
        default=0.018,
        validation_alias=AliasChoices("skip_rerank_threshold", "SKIP_RERANK_THRESHOLD"),
    )
    # Deliberately loose: top-20 RRF scores are ~0.012..0.016; reject only very low scores.
    relevance_threshold_rrf: float = Field(
        default=0.005,
        validation_alias=AliasChoices("relevance_threshold_rrf", "RELEVANCE_THRESHOLD_RRF"),
    )
    score_improvement_delta: float = Field(
        default=0.001,
        validation_alias=AliasChoices("score_improvement_delta", "SCORE_IMPROVEMENT_DELTA"),
    )
    small_to_big_mode: str = Field(
        default="on",
        validation_alias=AliasChoices("small_to_big_mode", "SMALL_TO_BIG_MODE"),
    )
    small_to_big_window_before: int = Field(
        default=0,
        validation_alias=AliasChoices("small_to_big_window_before", "SMALL_TO_BIG_WINDOW_BEFORE"),
    )
    small_to_big_window_after: int = Field(
        default=2,
        validation_alias=AliasChoices("small_to_big_window_after", "SMALL_TO_BIG_WINDOW_AFTER"),
    )
    max_expanded_chunks: int = Field(
        default=10,
        validation_alias=AliasChoices("max_expanded_chunks", "MAX_EXPANDED_CHUNKS"),
    )
    max_context_tokens: int = Field(
        default=8000,
        validation_alias=AliasChoices("max_context_tokens", "MAX_CONTEXT_TOKENS"),
    )
    domain: str = Field(
        default="недвижимость",
        validation_alias=AliasChoices("domain", "BOT_DOMAIN"),
    )
    response_style_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("response_style_enabled", "RESPONSE_STYLE_ENABLED"),
    )
    response_style_shadow_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("response_style_shadow_mode", "RESPONSE_STYLE_SHADOW_MODE"),
    )
    show_sources: bool = Field(
        default=False,
        validation_alias=AliasChoices("show_sources", "SHOW_SOURCES"),
    )
    guard_mode: str = Field(
        default="hard",
        validation_alias=AliasChoices("guard_mode", "GUARD_MODE"),
    )
    content_filter_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("content_filter_enabled", "CONTENT_FILTER_ENABLED"),
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],  # noqa: ARG003 - native hook signature
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003 - explicit from_env only
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003 - never load dotenv
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003 - init only
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Preserve construction-time isolation from ambient environment and files.
        return (init_settings,)

    @classmethod
    def from_env(cls) -> GraphConfig:
        """Read current process environment, retaining the established normalization."""
        values = EnvSettingsSource(cls)()
        values["redis_mode"] = parse_redis_mode(values.get("redis_mode"))
        config = cls(**values)
        if not values.get("rewrite_model"):
            config.rewrite_model = config.llm_model
        config.reasoning_effort = config.reasoning_effort or None
        config.reasoning_format = config.reasoning_format or None
        return config

    def get_reasoning_kwargs(self) -> dict[str, Any]:
        """Return SDK-shaped reasoning params for chat.completions.create()."""
        extra_body: dict[str, Any] = {}
        if self.disable_reasoning is not None:
            extra_body["disable_reasoning"] = self.disable_reasoning
            return {"extra_body": extra_body}

        kwargs: dict[str, Any] = {}
        if self.reasoning_effort is not None:
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.reasoning_format is not None:
            extra_body["reasoning_format"] = self.reasoning_format
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def create_llm(self, model_override: str | None = None) -> Any:
        """Create the native LiteLLM SDK client."""
        from src.runtime.llm import create_llm_client

        return create_llm_client(
            model=model_override or self.llm_model,
            timeout=60.0,
        )


__all__ = ["GraphConfig"]
